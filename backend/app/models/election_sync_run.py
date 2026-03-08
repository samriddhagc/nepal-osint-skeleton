"""Operational metadata for election candidate sync runs."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ElectionSyncRun(Base):
    """Stores import/link/reconcile run metadata for auditability."""

    __tablename__ = "election_sync_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False, default="manual_replay")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    years: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    import_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    link_stats: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    override_stats: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reconciliation: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

