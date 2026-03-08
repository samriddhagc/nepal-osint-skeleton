"""Pydantic schemas for Parliament API.

Schemas for MP Performance Index data including:
- MP profiles with performance scores
- Bills and legislation
- Committee memberships
- Parliamentary questions
- Attendance records
"""
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


# ============== MP Performance Schemas ==============

class MPPerformanceBase(BaseModel):
    """Base MP performance data."""
    mp_id: str
    name_en: str
    name_ne: Optional[str] = None
    party: Optional[str] = None
    constituency: Optional[str] = None
    province_id: Optional[int] = None
    election_type: Optional[str] = None  # 'fptp' or 'pr'
    chamber: Optional[str] = None  # 'hor' or 'na'
    term: Optional[str] = None
    photo_url: Optional[str] = None
    is_minister: bool = False
    ministry_portfolio: Optional[str] = None


class MPPerformanceScores(BaseModel):
    """MP performance score breakdown."""
    # Legislative (30%)
    bills_introduced: int = 0
    bills_passed: int = 0
    legislative_score: float = 0.0
    legislative_percentile: Optional[int] = None

    # Participation (25%)
    sessions_total: int = 0
    sessions_attended: int = 0
    session_attendance_pct: Optional[float] = None
    participation_score: float = 0.0
    participation_percentile: Optional[int] = None

    # Accountability (25%)
    questions_asked: int = 0
    questions_answered: int = 0
    accountability_score: float = 0.0
    accountability_percentile: Optional[int] = None

    # Committee Work (20%)
    committee_memberships: int = 0
    committee_leadership_roles: int = 0
    committee_attendance_pct: Optional[float] = None
    committee_score: float = 0.0
    committee_percentile: Optional[int] = None

    # Composite
    performance_score: float = 0.0
    performance_percentile: Optional[int] = None
    performance_tier: Optional[str] = None  # 'top10', 'above_avg', etc.

    # Peer ranking
    peer_group: Optional[str] = None
    peer_rank: Optional[int] = None
    peer_total: Optional[int] = None


class MPPerformanceResponse(MPPerformanceBase, MPPerformanceScores):
    """Complete MP performance response."""
    id: str
    linked_candidate_id: Optional[str] = None
    link_confidence: Optional[float] = None
    is_current_member: bool = True
    score_updated_at: Optional[datetime] = None


class MPPerformanceSummary(BaseModel):
    """Condensed MP performance for dossier integration."""
    id: str
    name_en: str
    name_ne: Optional[str] = None
    party: Optional[str] = None
    chamber: Optional[str] = None

    # Key scores
    performance_score: float = 0.0
    performance_percentile: Optional[int] = None
    performance_tier: Optional[str] = None

    # Quick breakdown
    legislative_score: float = 0.0
    legislative_percentile: Optional[int] = None
    participation_score: float = 0.0
    participation_percentile: Optional[int] = None
    accountability_score: float = 0.0
    accountability_percentile: Optional[int] = None
    committee_score: float = 0.0
    committee_percentile: Optional[int] = None

    # Key metrics
    bills_introduced: int = 0
    bills_passed: int = 0
    session_attendance_pct: Optional[float] = None
    questions_asked: int = 0
    committee_memberships: int = 0
    committee_leadership_roles: int = 0

    # Peer comparison
    peer_group: Optional[str] = None
    peer_rank: Optional[int] = None
    peer_total: Optional[int] = None

    # Recent activity (for frontend display)
    recent_bills: List["BillSummary"] = Field(default_factory=list)


class MPPerformanceListResponse(BaseModel):
    """Paginated list of MPs with performance data."""
    items: List[MPPerformanceResponse]
    total: int
    page: int = 1
    per_page: int = 50
    has_more: bool = False


# ============== Bill Schemas ==============

class BillResponse(BaseModel):
    """Parliament bill response."""
    id: str
    external_id: Optional[str] = None
    title_en: str
    title_ne: Optional[str] = None
    bill_type: Optional[str] = None  # 'government', 'private_member', 'money', 'amendment'
    status: Optional[str] = None  # 'registered', 'first_reading', etc.
    presented_date: Optional[date] = None
    passed_date: Optional[date] = None
    presenting_mp_id: Optional[str] = None
    presenting_mp_name: Optional[str] = None
    ministry: Optional[str] = None
    chamber: Optional[str] = None
    term: Optional[str] = None
    pdf_url: Optional[str] = None


class BillSummary(BaseModel):
    """Bill summary for listing."""
    id: str
    title_en: str
    status: Optional[str] = None
    presented_date: Optional[date] = None
    passed_date: Optional[date] = None


class BillListResponse(BaseModel):
    """Paginated list of bills."""
    items: List[BillResponse]
    total: int
    page: int = 1
    per_page: int = 50
    has_more: bool = False


# ============== Committee Schemas ==============

class CommitteeMemberResponse(BaseModel):
    """Committee member with role."""
    mp_id: str
    mp_name: str
    role: str  # 'chair', 'vice_chair', 'member'
    attendance_pct: Optional[float] = None


class CommitteeResponse(BaseModel):
    """Parliament committee response."""
    id: str
    external_id: Optional[str] = None
    name_en: str
    name_ne: Optional[str] = None
    committee_type: Optional[str] = None
    chamber: Optional[str] = None
    term: Optional[str] = None
    is_active: bool = True
    total_meetings: int = 0
    members: List[CommitteeMemberResponse] = Field(default_factory=list)


class CommitteeSummary(BaseModel):
    """Committee summary for MP profile."""
    id: str
    name_en: str
    role: str
    attendance_pct: Optional[float] = None
    meetings_attended: int = 0
    meetings_total: int = 0


class CommitteeListResponse(BaseModel):
    """List of committees."""
    items: List[CommitteeResponse]
    total: int


# ============== Question Schemas ==============

class QuestionResponse(BaseModel):
    """Parliamentary question response."""
    id: str
    external_id: Optional[str] = None
    asker_mp_id: Optional[str] = None
    asker_mp_name: Optional[str] = None
    question_type: Optional[str] = None  # 'zero_hour', 'special_hour', etc.
    question_text: Optional[str] = None
    question_date: Optional[date] = None
    ministry_addressed: Optional[str] = None
    answered: bool = False
    answerer_mp_id: Optional[str] = None
    answerer_mp_name: Optional[str] = None
    answer_date: Optional[date] = None


class QuestionListResponse(BaseModel):
    """List of parliamentary questions."""
    items: List[QuestionResponse]
    total: int


# ============== Ranking Schemas ==============

class MPRankingEntry(BaseModel):
    """Single entry in MP rankings."""
    id: str
    name_en: str
    name_ne: Optional[str] = None
    party: Optional[str] = None
    constituency: Optional[str] = None
    photo_url: Optional[str] = None
    score: float
    percentile: Optional[int] = None
    rank: int


class MPRankingResponse(BaseModel):
    """MP rankings response."""
    category: str  # 'overall', 'legislative', 'participation', 'accountability', 'committee'
    peer_group: Optional[str] = None
    rankings: List[MPRankingEntry]
    total_mps: int


# ============== Attendance Schemas ==============

class AttendanceRecordResponse(BaseModel):
    """Attendance record response."""
    session_date: date
    session_type: Optional[str] = None
    present: bool
    chamber: Optional[str] = None


class AttendanceStatsResponse(BaseModel):
    """Attendance statistics for an MP."""
    mp_id: str
    sessions_total: int
    sessions_attended: int
    attendance_pct: Optional[float] = None
    recent_records: List[AttendanceRecordResponse] = Field(default_factory=list)


# ============== Sync Status Schemas ==============

class SyncStatusResponse(BaseModel):
    """Parliament data sync status."""
    last_members_sync: Optional[datetime] = None
    last_bills_sync: Optional[datetime] = None
    last_attendance_sync: Optional[datetime] = None
    last_score_calculation: Optional[datetime] = None
    total_mps: int = 0
    total_bills: int = 0
    total_committees: int = 0


# Forward references
MPPerformanceSummary.model_rebuild()
