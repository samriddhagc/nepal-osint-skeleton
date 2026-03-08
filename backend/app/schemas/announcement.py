"""Pydantic schemas for government announcements."""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class AttachmentSchema(BaseModel):
    """Attachment file schema."""
    name: str
    url: str


class AnnouncementResponse(BaseModel):
    """Single announcement response."""
    id: str
    external_id: str
    source: str
    source_name: str
    title: str
    url: str
    category: str
    date_bs: Optional[str] = None
    date_ad: Optional[datetime] = None
    attachments: List[AttachmentSchema] = Field(default_factory=list)
    has_attachments: bool = False
    content: Optional[str] = None
    is_read: bool = False
    is_important: bool = False
    published_at: Optional[datetime] = None
    fetched_at: datetime
    created_at: datetime


class AnnouncementListResponse(BaseModel):
    """List of announcements with pagination."""
    announcements: List[AnnouncementResponse]
    total: int
    page: int = 1
    per_page: int = 20
    has_more: bool = False


class AnnouncementSummary(BaseModel):
    """Summary for dashboard widget."""
    total: int
    unread: int
    by_source: dict[str, int]
    by_category: dict[str, int]
    latest: List[AnnouncementResponse]


class IngestionStats(BaseModel):
    """Stats from announcement ingestion."""
    source: str
    fetched: int
    new: int
    updated: int
    errors: List[str] = Field(default_factory=list)


class SourceInfo(BaseModel):
    """Information about a government source."""
    source: str
    name: str
    name_ne: Optional[str] = None
    categories: List[str]
    total_announcements: int
    last_fetched: Optional[datetime] = None
