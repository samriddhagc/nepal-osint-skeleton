"""Election database models for Nepal OSINT v5.

Models for storing election data from Election Commission Nepal (ECN).
Supports parliamentary elections (2074, 2079, 2082 BS) with constituencies,
candidates, and user watchlists.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    String, Text, Boolean, DateTime, Integer, Float, ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import JSON, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.political_entity import PoliticalEntity


class ElectionType(str, Enum):
    """Type of election."""
    PARLIAMENTARY = "parliamentary"
    PROVINCIAL = "provincial"
    LOCAL = "local"
    BY_ELECTION = "by_election"


class ElectionStatus(str, Enum):
    """Status of an election."""
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    COMPLETED = "completed"


class ConstituencyStatus(str, Enum):
    """Status of constituency results."""
    PENDING = "pending"
    COUNTING = "counting"
    DECLARED = "declared"


class AlertLevel(str, Enum):
    """Alert level for watchlist items."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Election(Base, TimestampMixin):
    """Election metadata for a specific election year.

    Each row represents one election event (e.g., 2079 Parliamentary Election).
    """
    __tablename__ = "elections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Election identification
    year_bs: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)  # Bikram Sambat year (2074, 2079, 2082)
    year_ad: Mapped[int] = mapped_column(Integer, nullable=False)  # Gregorian year (2017, 2022, 2025)
    election_type: Mapped[str] = mapped_column(String(50), nullable=False, default=ElectionType.PARLIAMENTARY.value)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ElectionStatus.COMPLETED.value)

    # National statistics
    total_constituencies: Mapped[int] = mapped_column(Integer, default=165)
    total_registered_voters: Mapped[Optional[int]] = mapped_column(Integer)
    total_votes_cast: Mapped[Optional[int]] = mapped_column(Integer)
    turnout_pct: Mapped[Optional[float]] = mapped_column(Float)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    constituencies: Mapped[list["Constituency"]] = relationship(
        "Constituency", back_populates="election", cascade="all, delete-orphan"
    )
    candidates: Mapped[list["Candidate"]] = relationship(
        "Candidate", back_populates="election", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_elections_year_bs", "year_bs"),
        Index("idx_elections_status", "status"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "year_bs": self.year_bs,
            "year_ad": self.year_ad,
            "election_type": self.election_type,
            "status": self.status,
            "total_constituencies": self.total_constituencies,
            "total_registered_voters": self.total_registered_voters,
            "total_votes_cast": self.total_votes_cast,
            "turnout_pct": self.turnout_pct,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Constituency(Base, TimestampMixin):
    """Electoral constituency (प्रतिनिधि सभा निर्वाचन क्षेत्र).

    Nepal has 165 constituencies across 77 districts and 7 provinces.
    Each row represents one constituency's data for a specific election.
    """
    __tablename__ = "constituencies"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    election_id: Mapped[UUID] = mapped_column(ForeignKey("elections.id", ondelete="CASCADE"), nullable=False)

    # Constituency identification
    constituency_code: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "kathmandu-1", "achham-2"
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)  # English name
    name_ne: Mapped[Optional[str]] = mapped_column(String(255))  # Nepali name

    # Geographic hierarchy
    district: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[str] = mapped_column(String(100), nullable=False)
    province_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-7

    # Result status
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ConstituencyStatus.PENDING.value)

    # Vote statistics
    total_registered_voters: Mapped[Optional[int]] = mapped_column(Integer)
    total_votes_cast: Mapped[Optional[int]] = mapped_column(Integer)
    turnout_pct: Mapped[Optional[float]] = mapped_column(Float)
    valid_votes: Mapped[Optional[int]] = mapped_column(Integer)
    invalid_votes: Mapped[Optional[int]] = mapped_column(Integer)

    # Winner reference (set after declaration)
    winner_candidate_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"))
    winner_party: Mapped[Optional[str]] = mapped_column(String(255))  # Denormalized for faster queries
    winner_votes: Mapped[Optional[int]] = mapped_column(Integer)
    winner_margin: Mapped[Optional[int]] = mapped_column(Integer)  # Margin over runner-up

    # Relationships
    election: Mapped["Election"] = relationship("Election", back_populates="constituencies")
    candidates: Mapped[list["Candidate"]] = relationship(
        "Candidate", back_populates="constituency",
        foreign_keys="Candidate.constituency_id",
        cascade="all, delete-orphan"
    )
    watchlist_items: Mapped[list["UserConstituencyWatchlist"]] = relationship(
        "UserConstituencyWatchlist", back_populates="constituency", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_constituencies_election_code", "election_id", "constituency_code", unique=True),
        Index("idx_constituencies_election_district", "election_id", "district"),
        Index("idx_constituencies_election_province", "election_id", "province_id"),
        Index("idx_constituencies_status", "status"),
        Index("idx_constituencies_winner_party", "winner_party"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "election_id": str(self.election_id),
            "constituency_code": self.constituency_code,
            "name_en": self.name_en,
            "name_ne": self.name_ne,
            "district": self.district,
            "province": self.province,
            "province_id": self.province_id,
            "status": self.status,
            "total_registered_voters": self.total_registered_voters,
            "total_votes_cast": self.total_votes_cast,
            "turnout_pct": self.turnout_pct,
            "valid_votes": self.valid_votes,
            "invalid_votes": self.invalid_votes,
            "winner_party": self.winner_party,
            "winner_votes": self.winner_votes,
            "winner_margin": self.winner_margin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Candidate(Base, TimestampMixin):
    """Election candidate participating in a constituency.

    Stores candidate details and vote results from ECN data.
    """
    __tablename__ = "candidates"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    election_id: Mapped[UUID] = mapped_column(ForeignKey("elections.id", ondelete="CASCADE"), nullable=False)
    constituency_id: Mapped[UUID] = mapped_column(ForeignKey("constituencies.id", ondelete="CASCADE"), nullable=False)

    # ECN identification
    external_id: Mapped[str] = mapped_column(String(50), nullable=False)  # ECN candidate ID (e.g., "340695")

    # Names
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ne: Mapped[Optional[str]] = mapped_column(String(255))

    # Party affiliation
    party: Mapped[str] = mapped_column(String(255), nullable=False)
    party_ne: Mapped[Optional[str]] = mapped_column(String(255))

    # Vote results
    votes: Mapped[int] = mapped_column(Integer, default=0)
    vote_pct: Mapped[float] = mapped_column(Float, default=0.0)
    rank: Mapped[int] = mapped_column(Integer, default=0)  # Position (1 = winner)
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)

    # Candidate profile
    photo_url: Mapped[Optional[str]] = mapped_column(String(500))  # ECN photo URL
    age: Mapped[Optional[int]] = mapped_column(Integer)
    gender: Mapped[Optional[str]] = mapped_column(String(20))  # "पुरुष" / "महिला"
    education: Mapped[Optional[str]] = mapped_column(String(255))
    education_institution: Mapped[Optional[str]] = mapped_column(String(255))

    # Enhanced profile fields (for search and biography)
    name_en_roman: Mapped[Optional[str]] = mapped_column(String(255))  # Romanized English transliteration
    aliases: Mapped[Optional[list]] = mapped_column(JSON)  # Alternative name spellings for search
    biography: Mapped[Optional[str]] = mapped_column(Text)  # Short biography
    biography_source: Mapped[Optional[str]] = mapped_column(String(500))  # Source URL for biography
    is_notable: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)  # Has significant public profile
    previous_positions: Mapped[Optional[dict]] = mapped_column(JSON)  # Previous elected positions

    # Linked PoliticalEntity (canonical hub)
    linked_entity_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("political_entities.id", ondelete="SET NULL"),
        index=True,
    )
    entity_link_confidence: Mapped[Optional[float]] = mapped_column(Float)

    # Relationships
    election: Mapped["Election"] = relationship("Election", back_populates="candidates")
    constituency: Mapped["Constituency"] = relationship(
        "Constituency", back_populates="candidates",
        foreign_keys=[constituency_id]
    )
    political_entity: Mapped[Optional["PoliticalEntity"]] = relationship(
        "PoliticalEntity",
        back_populates="candidates",
        foreign_keys=[linked_entity_id],
    )

    __table_args__ = (
        Index("idx_candidates_constituency", "constituency_id"),
        Index("idx_candidates_election_party", "election_id", "party"),
        Index("idx_candidates_external_id", "election_id", "external_id", unique=True),
        Index("idx_candidates_is_winner", "is_winner"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "election_id": str(self.election_id),
            "constituency_id": str(self.constituency_id),
            "external_id": self.external_id,
            "name_en": self.name_en,
            "name_ne": self.name_ne,
            "name_en_roman": self.name_en_roman,
            "aliases": self.aliases,
            "party": self.party,
            "party_ne": self.party_ne,
            "votes": self.votes,
            "vote_pct": self.vote_pct,
            "rank": self.rank,
            "is_winner": self.is_winner,
            "photo_url": self.photo_url,
            "age": self.age,
            "gender": self.gender,
            "education": self.education,
            "education_institution": self.education_institution,
            "biography": self.biography,
            "biography_source": self.biography_source,
            "is_notable": self.is_notable,
            "previous_positions": self.previous_positions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserConstituencyWatchlist(Base, TimestampMixin):
    """User watchlist for tracking specific constituencies.

    Allows users to track constituencies they're interested in monitoring
    during elections.
    """
    __tablename__ = "user_constituency_watchlist"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # User identification (session-based for now, can integrate with auth later)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # Constituency being watched
    constituency_id: Mapped[UUID] = mapped_column(ForeignKey("constituencies.id", ondelete="CASCADE"), nullable=False)

    # Watchlist settings
    alert_level: Mapped[str] = mapped_column(String(20), default=AlertLevel.MEDIUM.value)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    constituency: Mapped["Constituency"] = relationship("Constituency", back_populates="watchlist_items")

    __table_args__ = (
        Index("idx_watchlist_user", "user_id"),
        Index("idx_watchlist_user_constituency", "user_id", "constituency_id", unique=True),
        Index("idx_watchlist_active", "is_active"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "constituency_id": str(self.constituency_id),
            "alert_level": self.alert_level,
            "notes": self.notes,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
