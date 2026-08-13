"""Customer notifications."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.platform import Notification


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_customer(self, customer_id: UUID, *, unread_only: bool = False) -> list[Notification]:
        stmt = select(Notification).where(Notification.customer_id == customer_id)
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        stmt = stmt.order_by(Notification.created_at.desc()).limit(100)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_read(self, customer_id: UUID, notification_id: UUID) -> Notification:
        result = await self._session.execute(
            select(Notification).where(
                Notification.id == notification_id, Notification.customer_id == customer_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("Notification not found.")
        row.is_read = True
        await self._session.flush()
        return row

    async def notify(
        self,
        customer_id: UUID,
        *,
        title: str,
        body: str,
        kind: str = "info",
        channel: str = "panel",
    ) -> Notification:
        row = Notification(
            customer_id=customer_id,
            title=title,
            body=body,
            kind=kind,
            channel=channel,
        )
        self._session.add(row)
        await self._session.flush()
        return row
