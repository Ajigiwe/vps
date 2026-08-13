"""Resource manager — capacity checks and 20% safety reserve."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import CustomerEnvironment, HostingPlan, InfrastructureNode, Subscription


@dataclass
class CapacitySnapshot:
    node_id: str
    hostname: str
    cpu_total: int
    ram_total_gb: int
    storage_total_gb: int
    cpu_reserved_pct: int
    cpu_allocatable: int
    ram_allocatable: int
    storage_allocatable: int
    cpu_used: int
    ram_used: int
    storage_used: int
    cpu_free: int
    ram_free: int
    storage_free: int
    status: str


class ResourceManager:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_nodes(self) -> list[InfrastructureNode]:
        result = await self._session.execute(
            select(InfrastructureNode).order_by(InfrastructureNode.hostname)
        )
        return list(result.scalars().all())

    async def pick_node_for_plan(self, plan: HostingPlan) -> InfrastructureNode:
        nodes = await self.list_nodes()
        healthy = [n for n in nodes if n.status in {"healthy", "warning"}]
        if not healthy:
            raise RuntimeError("No healthy infrastructure nodes available.")

        best: InfrastructureNode | None = None
        best_free = -1
        for node in healthy:
            snap = await self.snapshot(node)
            if (
                snap.cpu_free >= plan.cpu_cores
                and snap.ram_free >= plan.ram_gb
                and snap.storage_free >= plan.storage_gb
            ):
                free_score = snap.cpu_free + snap.ram_free + snap.storage_free
                if free_score > best_free:
                    best = node
                    best_free = free_score
        if best is None:
            raise RuntimeError(
                "Insufficient capacity for this plan. Contact IFNOTUS support or choose a smaller plan."
            )
        return best

    async def snapshot(self, node: InfrastructureNode) -> CapacitySnapshot:
        reserved_cpu = max(1, int(node.cpu_total * node.cpu_reserved_pct / 100))
        reserved_ram = max(1, int(node.ram_total_gb * node.cpu_reserved_pct / 100))
        reserved_storage = max(1, int(node.storage_total_gb * node.cpu_reserved_pct / 100))

        cpu_alloc = node.cpu_total - reserved_cpu
        ram_alloc = node.ram_total_gb - reserved_ram
        storage_alloc = node.storage_total_gb - reserved_storage

        result = await self._session.execute(
            select(
                func.coalesce(func.sum(CustomerEnvironment.cpu_limit), 0),
                func.coalesce(func.sum(CustomerEnvironment.ram_limit_gb), 0),
                func.coalesce(func.sum(CustomerEnvironment.storage_limit_gb), 0),
            ).where(
                CustomerEnvironment.node_id == node.id,
                CustomerEnvironment.status.in_(["provisioning", "active", "suspended"]),
            )
        )
        cpu_used, ram_used, storage_used = result.one()
        cpu_used_i = int(cpu_used or 0)
        ram_used_i = int(ram_used or 0)
        storage_used_i = int(storage_used or 0)

        return CapacitySnapshot(
            node_id=str(node.id),
            hostname=node.hostname,
            cpu_total=node.cpu_total,
            ram_total_gb=node.ram_total_gb,
            storage_total_gb=node.storage_total_gb,
            cpu_reserved_pct=node.cpu_reserved_pct,
            cpu_allocatable=cpu_alloc,
            ram_allocatable=ram_alloc,
            storage_allocatable=storage_alloc,
            cpu_used=cpu_used_i,
            ram_used=ram_used_i,
            storage_used=storage_used_i,
            cpu_free=max(0, cpu_alloc - cpu_used_i),
            ram_free=max(0, ram_alloc - ram_used_i),
            storage_free=max(0, storage_alloc - storage_used_i),
            status=node.status,
        )

    async def active_subscription_usage(self, customer_id) -> dict:
        result = await self._session.execute(
            select(Subscription).where(
                Subscription.customer_id == customer_id,
                Subscription.status == "active",
            )
        )
        subs = list(result.scalars().all())
        return {
            "active_subscriptions": len(subs),
            "cpu": sum(s.cpu_allocated for s in subs),
            "ram_gb": sum(s.ram_allocated for s in subs),
            "storage_gb": sum(s.storage_allocated for s in subs),
            "bandwidth_used_gb": float(sum((s.bandwidth_used_gb or Decimal(0)) for s in subs)),
        }
