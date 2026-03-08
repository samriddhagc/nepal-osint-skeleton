"""Pydantic schemas for government procurement contracts."""
from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class ContractResponse(BaseModel):
    """Single contract response."""
    id: str
    external_id: str
    ifb_number: str
    project_name: str
    procuring_entity: str
    procurement_type: str
    contract_award_date: Optional[date] = None
    contract_amount_npr: Optional[float] = None
    contractor_name: str
    district: Optional[str] = None
    province: Optional[int] = None
    fiscal_year_bs: Optional[str] = None
    source_url: Optional[str] = None
    fetched_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ContractListResponse(BaseModel):
    """Paginated list of contracts."""
    contracts: List[ContractResponse]
    total: int
    page: int = 1
    per_page: int = 20
    has_more: bool = False


class ProcurementTypeStats(BaseModel):
    """Stats for a single procurement type."""
    type: str
    count: int
    total_value: float


class FiscalYearStats(BaseModel):
    """Stats for a single fiscal year."""
    fiscal_year: Optional[str] = None
    count: int
    total_value: float


class ProcurementStatsResponse(BaseModel):
    """Aggregate procurement statistics."""
    total_contracts: int
    total_value_npr: float
    by_procurement_type: List[ProcurementTypeStats]
    by_fiscal_year: List[FiscalYearStats]


class TopContractorResponse(BaseModel):
    """Top contractor by value."""
    contractor_name: str
    contract_count: int
    total_value: float


class TopEntityResponse(BaseModel):
    """Top procuring entity by value."""
    procuring_entity: str
    contract_count: int
    total_value: float


class ProcurementIngestionStats(BaseModel):
    """Stats from procurement data ingestion."""
    source: str = "bolpatra.gov.np"
    fetched: int
    new: int
    updated: int
    errors: List[str] = Field(default_factory=list)
