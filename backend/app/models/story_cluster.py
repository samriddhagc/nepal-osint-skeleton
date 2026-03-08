"""StoryCluster model - groups related stories together."""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import String, Text, DateTime, Integer, Boolean, ForeignKey, Float, func, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.story import Story
    from app.models.user import User


class StoryCluster(Base):
    """Cluster of related news stories."""

    __tablename__ = "story_clusters"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Representative content
    headline: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Representative headline (most recent story)",
    )
    summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Aggregated summary of cluster",
    )

    # Classification
    category: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="Dominant category: political | economic | security | disaster | social",
    )
    severity: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="Highest severity: critical | high | medium | low",
    )

    # Counts
    story_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    source_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    # ============================================================
    # Palantir-Grade Corroboration Tracking
    # ============================================================
    unique_sources: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String),
        nullable=True,
        comment="List of unique source IDs backing this story",
    )
    diversity_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        default=0.0,
        comment="Simpson Diversity Index (0-1, higher = more diverse sources)",
    )
    confirmation_chain: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Chronological chain of source confirmations [{source, timestamp, snippet}]",
    )
    confidence_level: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        default="single_source",
        comment="single_source | corroborated | well_corroborated | highly_corroborated",
    )

    # ============================================================
    # Intelligence Scoring (Palantir-Grade)
    # ============================================================
    intelligence_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Weighted intelligence score (0-100)",
    )
    actionability: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="immediate | monitor | archive",
    )

    # ============================================================
    # Cross-Lingual Tracking
    # ============================================================
    languages: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String),
        nullable=True,
        comment="Languages present in cluster stories",
    )
    cross_lingual_match: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether cluster contains stories in multiple languages",
    )

    # Timestamps
    first_published: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Publication time of earliest story in cluster",
    )
    last_updated: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Publication time of latest story in cluster",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
    )

    # Analysis fields (populated by Haiku)
    bluf: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Bottom Line Up Front summary",
    )
    analysis: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full analysis JSON from Haiku",
    )
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    analysis_model: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Model used for analysis (e.g., claude-3-5-haiku)",
    )

    # ============================================================
    # Analyst Workflow / Publishing (Human-in-the-loop)
    # ============================================================
    workflow_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unreviewed",
        server_default="unreviewed",
        index=True,
        comment="unreviewed|monitoring|verified|published|rejected",
    )

    # Analyst overrides (do NOT get overwritten by auto-clustering)
    analyst_headline: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Analyst-verified headline (customer-facing if published)",
    )
    analyst_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Analyst-verified summary (customer-facing if published)",
    )
    analyst_category: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Analyst category override",
    )
    analyst_severity: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Analyst severity override",
    )
    analyst_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Internal analyst notes (not customer-facing)",
    )

    # Verification metadata
    verified_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    verified_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[verified_by_id],
    )

    # Publishing metadata
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
        comment="Whether this cluster/event is visible to consumer customers",
    )
    published_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    customer_brief: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Customer-facing brief (overrides summary when published)",
    )
    published_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[published_by_id],
    )

    # Relationships
    stories: Mapped[list["Story"]] = relationship(
        "Story",
        back_populates="cluster",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_clusters_category_severity", "category", "severity"),
        Index("idx_clusters_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<StoryCluster {self.id}: {self.headline[:50]}... ({self.story_count} stories)>"
