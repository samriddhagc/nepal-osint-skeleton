"""Pydantic schemas for election API."""
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.schemas.parliament import MPPerformanceSummary


# ============== Election Schemas ==============

class ElectionResponse(BaseModel):
    """Election metadata response."""
    id: str
    year_bs: int
    year_ad: int
    election_type: str
    status: str
    total_constituencies: int
    total_registered_voters: Optional[int] = None
    total_votes_cast: Optional[int] = None
    turnout_pct: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ElectionListResponse(BaseModel):
    """List of elections response."""
    elections: list[ElectionResponse]


# ============== Candidate Schemas ==============

class CandidateEntitySummary(BaseModel):
    """Lightweight linked entity summary for provenance."""
    entity_id: str
    canonical_id: str
    name_en: str
    name_ne: Optional[str] = None
    match_confidence: Optional[float] = None


class CandidateResponse(BaseModel):
    """Candidate response."""
    id: str
    external_id: str
    name_en: str
    name_ne: Optional[str] = None
    name_en_roman: Optional[str] = None
    party: str
    party_ne: Optional[str] = None
    votes: int = 0
    vote_pct: float = 0.0
    rank: int = 0
    is_winner: bool = False
    is_notable: Optional[bool] = None
    photo_url: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    education: Optional[str] = None
    education_institution: Optional[str] = None
    biography: Optional[str] = None
    biography_source: Optional[str] = None
    biography_source_label: Optional[str] = None
    profile_origin: Optional[str] = None  # "json" | "override" | "seed"
    aliases: Optional[list[str]] = None
    previous_positions: Optional[Any] = None
    linked_entity_id: Optional[str] = None
    entity_link_confidence: Optional[float] = None
    entity_summary: Optional[CandidateEntitySummary] = None


# ============== Constituency Schemas ==============

class ConstituencyResponse(BaseModel):
    """Constituency summary response."""
    id: str
    constituency_code: str
    name_en: str
    name_ne: Optional[str] = None
    district: str
    province: str
    province_id: int
    status: str
    total_registered_voters: Optional[int] = None
    total_votes_cast: Optional[int] = None
    turnout_pct: Optional[float] = None
    winner_party: Optional[str] = None
    winner_votes: Optional[int] = None
    winner_margin: Optional[int] = None


class ConstituencyDetailResponse(ConstituencyResponse):
    """Constituency detail response with candidates."""
    candidates: list[CandidateResponse] = Field(default_factory=list)
    valid_votes: Optional[int] = None
    invalid_votes: Optional[int] = None


class ConstituencyListResponse(BaseModel):
    """Paginated list of constituencies."""
    items: list[ConstituencyResponse]
    total: int
    page: int = 1
    per_page: int = 50
    has_more: bool = False


# ============== National Summary Schemas ==============

class PartySeatResponse(BaseModel):
    """Party seat count."""
    party: str
    seats: int


class NationalSummaryResponse(BaseModel):
    """National election summary."""
    election_id: str
    year_bs: int
    year_ad: int
    status: str
    total_constituencies: int
    declared: int
    counting: int
    pending: int
    turnout_pct: float
    total_votes_cast: int
    total_registered_voters: int
    leading_party: Optional[str] = None
    leading_party_seats: int = 0
    party_seats: list[PartySeatResponse] = Field(default_factory=list)


class SnapshotConstituencyResponse(BaseModel):
    """Constituency shape used by election snapshot API (frontend-compatible)."""
    constituency_id: str
    name_en: str
    name_ne: Optional[str] = None
    district: str
    province: str
    province_id: int
    status: str
    winner_party: Optional[str] = None
    winner_name: Optional[str] = None
    winner_votes: Optional[int] = None
    total_votes: int = 0
    turnout_pct: Optional[float] = None
    candidates: list[CandidateResponse] = Field(default_factory=list)


class ElectionSnapshotResponse(BaseModel):
    """Full election snapshot (DB-backed, frontend-consumable)."""
    election_year: int
    total_constituencies: int
    results: list[SnapshotConstituencyResponse] = Field(default_factory=list)
    constituencies: list[SnapshotConstituencyResponse] = Field(default_factory=list)
    national_summary: Optional[NationalSummaryResponse] = None
    source_mode: str = "db_primary_json_fallback"


# ============== District Map Schemas ==============

class DistrictElectionData(BaseModel):
    """District-level election data for map display."""
    district: str
    province: str
    province_id: int
    constituencies: int
    declared: int
    counting: int
    pending: int
    dominant_party: Optional[str] = None
    parties: dict[str, int] = Field(default_factory=dict)
    total_votes: int = 0


class DistrictMapDataResponse(BaseModel):
    """Map data response with all districts."""
    election_id: str
    year_bs: int
    districts: list[DistrictElectionData]


# ============== Watchlist Schemas ==============

class WatchlistItemRequest(BaseModel):
    """Request to add item to watchlist."""
    alert_level: str = "medium"
    notes: Optional[str] = None


class WatchlistItemResponse(BaseModel):
    """Watchlist item response."""
    id: str
    user_id: str
    constituency_id: str
    constituency_code: Optional[str] = None
    constituency_name: Optional[str] = None
    district: Optional[str] = None
    province: Optional[str] = None
    province_id: Optional[int] = None
    status: Optional[str] = None
    winner_party: Optional[str] = None
    alert_level: str
    notes: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


class WatchlistResponse(BaseModel):
    """User watchlist response."""
    items: list[WatchlistItemResponse]
    total: int


class WatchlistSummaryResponse(BaseModel):
    """Watchlist summary for dashboard."""
    total_items: int
    by_status: dict[str, int] = Field(default_factory=dict)
    by_alert_level: dict[str, int] = Field(default_factory=dict)


# ============== Swing Analysis Schemas ==============

class SwingDataResponse(BaseModel):
    """Swing analysis data."""
    party: str
    current_seats: int
    previous_seats: int
    change: int
    swing_pct: float


class SwingAnalysisResponse(BaseModel):
    """Swing analysis response."""
    current_year: int
    previous_year: int
    swings: list[SwingDataResponse]


# ============== Candidate Dossier Schemas ==============

class StoryMentionResponse(BaseModel):
    """Story mentioning a candidate."""
    story_id: str
    story_title: str
    story_url: Optional[str] = None
    published_at: Optional[datetime] = None
    source_name: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None


class PreviousRunResponse(BaseModel):
    """Previous election run data."""
    election_year: int
    party_name: Optional[str] = None
    constituency_name: Optional[str] = None
    is_winner: bool = False
    votes_received: Optional[int] = None


class ParliamentRecordSummary(BaseModel):
    """Condensed parliamentary record for dossier integration."""
    id: str
    name_en: str
    name_ne: Optional[str] = None
    party: Optional[str] = None
    chamber: Optional[str] = None

    # Key scores
    performance_score: float = 0.0
    performance_percentile: Optional[int] = None
    performance_tier: Optional[str] = None

    # Category scores
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
    speeches_count: int = 0  # From parliament video archives

    # Peer comparison
    peer_group: Optional[str] = None
    peer_rank: Optional[int] = None
    peer_total: Optional[int] = None

    # Prime Minister history
    is_former_pm: bool = False
    pm_terms: int = 0
    notable_roles: Optional[str] = None


class CandidateDossierResponse(BaseModel):
    """Candidate intelligence dossier response."""
    candidate: CandidateResponse
    constituency_code: str
    constituency_name: str
    district: str
    province: str
    province_id: int
    rivals: list[CandidateResponse] = Field(default_factory=list)
    previous_runs: list[PreviousRunResponse] = Field(default_factory=list)
    story_count: int = 0
    constituency_rank: int = 0

    # Election status
    election_year: int = 2082  # Which election year this candidate record is from (BS)
    is_running_2082: bool = True  # Whether candidate is running in current (2082) election

    # Parliamentary record (if candidate is/was an MP)
    parliamentary_record: Optional[ParliamentRecordSummary] = None


class CandidateStoriesResponse(BaseModel):
    """Candidate news stories response."""
    candidate_id: str
    candidate_name: str
    stories: list[StoryMentionResponse] = Field(default_factory=list)
    total: int = 0
    hours: int = 720


# ============== WikiLeaks Integration Schemas ==============

class WikiLeaksDocumentResponse(BaseModel):
    """A WikiLeaks document/cable mentioning a candidate."""
    title: str
    url: str
    collection: str  # e.g., "Cable Gate", "GI Files", "PlusD"
    snippet: str  # Text snippet showing the match
    date_created: Optional[datetime] = None
    date_released: Optional[datetime] = None
    relevance_score: float = 0.0


class CandidateWikiLeaksResponse(BaseModel):
    """WikiLeaks documents mentioning a candidate."""
    candidate_id: str
    candidate_name: str
    query: str
    documents: list[WikiLeaksDocumentResponse] = Field(default_factory=list)
    total_results: int = 0
    searched_at: datetime
    cache_hit: bool = False


# ============== AI Leadership Profile Schemas ==============

class LeadershipProfileResponse(BaseModel):
    """AI-generated leadership profile for a candidate.

    Synthesizes education, news, WikiLeaks, and parliamentary data
    into an actionable intelligence product answering:
    'What kind of leader is this person?'
    """
    candidate_id: str
    candidate_name: str

    # Core assessment
    leadership_style: str  # e.g., "Pragmatic coalition builder"
    key_strengths: list[str] = Field(default_factory=list)  # Top 3 strengths
    key_concerns: list[str] = Field(default_factory=list)  # Top 3 concerns/red flags

    # Political positioning
    ideological_position: str  # e.g., "Center-left nationalist"
    policy_priorities: list[str] = Field(default_factory=list)  # Top 3 policy areas

    # Track record
    experience_summary: str  # 2-3 sentences on experience
    controversy_summary: Optional[str] = None  # Any controversies

    # International perception (from WikiLeaks)
    international_perception: Optional[str] = None  # How foreign govts see them

    # Overall assessment
    analyst_summary: str  # 3-4 sentence executive summary
    confidence_level: str  # "high", "medium", "low"

    # Metadata
    generated_at: datetime
    data_sources: list[str] = Field(default_factory=list)  # What data was used
    cache_hit: bool = False
