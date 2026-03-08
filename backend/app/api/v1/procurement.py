"""Government procurement contract API endpoints."""
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_analyst, require_dev
from app.core.database import get_db
from app.services.procurement_service import ProcurementService
from app.schemas.procurement import (
    ContractResponse,
    ContractListResponse,
    ProcurementStatsResponse,
    TopContractorResponse,
    TopEntityResponse,
    ProcurementIngestionStats,
)

router = APIRouter(prefix="/procurement", tags=["Government Procurement"])


@router.get("/contracts", response_model=ContractListResponse)
async def list_contracts(
    procuring_entity: Optional[str] = Query(default=None, description="Filter by procuring entity (partial match)"),
    procurement_type: Optional[str] = Query(default=None, description="Filter by type (NCB, ICB, Sealed Quotation, etc.)"),
    contractor_name: Optional[str] = Query(default=None, description="Filter by contractor name (partial match)"),
    district: Optional[str] = Query(default=None, description="Filter by district"),
    fiscal_year_bs: Optional[str] = Query(default=None, description="Filter by fiscal year (e.g. 081/082)"),
    min_amount: Optional[float] = Query(default=None, ge=0, description="Minimum contract amount (NRs)"),
    max_amount: Optional[float] = Query(default=None, ge=0, description="Maximum contract amount (NRs)"),
    search: Optional[str] = Query(default=None, description="Search in project name"),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """
    List government procurement contracts with filtering and pagination.

    Data sourced from bolpatra.gov.np e-GP portal.
    """
    service = ProcurementService(db)
    result = await service.list_contracts(
        procuring_entity=procuring_entity,
        procurement_type=procurement_type,
        contractor_name=contractor_name,
        district=district,
        fiscal_year_bs=fiscal_year_bs,
        min_amount=min_amount,
        max_amount=max_amount,
        search=search,
        page=page,
        per_page=per_page,
    )

    return ContractListResponse(
        contracts=[ContractResponse(**c) for c in result["contracts"]],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        has_more=result["has_more"],
    )


@router.get("/contracts/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single procurement contract by ID."""
    service = ProcurementService(db)
    result = await service.get_contract(contract_id)

    if not result:
        raise HTTPException(status_code=404, detail="Contract not found")

    return ContractResponse(**result)


@router.get("/stats", response_model=ProcurementStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregate procurement statistics.

    Returns total contracts, total value, breakdowns by procurement type
    and fiscal year.
    """
    service = ProcurementService(db)
    return await service.get_stats()


@router.get("/top-contractors", response_model=List[TopContractorResponse])
async def get_top_contractors(
    limit: int = Query(default=10, ge=1, le=50, description="Number of top contractors"),
    db: AsyncSession = Depends(get_db),
):
    """Get top contractors ranked by total contract value."""
    service = ProcurementService(db)
    return await service.get_top_contractors(limit=limit)


@router.get("/top-entities", response_model=List[TopEntityResponse])
async def get_top_procuring_entities(
    limit: int = Query(default=10, ge=1, le=50, description="Number of top entities"),
    db: AsyncSession = Depends(get_db),
):
    """Get top procuring entities ranked by total contract value."""
    service = ProcurementService(db)
    return await service.get_top_procuring_entities(limit=limit)


@router.post("/ingest", response_model=ProcurementIngestionStats)
async def ingest_contracts(
    page_size: int = Query(default=5000, ge=100, le=10000, description="Records to fetch from bolpatra"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Trigger scrape + ingest of government contracts from bolpatra.gov.np.

    This fetches all e-Contract records from the public procurement portal
    and upserts them into the database. Dev-only endpoint.
    """
    service = ProcurementService(db)
    stats = await service.ingest_contracts(page_size=page_size)
    return ProcurementIngestionStats(**stats)
