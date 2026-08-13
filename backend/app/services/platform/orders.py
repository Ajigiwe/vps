"""Orders + subscription creation after verified payment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppException, NotFoundError
from app.models.platform import (
    AiCreditAccount,
    Customer,
    CustomerDomain,
    HostingPlan,
    Notification,
    Order,
    PlatformAuditLog,
    PlatformJob,
    Subscription,
)
from app.schemas.platform import CreateOrderRequest, OrderResponse
from app.services.platform.paystack import PaystackService
from app.services.platform.resources import ResourceManager


DOMAIN_PRICES = {
    ".online": Decimal("50"),
    ".net": Decimal("200"),
    ".com": Decimal("250"),
}


class OrderService:
    def __init__(self, settings: Settings, session: AsyncSession) -> None:
        self._settings = settings
        self._session = session
        self._paystack = PaystackService(settings)
        self._resources = ResourceManager(session)

    async def create_order(self, customer: Customer, body: CreateOrderRequest) -> dict:
        plan = await self._get_plan(body.plan_id)
        # Capacity check before accepting payment
        await self._resources.pick_node_for_plan(plan)

        domain_name = (body.domain_name or "").lower().strip() or None
        extension = (body.domain_extension or "").lower().strip() or None
        if domain_name and not extension and "." in domain_name:
            host, ext = domain_name.split(".", 1)
            domain_name = domain_name
            extension = f".{ext}" if not ext.startswith(".") else ext

        domain_price = Decimal("0")
        if extension:
            domain_price = DOMAIN_PRICES.get(extension, Decimal("0"))
            if body.include_domain is False:
                domain_price = Decimal("0")

        plan_price = plan.price_monthly
        total = plan_price + domain_price
        order = Order(
            customer_id=customer.id,
            plan_id=plan.id,
            domain_name=domain_name,
            domain_extension=extension,
            plan_price=plan_price,
            domain_price=domain_price,
            total_price=total,
            currency=plan.currency or "GHS",
            payment_status="pending",
            provisioning_status="pending",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        self._session.add(order)
        await self._session.flush()

        reference = self._paystack.new_reference()
        order.paystack_reference = reference
        amount_pesewas = int(total * 100)
        init = await self._paystack.initialize_transaction(
            email=customer.email,
            amount_pesewas=amount_pesewas,
            reference=reference,
            callback_url=f"{self._settings.customer_portal_url}/billing/callback",
            metadata={"order_id": str(order.id), "customer_id": str(customer.id)},
        )
        self._session.add(
            PlatformAuditLog(
                customer_id=customer.id,
                action="order.create",
                target_type="order",
                target_id=str(order.id),
                result="success",
                metadata_json={"total": str(total), "reference": reference},
            )
        )
        await self._session.flush()
        return {
            "order": OrderResponse.model_validate(order),
            "authorization_url": (init.get("data") or {}).get("authorization_url"),
            "reference": reference,
            "demo": bool((init.get("data") or {}).get("demo")),
            "paystack_public_key": self._paystack.public_key,
        }

    async def verify_and_activate(self, reference: str) -> OrderResponse:
        order = await self._get_by_reference(reference)
        if order.payment_status == "paid":
            return OrderResponse.model_validate(order)

        await self._paystack.verify_transaction(reference)
        order.payment_status = "paid"
        order.paid_at = datetime.now(UTC)
        order.provisioning_status = "queued"

        plan = await self._get_plan(order.plan_id)
        sub = Subscription(
            customer_id=order.customer_id,
            order_id=order.id,
            plan_id=plan.id,
            status="active",
            cpu_allocated=plan.cpu_cores,
            ram_allocated=plan.ram_gb,
            storage_allocated=plan.storage_gb,
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=30),
            auto_renew=True,
        )
        self._session.add(sub)
        await self._session.flush()

        # AI credits from plan
        credits = await self._session.execute(
            select(AiCreditAccount).where(AiCreditAccount.customer_id == order.customer_id)
        )
        account = credits.scalar_one_or_none()
        if account is None:
            account = AiCreditAccount(customer_id=order.customer_id)
            self._session.add(account)
            await self._session.flush()
        account.credits_remaining += plan.ai_credits
        account.total_allocated += plan.ai_credits

        if order.domain_name:
            registrar_name = "pending"
            try:
                from app.services.platform.registrar import DomainRegistrar

                sld = order.domain_name
                ext = order.domain_extension or ""
                if "." in sld:
                    host, rest = sld.split(".", 1)
                    sld = host
                    if not ext:
                        ext = f".{rest}"
                result = await DomainRegistrar(self._settings).register(sld, ext or ".online")
                if result.get("registered"):
                    registrar_name = str(result.get("provider") or "namecheap")
                elif result.get("provider"):
                    registrar_name = str(result.get("provider"))
            except Exception:  # noqa: BLE001
                registrar_name = "pending"
            self._session.add(
                CustomerDomain(
                    customer_id=order.customer_id,
                    domain_name=order.domain_name,
                    registrar=registrar_name,
                    registration_date=datetime.now(UTC),
                    expiry_date=datetime.now(UTC) + timedelta(days=365),
                    auto_renew=True,
                    dns_records=[],
                    ssl_status="pending",
                )
            )

        job = PlatformJob(
            job_type="provision_environment",
            customer_id=order.customer_id,
            status="pending",
            payload={
                "order_id": str(order.id),
                "subscription_id": str(sub.id),
                "plan_id": str(plan.id),
                "domain_name": order.domain_name,
            },
        )
        self._session.add(job)
        self._session.add(
            Notification(
                customer_id=order.customer_id,
                title="Payment confirmed",
                body="Your IFNOTUS payment was verified. Provisioning has started.",
                kind="payment",
                channel="panel",
            )
        )
        self._session.add(
            PlatformAuditLog(
                customer_id=order.customer_id,
                action="order.paid",
                target_type="order",
                target_id=str(order.id),
                result="success",
                metadata_json={"reference": reference},
            )
        )
        await self._session.flush()

        # Best-effort enqueue (inline provision also available)
        await self._enqueue_or_run(job)
        return OrderResponse.model_validate(order)

    async def list_orders(self, customer_id: UUID) -> list[Order]:
        result = await self._session.execute(
            select(Order).where(Order.customer_id == customer_id).order_by(Order.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_order(self, customer_id: UUID, order_id: UUID) -> Order:
        result = await self._session.execute(
            select(Order).where(Order.id == order_id, Order.customer_id == customer_id)
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise NotFoundError("Order not found.")
        return order

    async def _enqueue_or_run(self, job: PlatformJob) -> None:
        from app.services.platform.provisioning import ProvisioningEngine

        engine = ProvisioningEngine(self._settings, self._session)
        try:
            await engine.run_job(job)
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error_info = str(exc)
            await self._session.flush()
            raise AppException(f"Provisioning failed: {exc}") from exc

    async def _get_plan(self, plan_id: UUID) -> HostingPlan:
        result = await self._session.execute(select(HostingPlan).where(HostingPlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if plan is None or not plan.is_active:
            raise NotFoundError("Hosting plan not found.")
        return plan

    async def _get_by_reference(self, reference: str) -> Order:
        result = await self._session.execute(select(Order).where(Order.paystack_reference == reference))
        order = result.scalar_one_or_none()
        if order is None:
            raise NotFoundError("Order not found for this payment reference.")
        return order
