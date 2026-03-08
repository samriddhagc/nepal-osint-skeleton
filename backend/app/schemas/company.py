"""Pydantic schemas for company registrations."""
from datetime import date, datetime
from typing import Optional, List, Dict

from pydantic import BaseModel, Field


class CompanyResponse(BaseModel):
    """Single company response."""
    id: str
    external_id: str
    registration_number: int
    name_nepali: Optional[str] = None
    name_english: str
    registration_date_bs: Optional[str] = None
    registration_date_ad: Optional[date] = None
    company_type: Optional[str] = None
    company_type_category: Optional[str] = None
    company_address: Optional[str] = None
    district: Optional[str] = None
    province: Optional[str] = None
    last_communication_bs: Optional[str] = None
    # CAMIS enrichment fields
    pan: Optional[str] = None
    camis_company_id: Optional[int] = None
    cro_company_id: Optional[str] = None
    camis_enriched: bool = False
    camis_enriched_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CompanyDirectorResponse(BaseModel):
    """Single director/officer response."""
    id: str
    company_id: Optional[str] = None
    name_en: str
    name_np: Optional[str] = None
    role: Optional[str] = None
    company_name_hint: Optional[str] = None
    source: str
    source_url: Optional[str] = None
    confidence: float = 1.0
    pan: Optional[str] = None
    citizenship_no: Optional[str] = None
    appointed_date: Optional[date] = None
    resigned_date: Optional[date] = None
    fetched_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CompanyFullResponse(BaseModel):
    """Company with directors."""
    company: CompanyResponse
    directors: List[CompanyDirectorResponse] = Field(default_factory=list)


class CompanyListResponse(BaseModel):
    """Paginated list of companies."""
    companies: List[CompanyResponse]
    total: int
    page: int = 1
    per_page: int = 20
    has_more: bool = False


class CompanyStatsResponse(BaseModel):
    """Aggregate company registration statistics."""
    total_companies: int
    max_registration_number: int
    by_type_category: Dict[str, int]
    by_district: Dict[str, int]


class CompanyIngestionStats(BaseModel):
    """Stats from company data ingestion."""
    source: str = "ocr.gov.np"
    range_start: int
    range_end: int
    queries_made: int
    fetched: int
    new: int
    updated: int
    errors: List[str] = Field(default_factory=list)


class CAMISEnrichmentStats(BaseModel):
    """Stats from CAMIS enrichment batch."""
    total_unenriched: int
    batch_size: int
    enriched: int
    pans_found: int
    errors: List[str] = Field(default_factory=list)


class DirectorExtractionStats(BaseModel):
    """Stats from director NER extraction."""
    stories_processed: int
    mentions_found: int
    saved: int
    skipped_duplicate: int
    errors: int


class CAMISSearchResult(BaseModel):
    """A company record from CAMIS search."""
    data: List[dict] = Field(default_factory=list)
