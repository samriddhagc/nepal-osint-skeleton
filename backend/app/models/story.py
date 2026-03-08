"""Story model - news articles ingested from RSS feeds."""
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import String, Text, DateTime, Boolean, Numeric, Index, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.story_cluster import StoryCluster
    from app.models.story_embedding import StoryEmbedding
    from app.models.story_feature import StoryFeature


class Story(Base):
    """News story ingested from RSS feeds."""

    __tablename__ = "stories"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Deduplication
    external_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="SHA-256 hash of normalized URL for deduplication",
    )

    # Source
    source_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    source_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    categories: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Nepal relevance classification
    nepal_relevance: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        index=True,
        comment="NEPAL_DOMESTIC | NEPAL_NEIGHBOR | INTERNATIONAL",
    )
    relevance_score: Mapped[Optional[float]] = mapped_column(
        Numeric(4, 3),
        nullable=True,
    )
    relevance_triggers: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Keywords that triggered classification",
    )

    # Category and severity classification
    category: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="political | economic | security | disaster | social",
    )
    severity: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="critical | high | medium | low",
    )

    # Clustering
    cluster_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("story_clusters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cluster: Mapped[Optional["StoryCluster"]] = relationship(
        "StoryCluster",
        back_populates="stories",
    )

    # Embedding and features relationships
    embedding: Mapped[Optional["StoryEmbedding"]] = relationship(
        "StoryEmbedding",
        back_populates="story",
        uselist=False,
        cascade="all, delete-orphan",
    )
    features: Mapped[Optional["StoryFeature"]] = relationship(
        "StoryFeature",
        back_populates="story",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # Timestamps
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
    )

    # Metadata
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # AI Summary Cache
    ai_summary: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Cached AI-generated summary JSON",
    )
    ai_summary_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When AI summary was generated",
    )

    # Geographic classification (district/province)
    districts: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Array of district names extracted from title/content",
    )
    provinces: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Array of province names derived from districts",
    )

    __table_args__ = (
        Index("idx_stories_source_published", "source_id", "published_at"),
        Index("idx_stories_relevance_published", "nepal_relevance", "published_at"),
        Index("idx_stories_created", "created_at"),
        Index("idx_stories_category_published", "category", "published_at"),
        Index("idx_stories_severity_published", "severity", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<Story {self.id}: {self.title[:50]}...>"
