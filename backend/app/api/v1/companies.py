"""Company registration API endpoints (OCR data + CAMIS enrichment)."""
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_analyst, require_dev
from app.core.database import get_db
from app.services.company_service import CompanyService
from app.schemas.company import (
    CompanyResponse,
    CompanyDirectorResponse,
    CompanyFullResponse,
    CompanyListResponse,
    CompanyStatsResponse,
    CompanyIngestionStats,
    CAMISEnrichmentStats,
    DirectorExtractionStats,
    CAMISSearchResult,
)

router = APIRouter(prefix="/companies", tags=["Company Registrations"])


@router.get("/list", response_model=CompanyListResponse)
async def list_companies(
    name: Optional[str] = Query(default=None, description="Filter by English name (partial match)"),
    registration_number: Optional[int] = Query(default=None, description="Filter by registration number"),
    company_type_category: Optional[str] = Query(default=None, description="Filter by type (Private, Public, Foreign, Non-profit)"),
    district: Optional[str] = Query(default=None, description="Filter by district (partial match)"),
    province: Optional[str] = Query(default=None, description="Filter by province (partial match)"),
    search: Optional[str] = Query(default=None, description="Search in company name"),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """
    List registered companies with filtering and pagination.

    Data sourced from Nepal's Office of Company Registrar (OCR).
    """
    service = CompanyService(db)
    result = await service.list_companies(
        name=name,
        registration_number=registration_number,
        company_type_category=company_type_category,
        district=district,
        province=province,
        search=search,
        page=page,
        per_page=per_page,
    )
    return CompanyListResponse(
        companies=[CompanyResponse(**c) for c in result["companies"]],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        has_more=result["has_more"],
    )


@router.get("/search", response_model=List[CompanyResponse])
async def search_companies(
    q: str = Query(description="Search query for company name"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """Search companies by name (English)."""
    service = CompanyService(db)
    results = await service.search_companies(query=q, limit=limit)
    return [CompanyResponse(**c) for c in results]


@router.get("/stats", response_model=CompanyStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregate company registration statistics.

    Returns total companies, breakdown by type and district.
    """
    service = CompanyService(db)
    return await service.get_stats()


@router.get("/search-camis", response_model=CAMISSearchResult)
async def search_camis(
    name: Optional[str] = Query(default=None, description="Company name to search in CAMIS"),
    reg_number: Optional[str] = Query(default=None, description="Registration number to search in CAMIS"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Search companies via CAMIS API (camis.ocr.gov.np).

    Broader coverage than our local DB -- supports name-based search.
    Requires CAMIS_USERNAME and CAMIS_PASSWORD env vars.
    Dev-only endpoint.
    """
    if not name and not reg_number:
        raise HTTPException(status_code=400, detail="Provide name or reg_number")
    service = CompanyService(db)
    results = await service.search_camis(name=name, reg_number=reg_number)
    return CAMISSearchResult(data=results)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single company by ID."""
    service = CompanyService(db)
    result = await service.get_company(company_id)
    if not result:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyResponse(**result)


@router.get("/{company_id}/directors", response_model=List[CompanyDirectorResponse])
async def get_company_directors(
    company_id: str,
    source: Optional[str] = Query(default=None, description="Filter by source (news_ner, sebon, nrb, camis, manual)"),
    db: AsyncSession = Depends(get_db),
):
    """Get directors/officers for a company from all sources."""
    service = CompanyService(db)
    # Verify company exists
    company = await service.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    directors = await service.get_company_directors(company_id, source=source)
    return [CompanyDirectorResponse(**d) for d in directors]


@router.get("/{company_id}/full", response_model=CompanyFullResponse)
async def get_company_full(
    company_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get company with all directors (enriched view)."""
    service = CompanyService(db)
    result = await service.get_company_full(company_id)
    if not result:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyFullResponse(
        company=CompanyResponse(**result["company"]),
        directors=[CompanyDirectorResponse(**d) for d in result["directors"]],
    )


@router.post("/ingest", response_model=CompanyIngestionStats)
async def ingest_companies(
    start: int = Query(default=1, ge=1, description="Start registration number"),
    end: int = Query(default=100, ge=1, description="End registration number"),
    delay: float = Query(default=1.0, ge=0.5, le=5.0, description="Delay between requests (seconds)"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Trigger scrape + ingest of company data from OCR (application.ocr.gov.np).

    Enumerates registration numbers sequentially and stores all company records.
    Each registration number can return multiple companies.

    WARNING: Large ranges are slow (~1 req/sec due to the govt server).
    Use smaller batches (e.g., 1-1000) for incremental backfill.
    Dev-only endpoint.
    """
    if end - start > 10000:
        raise HTTPException(
            status_code=400,
            detail="Range too large. Max 10000 registration numbers per request. Use smaller batches.",
        )

    service = CompanyService(db)
    stats = await service.ingest_companies(start=start, end=end, delay=delay)
    return CompanyIngestionStats(**stats)


@router.post("/enrich-camis", response_model=CAMISEnrichmentStats)
async def enrich_camis(
    limit: int = Query(default=100, ge=1, le=10000, description="Number of companies to enrich"),
    workers: int = Query(default=8, ge=1, le=16, description="Parallel workers (concurrent CAMIS requests)"),
    min_reg_number: int = Query(default=0, ge=0, description="Start from this registration number (skip older companies)"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Trigger CAMIS enrichment for un-enriched companies.

    Fetches PAN numbers, CAMIS IDs, and CRO IDs from the CAMIS API.
    Uses parallel workers for ~8x speedup. Use min_reg_number to skip old
    companies without PAN data (PANs start around reg >= 150000).
    Dev-only endpoint.
    """
    service = CompanyService(db)
    stats = await service.enrich_from_camis(limit=limit, workers=workers, min_reg_number=min_reg_number)
    return CAMISEnrichmentStats(**stats)


@router.post("/extract-directors", response_model=DirectorExtractionStats)
async def extract_directors(
    limit: int = Query(default=500, ge=1, le=5000, description="Number of recent stories to process"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Run NER-based director/CEO extraction on recent news stories.

    Extracts person-company-role relationships from news text and stores
    as CompanyDirector records with source='news_ner'. Dev-only endpoint.
    """
    service = CompanyService(db)
    stats = await service.extract_directors_from_news(limit=limit)
    return DirectorExtractionStats(**stats)
