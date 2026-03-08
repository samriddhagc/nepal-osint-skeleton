"""Notification repository for data access."""
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import UserNotification


class NotificationRepository:
    """Data access for user notifications."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: UUID,
        type: str,
        title: str,
        message: str | None = None,
        data: dict | None = None,
    ) -> UserNotification:
        """Create a notification."""
        notification = UserNotification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            data=data,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def get_for_user(
        self,
        user_id: UUID,
        limit: int = 50,
    ) -> tuple[list[UserNotification], int]:
        """Get notifications for user. Returns (items, unread_count)."""
        # Get notifications
        result = await self.db.execute(
            select(UserNotification)
            .where(UserNotification.user_id == user_id)
            .order_by(UserNotification.created_at.desc())
            .limit(limit)
        )
        items = list(result.scalars().all())

        # Unread count
        unread_result = await self.db.execute(
            select(func.count()).where(
                and_(
                    UserNotification.user_id == user_id,
                    UserNotification.is_read == False,
                )
            )
        )
        unread_count = unread_result.scalar() or 0

        return items, unread_count

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> bool:
        """Mark a single notification as read."""
        result = await self.db.execute(
            update(UserNotification)
            .where(
                and_(
                    UserNotification.id == notification_id,
                    UserNotification.user_id == user_id,
                )
            )
            .values(is_read=True)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def mark_all_read(self, user_id: UUID) -> int:
        """Mark all notifications as read for a user."""
        result = await self.db.execute(
            update(UserNotification)
            .where(
                and_(
                    UserNotification.user_id == user_id,
                    UserNotification.is_read == False,
                )
            )
            .values(is_read=True)
        )
        await self.db.commit()
        return result.rowcount

    async def get_unread_count(self, user_id: UUID) -> int:
        """Get count of unread notifications."""
        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    UserNotification.user_id == user_id,
                    UserNotification.is_read == False,
                )
            )
        )
        return result.scalar() or 0
