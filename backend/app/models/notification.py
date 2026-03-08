"""User notification model for in-app notifications."""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Text, Boolean, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationType(str, Enum):
    """Notification types for the correction workflow."""
    CORRECTION_APPROVED = "correction_approved"
    CORRECTION_REJECTED = "correction_rejected"
    CORRECTION_ROLLED_BACK = "correction_rolled_back"
    BULK_UPLOAD_COMPLETE = "bulk_upload_complete"


class UserNotification(Base):
    """In-app notification for users.

    Used primarily for correction workflow notifications:
    approved, rejected, rolled back.
    """

    __tablename__ = "user_notifications"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        read = "read" if self.is_read else "unread"
        return f"<Notification [{self.type}] to {self.user_id} ({read})>"
