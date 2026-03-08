"""In-app notification service."""
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.notification_repository import NotificationRepository

logger = logging.getLogger(__name__)


class NotificationService:
    """Manages in-app notifications for the correction workflow."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NotificationRepository(db)

    async def notify_correction_approved(
        self, user_id: UUID, candidate_name: str, field: str, correction_id: UUID
    ):
        """Notify analyst that their correction was approved."""
        await self.repo.create(
            user_id=user_id,
            type="correction_approved",
            title="Correction Approved",
            message=f"Your correction to {candidate_name}'s {field} was approved",
            data={"correction_id": str(correction_id)},
        )

    async def notify_correction_rejected(
        self, user_id: UUID, candidate_name: str, field: str, correction_id: UUID, reason: str
    ):
        """Notify analyst that their correction was rejected."""
        await self.repo.create(
            user_id=user_id,
            type="correction_rejected",
            title="Correction Rejected",
            message=f"Your correction to {candidate_name}'s {field} was rejected: {reason}",
            data={"correction_id": str(correction_id), "reason": reason},
        )

    async def notify_correction_rolled_back(
        self, user_id: UUID, candidate_name: str, field: str, correction_id: UUID
    ):
        """Notify analyst that their approved correction was rolled back."""
        await self.repo.create(
            user_id=user_id,
            type="correction_rolled_back",
            title="Correction Rolled Back",
            message=f"Your approved correction to {candidate_name}'s {field} was rolled back",
            data={"correction_id": str(correction_id)},
        )

    async def notify_bulk_upload_complete(
        self, user_id: UUID, total: int, valid: int, invalid: int, batch_id: str
    ):
        """Notify dev that bulk upload processing is complete."""
        await self.repo.create(
            user_id=user_id,
            type="bulk_upload_complete",
            title="Bulk Upload Complete",
            message=f"Processed {total} rows: {valid} valid, {invalid} invalid",
            data={"batch_id": batch_id, "total": total, "valid": valid, "invalid": invalid},
        )

    async def get_notifications(self, user_id: UUID, limit: int = 50) -> dict:
        """Get notifications for a user."""
        items, unread_count = await self.repo.get_for_user(user_id, limit)
        return {
            "items": [
                {
                    "id": str(n.id),
                    "type": n.type,
                    "title": n.title,
                    "message": n.message,
                    "data": n.data,
                    "is_read": n.is_read,
                    "created_at": n.created_at,
                }
                for n in items
            ],
            "unread_count": unread_count,
        }

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> dict:
        """Mark a single notification as read."""
        success = await self.repo.mark_read(notification_id, user_id)
        return {"success": success}

    async def mark_all_read(self, user_id: UUID) -> dict:
        """Mark all notifications as read."""
        count = await self.repo.mark_all_read(user_id)
        return {"success": True, "marked_read": count}
