"""Persistent linkage between procurement contractors and OCR companies."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ProcurementCompanyLink(Base):
    """One best-match linkage row per distinct procurement contractor name."""

    __tablename__ = "procurement_company_links"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    contractor_name: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    contractor_name_normalized: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    contractor_name_compact: Mapped[str] = mapped_column(String(500), nullable=False, index=True)

    company_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("company_registrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    match_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unmatched", server_default="unmatched")
    match_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    details: Mapped[Optional[dict]] = mapped_column(JSONB)

    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("CompanyRegistration", foreign_keys=[company_id])

    __table_args__ = (
        Index("idx_proc_link_status", "match_status"),
    )
