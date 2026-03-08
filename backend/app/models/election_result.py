"""Live election result models — scraped from result.election.gov.np."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, Integer, Float, DateTime, Index, Boolean
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ElectionCandidate(Base):
    """Per-constituency candidate with live vote count."""
    __tablename__ = "election_candidates_2082"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Location
    state_id: Mapped[int] = mapped_column(Integer, nullable=False)
    state_name: Mapped[str] = mapped_column(String(100), nullable=False)
    district_cd: Mapped[int] = mapped_column(Integer, nullable=False)
    district_name: Mapped[str] = mapped_column(String(100), nullable=False)
    constituency_no: Mapped[int] = mapped_column(Integer, nullable=False)

    # Election type: 'hor' (House of Representatives) or 'pa' (Provincial Assembly)
    election_type: Mapped[str] = mapped_column(String(10), nullable=False, default="hor")

    # Candidate
    ecn_candidate_id: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    gender: Mapped[Optional[str]] = mapped_column(String(20))
    age: Mapped[Optional[int]] = mapped_column(Integer)
    party_name: Mapped[str] = mapped_column(String(255), nullable=False)
    party_id: Mapped[Optional[int]] = mapped_column(Integer)
    symbol_name: Mapped[Optional[str]] = mapped_column(String(100))
    symbol_id: Mapped[Optional[int]] = mapped_column(Integer)

    # Vote data (updated by scraper)
    total_vote_received: Mapped[int] = mapped_column(Integer, default=0)
    casted_vote: Mapped[int] = mapped_column(Integer, default=0)
    total_voters: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[Optional[int]] = mapped_column(Integer)

    # Status
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )

    __table_args__ = (
        Index("idx_ec2082_district_const", "district_cd", "constituency_no", "election_type"),
        Index("idx_ec2082_party", "party_name"),
        Index("idx_ec2082_state", "state_id"),
        Index("idx_ec2082_ecn_id", "ecn_candidate_id", unique=True),
        Index("idx_ec2082_votes", "total_vote_received"),
    )


class ElectionPartySummary(Base):
    """Party-level seat summary (winners + leaders)."""
    __tablename__ = "election_party_summary_2082"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    election_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'hor' or 'pa'
    state_id: Mapped[Optional[int]] = mapped_column(Integer)  # NULL for national HOR

    party_name: Mapped[str] = mapped_column(String(255), nullable=False)
    party_id: Mapped[Optional[int]] = mapped_column(Integer)

    seats_won: Mapped[int] = mapped_column(Integer, default=0)
    seats_leading: Mapped[int] = mapped_column(Integer, default=0)
    total_votes: Mapped[int] = mapped_column(Integer, default=0)

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )

    __table_args__ = (
        Index("idx_eps2082_type_state", "election_type", "state_id"),
        Index("idx_eps2082_party", "party_name"),
    )


class ElectionScrapeLog(Base):
    """Track scraper runs for monitoring."""
    __tablename__ = "election_scrape_log"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    constituencies_scraped: Mapped[int] = mapped_column(Integer, default=0)
    candidates_updated: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
