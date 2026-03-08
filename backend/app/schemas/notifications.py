"""Pydantic schemas for notification endpoints."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    """Single notification."""
    id: str
    type: str
    title: str
    message: Optional[str] = None
    data: Optional[dict] = None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    """List of notifications with unread count."""
    items: list[NotificationResponse]
    unread_count: int = 0


class MarkReadResponse(BaseModel):
    """Response after marking notification(s) as read."""
    success: bool = True
    marked_read: int = 0
