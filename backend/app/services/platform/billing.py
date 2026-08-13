"""Subscription lifecycle — reminders, grace, suspend, renew, upgrade."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppException, NotFoundError
from app.core.logging import get_logger
from app.models.platform import (
    CustomerEnvironment,
    HostingPlan,
    Notification,
    PlatformAuditLog,
    Subscription,
)
from app.services.platform.isolation import IsolationService
from app.services.platform.resources import ResourceManager

logger = get_logger(__name__)

REMINDER_DAYS = (30, 14, 7, 1)


class SubscriptionBillingService:
    def __init__(self, settings: Settings, session: AsyncSession) -> None:
        self._settings = settings
        self._session = session
        self._resources = ResourceManager(session)
        self._isolation = IsolationService(settings)

    async def list_for_customer(self, customer_id: UUID) -> list[Subscription]:
        result = await self._session.execute(
            select(Subscription)
            .where(Subscription.customer_id == customer_id)
            .order_by(Subscription.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_owned(self, customer_id: UUID, subscription_id: UUID) -> Subscription:
        result = await self._session.execute(
            select(Subscription).where(
                Subscription.id == subscription_id,
                Subscription.customer_id == customer_id,
            )
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            raise NotFoundError("Subscription not found.")
        return sub

    async def set_auto_renew(self, customer_id: UUID, subscription_id: UUID, enabled: bool) -> Subscription:
        sub = await self.get_owned(customer_id, subscription_id)
        sub.auto_renew = enabled
        await self._session.flush()
        return sub

    async def renew(self, customer_id: UUID, subscription_id: UUID, *, days: int = 30) -> Subscription:
        sub = await self.get_owned(customer_id, subscription_id)
        now = datetime.now(UTC)
        base = sub.expires_at if sub.expires_at and sub.expires_at > now else now
        sub.expires_at = base + timedelta(days=days)
        sub.renewed_at = now
        sub.grace_until = None
        sub.last_reminder_days = None
        if sub.status in {"expired", "suspended", "grace"}:
            sub.status = "active"
            await self._restore_environments(sub)
        self._session.add(
            Notification(
                customer_id=customer_id,
                title="Subscription renewed",
                body=f"Your Podium hosting is extended until {sub.expires_at.date().isoformat()}.",
                kind="renewal",
            )
        )
        self._session.add(
            PlatformAuditLog(
                customer_id=customer_id,
                action="subscription.renewed",
                target_type="subscription",
                target_id=str(sub.id),
                result="success",
            )
        )
        await self._session.flush()
        return sub

    async def change_plan(self, customer_id: UUID, subscription_id: UUID, plan_id: UUID) -> Subscription:
        sub = await self.get_owned(customer_id, subscription_id)
        if sub.status not in {"active", "grace"}:
            raise AppException("Only active subscriptions can be upgraded or downgraded.")
        plan = await self._session.get(HostingPlan, plan_id)
        if plan is None or not plan.is_active:
            raise NotFoundError("Hosting plan not found.")
        if plan.id == sub.plan_id:
            raise AppException("Already on this plan.")

        # Capacity only matters when increasing resources
        if plan.cpu_cores > sub.cpu_allocated or plan.ram_gb > sub.ram_allocated or plan.storage_gb > sub.storage_allocated:
            await self._resources.pick_node_for_plan(plan)

        sub.plan_id = plan.id
        sub.cpu_allocated = plan.cpu_cores
        sub.ram_allocated = plan.ram_gb
        sub.storage_allocated = plan.storage_gb

        envs = await self._envs(sub.id)
        for env in envs:
            env.cpu_limit = plan.cpu_cores
            env.ram_limit_gb = plan.ram_gb
            env.storage_limit_gb = plan.storage_gb
            if env.container_id:
                self._isolation.resize_container(
                    env.container_id, cpu=plan.cpu_cores, ram_gb=plan.ram_gb
                )

        self._session.add(
            Notification(
                customer_id=customer_id,
                title="Plan changed",
                body=f"Your plan is now {plan.name} ({plan.cpu_cores} vCPU / {plan.ram_gb} GB).",
                kind="billing",
            )
        )
        self._session.add(
            PlatformAuditLog(
                customer_id=customer_id,
                action="subscription.plan_changed",
                target_type="subscription",
                target_id=str(sub.id),
                result="success",
                metadata_json={"plan": plan.slug},
            )
        )
        await self._session.flush()
        return sub

    async def tick(self) -> dict:
        """Daily-style sweep: reminders, grace, suspend, terminate."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(Subscription).where(Subscription.status.in_(["active", "grace", "suspended", "expired"]))
        )
        subs = list(result.scalars().all())
        summary = {"reminded": 0, "grace": 0, "suspended": 0, "terminated": 0, "auto_renewed": 0}

        for sub in subs:
            if not sub.expires_at:
                continue
            days_left = (sub.expires_at.date() - now.date()).days

            if sub.status == "active" and days_left in REMINDER_DAYS and sub.last_reminder_days != days_left:
                await self._remind(sub, days_left)
                sub.last_reminder_days = days_left
                summary["reminded"] += 1

            if sub.status == "active" and days_left < 0:
                if sub.auto_renew:
                    await self.renew(sub.customer_id, sub.id)
                    summary["auto_renewed"] += 1
                    continue
                grace = timedelta(days=self._settings.subscription_grace_days)
                sub.status = "grace"
                sub.grace_until = now + grace
                self._session.add(
                    Notification(
                        customer_id=sub.customer_id,
                        title="Payment overdue — grace period",
                        body=(
                            f"Your hosting expired. You have {self._settings.subscription_grace_days} "
                            "days to renew before the site is suspended."
                        ),
                        kind="grace",
                    )
                )
                summary["grace"] += 1

            if sub.status == "grace" and sub.grace_until and now >= sub.grace_until:
                sub.status = "suspended"
                await self._suspend_environments(sub, reason="Subscription grace period ended.")
                summary["suspended"] += 1

            if sub.status == "suspended" and sub.expires_at:
                terminate_after = timedelta(days=self._settings.subscription_terminate_after_days)
                if now >= sub.expires_at + terminate_after:
                    sub.status = "terminated"
                    await self._terminate_environments(sub)
                    summary["terminated"] += 1

        await self._session.flush()
        logger.info("subscription_tick", **summary)
        return summary

    async def _remind(self, sub: Subscription, days_left: int) -> None:
        when = "today" if days_left == 1 else f"in {days_left} days"
        self._session.add(
            Notification(
                customer_id=sub.customer_id,
                title=f"Hosting renews {when}",
                body=(
                    f"Your Podium subscription expires {when}. "
                    "Renew from the panel to keep your site online."
                ),
                kind=f"renewal_{days_left}",
            )
        )

    async def _envs(self, subscription_id: UUID) -> list[CustomerEnvironment]:
        result = await self._session.execute(
            select(CustomerEnvironment).where(CustomerEnvironment.subscription_id == subscription_id)
        )
        return list(result.scalars().all())

    async def _suspend_environments(self, sub: Subscription, *, reason: str) -> None:
        for env in await self._envs(sub.id):
            if env.status == "terminated":
                continue
            env.status = "suspended"
            env.health_status = "warning"
        self._session.add(
            Notification(
                customer_id=sub.customer_id,
                title="Hosting suspended",
                body=reason,
                kind="suspend",
            )
        )

    async def _restore_environments(self, sub: Subscription) -> None:
        for env in await self._envs(sub.id):
            if env.status == "suspended":
                env.status = "active"
                env.health_status = "healthy"

    async def _terminate_environments(self, sub: Subscription) -> None:
        for env in await self._envs(sub.id):
            env.status = "terminated"
            env.health_status = "critical"
            self._isolation.stop_container(env.container_id, env_id=str(env.id))
        self._session.add(
            Notification(
                customer_id=sub.customer_id,
                title="Hosting terminated",
                body="The subscription was not renewed. Resources have been released.",
                kind="terminate",
            )
        )
