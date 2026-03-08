"""Company registration models (OCR - Office of Company Registrar)."""
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import String, Text, Integer, Float, Boolean, Date, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.political_entity import PoliticalEntity
    from app.models.user import User


class CompanyRegistration(Base):
    """Company registered with Nepal's Office of Company Registrar (OCR)."""

    __tablename__ = "company_registrations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # External ID (hash of reg_number + name_english + reg_date for dedup)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Core fields from OCR
    registration_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name_nepali: Mapped[Optional[str]] = mapped_column(Text)
    name_english: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    registration_date_bs: Mapped[Optional[str]] = mapped_column(String(20))  # BS date e.g. "2041-01-29"
    registration_date_ad: Mapped[Optional[date]] = mapped_column(Date)  # Converted AD date
    company_type: Mapped[Optional[str]] = mapped_column(String(500))  # Full Nepali type string
    company_type_category: Mapped[Optional[str]] = mapped_column(String(50), index=True)  # Private/Public/Foreign/Non-profit
    company_address: Mapped[Optional[str]] = mapped_column(String(500))
    district: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    province: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    last_communication_bs: Mapped[Optional[str]] = mapped_column(String(20))  # Recent Communication With OCR

    # CAMIS enrichment fields
    camis_company_id: Mapped[Optional[int]] = mapped_column(Integer)  # CAMIS internal ID
    cro_company_id: Mapped[Optional[str]] = mapped_column(String(50))  # CRO legacy ID
    pan: Mapped[Optional[str]] = mapped_column(String(20), index=True)  # Company PAN number
    camis_enriched: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    camis_enriched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # IRD enrichment fields
    ird_enriched: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ird_enriched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Metadata
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Timestamps
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    directors: Mapped[list["CompanyDirector"]] = relationship(
        "CompanyDirector", back_populates="company", lazy="selectin"
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "external_id": self.external_id,
            "registration_number": self.registration_number,
            "name_nepali": self.name_nepali,
            "name_english": self.name_english,
            "registration_date_bs": self.registration_date_bs,
            "registration_date_ad": self.registration_date_ad.isoformat() if self.registration_date_ad else None,
            "company_type": self.company_type,
            "company_type_category": self.company_type_category,
            "company_address": self.company_address,
            "district": self.district,
            "province": self.province,
            "last_communication_bs": self.last_communication_bs,
            "pan": self.pan,
            "camis_company_id": self.camis_company_id,
            "cro_company_id": self.cro_company_id,
            "camis_enriched": self.camis_enriched,
            "camis_enriched_at": self.camis_enriched_at.isoformat() if self.camis_enriched_at else None,
            "ird_enriched": self.ird_enriched,
            "ird_enriched_at": self.ird_enriched_at.isoformat() if self.ird_enriched_at else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CompanyDirector(Base):
    """Director/officer of a company, sourced from multiple data pipelines."""

    __tablename__ = "company_directors"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Nullable FK -- director mentions from news may not yet be linked to a company
    company_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("company_registrations.id", ondelete="SET NULL"),
        index=True,
    )

    # Identity
    name_en: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    name_np: Mapped[Optional[str]] = mapped_column(String(300))
    role: Mapped[Optional[str]] = mapped_column(String(100))  # Director, MD, Chairman, CEO
    company_name_hint: Mapped[Optional[str]] = mapped_column(String(500))  # For unlinked records

    # Provenance
    source: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # news_ner, sebon, nrb, bolpatra, camis, manual
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    # Additional identity fields
    pan: Mapped[Optional[str]] = mapped_column(String(20))
    citizenship_no: Mapped[Optional[str]] = mapped_column(String(30))

    # Linked PoliticalEntity (canonical hub)
    linked_entity_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("political_entities.id", ondelete="SET NULL"),
        index=True,
    )
    entity_link_confidence: Mapped[Optional[float]] = mapped_column(Float)

    # Tenure
    appointed_date: Mapped[Optional[date]] = mapped_column(Date)
    resigned_date: Mapped[Optional[date]] = mapped_column(Date)

    # Raw payload from source
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Timestamps
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company: Mapped[Optional["CompanyRegistration"]] = relationship(
        "CompanyRegistration", back_populates="directors"
    )
    political_entity: Mapped[Optional["PoliticalEntity"]] = relationship(
        "PoliticalEntity",
        back_populates="company_directorships",
        foreign_keys=[linked_entity_id],
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "company_id": str(self.company_id) if self.company_id else None,
            "name_en": self.name_en,
            "name_np": self.name_np,
            "role": self.role,
            "company_name_hint": self.company_name_hint,
            "source": self.source,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "pan": self.pan,
            "citizenship_no": self.citizenship_no,
            "appointed_date": self.appointed_date.isoformat() if self.appointed_date else None,
            "resigned_date": self.resigned_date.isoformat() if self.resigned_date else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class IRDEnrichment(Base):
    """IRD PAN search enrichment data with privacy-preserving phone hashing."""

    __tablename__ = "ird_enrichments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    company_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("company_registrations.id", ondelete="SET NULL"),
        index=True,
    )

    # PAN (public tax identifier)
    pan: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)

    # Business details (public, non-sensitive)
    taxpayer_name_en: Mapped[Optional[str]] = mapped_column(String(500))
    taxpayer_name_np: Mapped[Optional[str]] = mapped_column(String(500))
    account_type: Mapped[Optional[str]] = mapped_column(String(10))
    account_status: Mapped[Optional[str]] = mapped_column(String(200))
    registration_date_bs: Mapped[Optional[str]] = mapped_column(String(50))
    filing_period: Mapped[Optional[str]] = mapped_column(String(5))
    tax_office: Mapped[Optional[str]] = mapped_column(String(300))
    is_personal: Mapped[Optional[str]] = mapped_column(String(5))

    # Location (coarse only)
    ward_no: Mapped[Optional[str]] = mapped_column(String(10))
    vdc_municipality: Mapped[Optional[str]] = mapped_column(String(200))

    # Privacy-preserving hashed fields (HMAC-SHA256)
    phone_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    mobile_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    # Tax clearance
    latest_tax_clearance_fy: Mapped[Optional[str]] = mapped_column(String(20))
    tax_clearance_verified: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Sanitised raw response (PII stripped)
    raw_data_sanitised: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Timestamps
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company: Mapped[Optional["CompanyRegistration"]] = relationship(
        "CompanyRegistration", foreign_keys=[company_id],
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "company_id": str(self.company_id) if self.company_id else None,
            "pan": self.pan,
            "taxpayer_name_en": self.taxpayer_name_en,
            "taxpayer_name_np": self.taxpayer_name_np,
            "account_type": self.account_type,
            "account_status": self.account_status,
            "registration_date_bs": self.registration_date_bs,
            "tax_office": self.tax_office,
            "is_personal": self.is_personal,
            "ward_no": self.ward_no,
            "vdc_municipality": self.vdc_municipality,
            "phone_hash": self.phone_hash,
            "mobile_hash": self.mobile_hash,
            "latest_tax_clearance_fy": self.latest_tax_clearance_fy,
            "tax_clearance_verified": self.tax_clearance_verified,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AnalystPhoneClusterGroup(Base):
    """Analyst-authored graph groups over phone/mobile clusters."""

    __tablename__ = "analyst_phone_cluster_groups"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    main_cluster_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    clusters: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="'[]'::jsonb",
    )
    edges: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="'[]'::jsonb",
    )
    created_by_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    updated_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    created_by: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by_id],
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[updated_by_id],
    )

    __table_args__ = (
        Index("ix_analyst_phone_cluster_groups_updated_at", "updated_at"),
    )
