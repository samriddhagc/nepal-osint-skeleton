"""Ministerial Position database model for executive branch tracking.

Tracks cabinet positions (Ministers, Deputy PM, State Ministers) for political figures.
This complements parliamentary data to give a complete picture of a candidate's
political experience - both legislative AND executive.
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    String, Text, Boolean, DateTime, Integer, Float, Date, ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.political_entity import PoliticalEntity


class PositionType(str, Enum):
    """Type of ministerial position."""
    PRIME_MINISTER = "prime_minister"
    DEPUTY_PM = "deputy_pm"
    MINISTER = "minister"
    STATE_MINISTER = "state_minister"
    ASSISTANT_MINISTER = "assistant_minister"


class MinisterialPosition(Base, TimestampMixin):
    """Cabinet/Executive position held by a political figure.

    Tracks the full history of ministerial appointments including:
    - Prime Ministers and their terms
    - Deputy Prime Ministers
    - Cabinet Ministers
    - State Ministers (Junior Ministers)

    This data is sourced from OPMCM (opmcm.gov.np) and news archives.
    """
    __tablename__ = "ministerial_positions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Person identification - link to candidates if available
    # We use name matching since ministers may not have run in elections
    person_name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    person_name_ne: Mapped[Optional[str]] = mapped_column(String(255))

    # Optional link to election candidate (for lookup)
    linked_candidate_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL")
    )

    # Optional link to MP performance record
    linked_mp_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("mp_performance.id", ondelete="SET NULL")
    )

    # Position details
    position_type: Mapped[str] = mapped_column(String(50), nullable=False)  # prime_minister, minister, etc.
    ministry: Mapped[Optional[str]] = mapped_column(String(255))  # e.g., "Home Affairs", "Finance"
    ministry_ne: Mapped[Optional[str]] = mapped_column(String(255))  # e.g., "गृह मन्त्रालय"
    position_title: Mapped[Optional[str]] = mapped_column(String(255))  # Full title if different

    # Tenure
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date)  # NULL if still serving
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)

    # Context
    government_name: Mapped[Optional[str]] = mapped_column(String(255))  # e.g., "Pushpa Kamal Dahal Government"
    prime_minister: Mapped[Optional[str]] = mapped_column(String(255))  # PM who appointed them
    appointment_order: Mapped[Optional[int]] = mapped_column(Integer)  # Cabinet rank/seniority

    # Party at time of appointment (may differ from current)
    party_at_appointment: Mapped[Optional[str]] = mapped_column(String(255))

    # Linked PoliticalEntity (canonical hub)
    linked_entity_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("political_entities.id", ondelete="SET NULL"),
        index=True,
    )
    entity_link_confidence: Mapped[Optional[float]] = mapped_column(Float)

    # Notes for additional context
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Metadata
    source: Mapped[Optional[str]] = mapped_column(String(100))  # 'opmcm', 'news', 'manual'
    source_url: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    political_entity: Mapped[Optional["PoliticalEntity"]] = relationship(
        "PoliticalEntity",
        back_populates="ministerial_positions",
        foreign_keys=[linked_entity_id],
    )

    __table_args__ = (
        Index("idx_ministerial_positions_person", "person_name_en"),
        Index("idx_ministerial_positions_candidate", "linked_candidate_id"),
        Index("idx_ministerial_positions_mp", "linked_mp_id"),
        Index("idx_ministerial_positions_ministry", "ministry"),
        Index("idx_ministerial_positions_type", "position_type"),
        Index("idx_ministerial_positions_current", "is_current"),
        Index("idx_ministerial_positions_dates", "start_date", "end_date"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "person_name_en": self.person_name_en,
            "person_name_ne": self.person_name_ne,
            "linked_candidate_id": str(self.linked_candidate_id) if self.linked_candidate_id else None,
            "linked_mp_id": str(self.linked_mp_id) if self.linked_mp_id else None,
            "position_type": self.position_type,
            "ministry": self.ministry,
            "ministry_ne": self.ministry_ne,
            "position_title": self.position_title,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_current": self.is_current,
            "government_name": self.government_name,
            "prime_minister": self.prime_minister,
            "party_at_appointment": self.party_at_appointment,
            "notes": self.notes,
        }

    @property
    def duration_days(self) -> Optional[int]:
        """Calculate duration of tenure in days."""
        if not self.start_date:
            return None
        end = self.end_date or date.today()
        return (end - self.start_date).days

    @property
    def formatted_position(self) -> str:
        """Get formatted position name."""
        if self.position_type == PositionType.PRIME_MINISTER.value:
            return "Prime Minister"
        elif self.position_type == PositionType.DEPUTY_PM.value:
            return f"Deputy Prime Minister{' and Minister of ' + self.ministry if self.ministry else ''}"
        elif self.position_type == PositionType.MINISTER.value:
            return f"Minister of {self.ministry}" if self.ministry else "Cabinet Minister"
        elif self.position_type == PositionType.STATE_MINISTER.value:
            return f"State Minister of {self.ministry}" if self.ministry else "State Minister"
        return self.position_title or "Government Position"
