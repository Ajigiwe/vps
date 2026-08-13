"""AI Engineer credit wallet."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundError
from app.models.platform import AiCreditAccount, AiOperation, PlatformAuditLog


class AiCreditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_account(self, customer_id: UUID) -> AiCreditAccount:
        result = await self._session.execute(
            select(AiCreditAccount).where(AiCreditAccount.customer_id == customer_id)
        )
        account = result.scalar_one_or_none()
        if account is None:
            account = AiCreditAccount(customer_id=customer_id)
            self._session.add(account)
            await self._session.flush()
        return account

    async def assert_credits(self, customer_id: UUID, cost: int = 1) -> AiCreditAccount:
        account = await self.get_account(customer_id)
        if account.credits_remaining < cost:
            raise AppException("Insufficient AI Engineer credits. Top up or upgrade your plan.")
        return account

    async def start_operation(
        self,
        *,
        customer_id: UUID,
        environment_id: UUID | None,
        operation_type: str,
        permission_level: int,
        request: str,
        risk: str = "low",
        require_confirm: bool = False,
        cost: int = 1,
    ) -> AiOperation:
        if permission_level < 1 or permission_level > 4:
            raise AppException("permission_level must be 1–4.")
        account = await self.assert_credits(customer_id, cost)
        op = AiOperation(
            customer_id=customer_id,
            environment_id=environment_id,
            operation_type=operation_type,
            permission_level=permission_level,
            credits_used=cost,
            status="authorized" if not require_confirm else "pending",
            request=request,
            risk_classification=risk,
            required_confirmation=require_confirm or permission_level >= 3,
        )
        self._session.add(op)
        # Reserve credits only when auto-authorized (levels 1–2)
        if not op.required_confirmation:
            account.credits_remaining -= cost
            account.lifetime_used += cost
            op.status = "running"
        await self._session.flush()
        return op

    async def confirm_operation(self, customer_id: UUID, operation_id: UUID) -> AiOperation:
        op = await self._get_op(customer_id, operation_id)
        if op.status not in {"pending", "authorized"}:
            raise AppException(f"Operation cannot be confirmed (status={op.status}).")
        account = await self.assert_credits(customer_id, op.credits_used)
        account.credits_remaining -= op.credits_used
        account.lifetime_used += op.credits_used
        op.status = "running"
        await self._session.flush()
        return op

    async def complete_operation(
        self, customer_id: UUID, operation_id: UUID, *, success: bool, result: str
    ) -> AiOperation:
        op = await self._get_op(customer_id, operation_id)
        op.status = "success" if success else "failed"
        op.result = result
        op.completed_at = datetime.now(UTC)
        self._session.add(
            PlatformAuditLog(
                customer_id=customer_id,
                action="ai.operation",
                target_type="ai_operation",
                target_id=str(op.id),
                result="success" if success else "failed",
                metadata_json={"type": op.operation_type, "level": op.permission_level},
            )
        )
        await self._session.flush()
        return op

    async def list_operations(self, customer_id: UUID, limit: int = 50) -> list[AiOperation]:
        result = await self._session.execute(
            select(AiOperation)
            .where(AiOperation.customer_id == customer_id)
            .order_by(AiOperation.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _get_op(self, customer_id: UUID, operation_id: UUID) -> AiOperation:
        result = await self._session.execute(
            select(AiOperation).where(
                AiOperation.id == operation_id, AiOperation.customer_id == customer_id
            )
        )
        op = result.scalar_one_or_none()
        if op is None:
            raise NotFoundError("AI operation not found.")
        return op
