"""Provisioning engine — create customer environment using Podium hosting tools."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.hosting import Domain
from app.models.platform import (
    CustomerEnvironment,
    HostingPlan,
    Notification,
    Order,
    PlatformAuditLog,
    PlatformJob,
    Subscription,
)
from app.services.hosting.nginx_provisioner import DomainNginxProvisioner
from app.services.platform.isolation import IsolationService
from app.services.platform.resources import ResourceManager

logger = get_logger(__name__)


class ProvisioningEngine:
    def __init__(self, settings: Settings, session: AsyncSession) -> None:
        self._settings = settings
        self._session = session
        self._resources = ResourceManager(session)
        self._nginx = DomainNginxProvisioner(settings)
        self._isolation = IsolationService(settings)

    async def run_job(self, job: PlatformJob) -> CustomerEnvironment:
        job.status = "running"
        job.started_at = datetime.now(UTC)
        await self._session.flush()

        payload = job.payload or {}
        order_id = UUID(payload["order_id"])
        subscription_id = UUID(payload["subscription_id"])
        plan_id = UUID(payload["plan_id"])
        domain_name = payload.get("domain_name")

        order = await self._session.get(Order, order_id)
        sub = await self._session.get(Subscription, subscription_id)
        plan = await self._session.get(HostingPlan, plan_id)
        if not order or not sub or not plan:
            raise RuntimeError("Order/subscription/plan missing for provision job.")

        node = await self._resources.pick_node_for_plan(plan)
        hostname = (domain_name or f"env-{str(order.id)[:8]}.customers.Podium.space").lower()
        doc_root = str(Path(self._settings.customer_environments_root) / str(order.customer_id) / hostname)
        self._nginx.ensure_document_root(doc_root)

        isolation = self._isolation.preferred_mode()
        container_id = None
        container_port = None
        if isolation == "docker":
            container_port = self._isolation.allocate_port(str(order.id))
            container_id = self._isolation.start_container(
                env_id=str(order.id),
                document_root=doc_root,
                cpu=plan.cpu_cores,
                ram_gb=plan.ram_gb,
                port=container_port,
            )
            if not container_id:
                isolation = "filesystem"
                container_port = None

        domain = Domain(
            name=hostname,
            domain_type="primary",
            document_root=doc_root,
            enabled=True,
            nginx_enabled=True,
            force_https=False,
            notes=f"Podium customer environment for order {order.id}",
        )
        self._session.add(domain)
        await self._session.flush()

        # Nginx vhost (skip if not on a real host with nginx dirs)
        try:
            await self._nginx.provision(
                hostname=hostname,
                document_root=doc_root,
                proxy_port=container_port,
                force_https=False,
                redirect_url=None,
                enabled=True,
                create_docroot=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("nginx_provision_skipped", error=str(exc), domain=hostname)

        env = CustomerEnvironment(
            subscription_id=sub.id,
            customer_id=order.customer_id,
            node_id=node.id,
            hosting_domain_id=domain.id,
            container_id=container_id,
            isolation_type=isolation,
            container_port=container_port,
            status="active",
            cpu_limit=plan.cpu_cores,
            ram_limit_gb=plan.ram_gb,
            storage_limit_gb=plan.storage_gb,
            ip_address=node.ip_address,
            domain=hostname,
            document_root=doc_root,
            health_status="healthy",
        )
        self._session.add(env)

        order.provisioning_status = "active"
        job.status = "success"
        job.completed_at = datetime.now(UTC)
        job.result = {
            "environment_id": str(env.id),
            "domain": hostname,
            "document_root": doc_root,
            "node": node.hostname,
            "isolation": isolation,
            "container_id": container_id,
            "container_port": container_port,
        }
        job.environment_id = env.id

        self._session.add(
            Notification(
                customer_id=order.customer_id,
                title="Hosting is ready",
                body=f"Your Podium environment is live at {hostname}.",
                kind="provision",
                channel="panel",
            )
        )
        self._session.add(
            PlatformAuditLog(
                customer_id=order.customer_id,
                action="environment.provisioned",
                target_type="environment",
                target_id=str(env.id),
                result="success",
                metadata_json=job.result,
            )
        )
        await self._session.flush()

        # SSL best-effort (webroot must be reachable publicly)
        try:
            from app.schemas.hosting import SslActionRequest
            from app.services.hosting.ssl import SslService

            ssl = SslService(self._settings, self._session)
            await ssl.issue(SslActionRequest(domain=hostname, webroot=doc_root, dry_run=False))
        except Exception as exc:  # noqa: BLE001
            logger.info("ssl_issue_deferred", domain=hostname, error=str(exc))

        return env

    async def list_environments(self, customer_id: UUID) -> list[CustomerEnvironment]:
        result = await self._session.execute(
            select(CustomerEnvironment)
            .where(CustomerEnvironment.customer_id == customer_id)
            .order_by(CustomerEnvironment.created_at.desc())
        )
        return list(result.scalars().all())
