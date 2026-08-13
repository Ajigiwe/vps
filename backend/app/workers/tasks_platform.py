"""Background task: provision customer environment."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.platform import PlatformJob
from app.services.platform.billing import SubscriptionBillingService
from app.services.platform.provisioning import ProvisioningEngine
from app.workers.base import BaseTask, TaskContext, TaskResult, TaskStatus

logger = get_logger(__name__)


class ProvisionEnvironmentTask(BaseTask):
    name = "provision_environment"
    queue = "default"
    max_attempts = 3

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    async def execute(self, payload: dict[str, Any], context: TaskContext) -> TaskResult:
        job_id = payload.get("job_id")
        async with self._session_factory() as session:
            try:
                job: PlatformJob | None = None
                if job_id:
                    job = await session.get(PlatformJob, UUID(str(job_id)))
                if job is None:
                    # Reconstruct ephemeral job from payload
                    job = PlatformJob(
                        job_type="provision_environment",
                        customer_id=UUID(payload["customer_id"]) if payload.get("customer_id") else None,
                        status="pending",
                        payload=payload,
                    )
                    session.add(job)
                    await session.flush()

                engine = ProvisioningEngine(self._settings, session)
                env = await engine.run_job(job)
                await session.commit()
                return TaskResult(
                    status=TaskStatus.COMPLETED,
                    data={"environment_id": str(env.id), "domain": env.domain},
                )
            except Exception as exc:
                await session.rollback()
                logger.exception("provision_task_failed")
                return TaskResult(status=TaskStatus.FAILED, error=str(exc))


class SubscriptionTickTask(BaseTask):
    name = "subscription_tick"
    queue = "default"
    max_attempts = 1

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    async def execute(self, payload: dict[str, Any], context: TaskContext) -> TaskResult:
        async with self._session_factory() as session:
            try:
                summary = await SubscriptionBillingService(self._settings, session).tick()
                await session.commit()
                return TaskResult(status=TaskStatus.COMPLETED, data=summary)
            except Exception as exc:
                await session.rollback()
                logger.exception("subscription_tick_failed")
                return TaskResult(status=TaskStatus.FAILED, error=str(exc))
