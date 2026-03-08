"""Promise tracker model for manifesto promise tracking."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, DateTime, Integer, Float, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ManifestoPromise(Base, TimestampMixin):
    """Tracks manifesto promises and their fulfillment status."""

    __tablename__ = "manifesto_promises"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    promise_id: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # e.g. G1, AC2
    party: Mapped[str] = mapped_column(String(20), nullable=False, default="RSP")
    election_year: Mapped[str] = mapped_column(String(10), nullable=False, default="2082")
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    promise: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # manifesto reference
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_started")
    # not_started | in_progress | partially_fulfilled | fulfilled | stalled
    status_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI-generated explanation
    evidence_urls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of URLs
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_manifesto_promises_party_year", "party", "election_year"),
        Index("ix_manifesto_promises_status", "status"),
    )
