"""Government procurement contract models (Bolpatra e-GP)."""
from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, Float, Date, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GovtContract(Base):
    """Government contract from bolpatra.gov.np e-GP portal."""

    __tablename__ = "govt_contracts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # External ID (hash of ifb_number for deduplication)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Core fields from bolpatra
    ifb_number: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(Text, nullable=False)
    procuring_entity: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    procurement_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    contract_award_date: Mapped[Optional[date]] = mapped_column(Date)
    contract_amount_npr: Mapped[Optional[float]] = mapped_column(Float)
    contractor_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)

    # Enrichment
    district: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    province: Mapped[Optional[int]] = mapped_column()
    fiscal_year_bs: Mapped[Optional[str]] = mapped_column(String(20), index=True)

    # Metadata
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Timestamps
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite indexes for common queries
    __table_args__ = (
        Index("ix_govt_contracts_award_date", "contract_award_date"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "external_id": self.external_id,
            "ifb_number": self.ifb_number,
            "project_name": self.project_name,
            "procuring_entity": self.procuring_entity,
            "procurement_type": self.procurement_type,
            "contract_award_date": self.contract_award_date.isoformat() if self.contract_award_date else None,
            "contract_amount_npr": self.contract_amount_npr,
            "contractor_name": self.contractor_name,
            "district": self.district,
            "province": self.province,
            "fiscal_year_bs": self.fiscal_year_bs,
            "source_url": self.source_url,
            "raw_data": self.raw_data,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
