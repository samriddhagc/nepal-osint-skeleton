"""Story Pydantic schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, HttpUrl


class StoryBase(BaseModel):
    """Base story fields."""
    title: str
    url: str
    summary: Optional[str] = None
    content: Optional[str] = None
    language: str = "en"
    author: Optional[str] = None
    categories: Optional[list[str]] = None


class StoryCreate(StoryBase):
    """Schema for creating a story."""
    source_id: str
    source_name: Optional[str] = None
    external_id: str
    published_at: Optional[datetime] = None
    nepal_relevance: Optional[str] = None
    relevance_score: Optional[float] = None
    relevance_triggers: Optional[list[str]] = None
    category: Optional[str] = None
    severity: Optional[str] = None


class StoryResponse(BaseModel):
    """Story response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str
    source_id: str
    source_name: Optional[str] = None
    title: str
    url: str
    summary: Optional[str] = None
    language: str
    author: Optional[str] = None
    categories: Optional[list[str]] = None
    nepal_relevance: Optional[str] = None
    relevance_score: Optional[float] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    cluster_id: Optional[UUID] = None
    published_at: Optional[datetime] = None
    created_at: datetime


class StoryListResponse(BaseModel):
    """Paginated list of stories."""
    items: list[StoryResponse]
    total: int
    page: int
    page_size: int
