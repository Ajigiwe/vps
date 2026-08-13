"""Environment lifecycle helpers (suspend / terminate / backup stub)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppException, NotFoundError
from app.services.platform.isolation import IsolationService
from app.models.platform import (
    CustomerEnvironment,
    EnvironmentBackup,
    Notification,
    PlatformAuditLog,
    PlatformJob,
    Subscription,
)


class EnvironmentLifecycleService:
    def __init__(self, settings: Settings, session: AsyncSession) -> None:
        self._settings = settings
        self._session = session

    async def get_owned(self, customer_id: UUID, environment_id: UUID) -> CustomerEnvironment:
        result = await self._session.execute(
            select(CustomerEnvironment).where(
                CustomerEnvironment.id == environment_id,
                CustomerEnvironment.customer_id == customer_id,
            )
        )
        env = result.scalar_one_or_none()
        if env is None:
            raise NotFoundError("Environment not found.")
        return env

    async def suspend(self, customer_id: UUID, environment_id: UUID) -> CustomerEnvironment:
        env = await self.get_owned(customer_id, environment_id)
        if env.status == "terminated":
            raise AppException("Environment is terminated.")
        env.status = "suspended"
        env.health_status = "warning"
        sub = await self._session.get(Subscription, env.subscription_id)
        if sub:
            sub.status = "suspended"
        self._session.add(
            Notification(
                customer_id=customer_id,
                title="Environment suspended",
                body=f"{env.domain or env.id} has been suspended.",
                kind="lifecycle",
            )
        )
        self._session.add(
            PlatformAuditLog(
                customer_id=customer_id,
                action="environment.suspend",
                target_type="environment",
                target_id=str(env.id),
                result="success",
            )
        )
        await self._session.flush()
        return env

    async def restore(self, customer_id: UUID, environment_id: UUID) -> CustomerEnvironment:
        env = await self.get_owned(customer_id, environment_id)
        if env.status == "terminated":
            raise AppException("Cannot restore a terminated environment.")
        env.status = "active"
        env.health_status = "healthy"
        sub = await self._session.get(Subscription, env.subscription_id)
        if sub:
            sub.status = "active"
        self._session.add(
            Notification(
                customer_id=customer_id,
                title="Environment restored",
                body=f"{env.domain or env.id} is active again.",
                kind="lifecycle",
            )
        )
        await self._session.flush()
        return env

    async def terminate(self, customer_id: UUID, environment_id: UUID) -> CustomerEnvironment:
        env = await self.get_owned(customer_id, environment_id)
        IsolationService(self._settings).stop_container(env.container_id, env_id=str(env.id))
        env.container_id = None
        # Retention: mark terminated; physical destroy is a follow-up job
        env.status = "terminated"
        env.health_status = "critical"
        sub = await self._session.get(Subscription, env.subscription_id)
        if sub:
            sub.status = "terminated"
        job = PlatformJob(
            job_type="terminate_environment",
            customer_id=customer_id,
            environment_id=env.id,
            status="pending",
            payload={"environment_id": str(env.id), "domain": env.domain},
        )
        self._session.add(job)
        self._session.add(
            PlatformAuditLog(
                customer_id=customer_id,
                action="environment.terminate",
                target_type="environment",
                target_id=str(env.id),
                result="success",
            )
        )
        await self._session.flush()
        return env

    async def create_backup(self, customer_id: UUID, environment_id: UUID) -> EnvironmentBackup:
        env = await self.get_owned(customer_id, environment_id)
        backup_root = Path(self._settings.operations_backup_dir) / "customers" / str(customer_id)
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        filename = str(backup_root / f"{env.id}_{stamp}.meta.json")
        Path(filename).write_text(
            f'{{"environment_id":"{env.id}","domain":"{env.domain}","created_at":"{datetime.now(UTC).isoformat()}"}}\n',
            encoding="utf-8",
        )
        row = EnvironmentBackup(
            customer_id=customer_id,
            environment_id=env.id,
            filename=filename,
            file_size=Path(filename).stat().st_size,
            checksum=None,
            backup_type="full",
            status="success",
            verified_at=datetime.now(UTC),
        )
        self._session.add(row)
        self._session.add(
            PlatformJob(
                job_type="backup_environment",
                customer_id=customer_id,
                environment_id=env.id,
                status="success",
                payload={"filename": filename},
                result={"filename": filename},
                completed_at=datetime.now(UTC),
            )
        )
        await self._session.flush()
        return row

    async def list_backups(self, customer_id: UUID, environment_id: UUID | None = None) -> list[EnvironmentBackup]:
        stmt = select(EnvironmentBackup).where(EnvironmentBackup.customer_id == customer_id)
        if environment_id:
            stmt = stmt.where(EnvironmentBackup.environment_id == environment_id)
        stmt = stmt.order_by(EnvironmentBackup.created_at.desc()).limit(100)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
