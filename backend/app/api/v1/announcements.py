"""Government announcements API endpoints."""
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_analyst, require_dev
from app.core.database import get_db
from app.services.announcement_service import AnnouncementService
from app.schemas.announcement import (
    AnnouncementResponse,
    AnnouncementListResponse,
    AnnouncementSummary,
    IngestionStats,
    SourceInfo,
)

router = APIRouter(prefix="/announcements", tags=["Government Announcements"])


@router.get("/summary", response_model=AnnouncementSummary)
async def get_announcements_summary(
    limit: int = Query(default=5, ge=1, le=20, description="Number of latest announcements"),
    hours: Optional[int] = Query(default=None, ge=1, le=168, description="Filter by hours (1=24h, 72=3d, 168=7d)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get summary of government announcements for dashboard widget.

    Returns total count, unread count, breakdown by source/category,
    and the latest announcements.
    """
    service = AnnouncementService(db)
    return await service.get_summary(limit=limit, hours=hours)


@router.get("/list", response_model=AnnouncementListResponse)
async def list_announcements(
    source: Optional[str] = Query(default=None, description="Filter by source (e.g., moha.gov.np)"),
    province: Optional[str] = Query(default=None, description="Filter by province (e.g., Koshi, Bagmati)"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    has_attachments: Optional[bool] = Query(default=None, description="Filter by attachment presence"),
    unread_only: bool = Query(default=False, description="Only show unread"),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """
    List government announcements with filtering and pagination.

    Filtering options:
    - source: Filter by specific source domain (takes precedence over province)
    - province: Filter by province name (Koshi, Madhesh, Bagmati, Gandaki, Lumbini, Karnali, Sudurpashchim)
    """
    service = AnnouncementService(db)
    result = await service.list_announcements(
        source=source,
        province=province,
        category=category,
        has_attachments=has_attachments,
        unread_only=unread_only,
        page=page,
        per_page=per_page,
    )

    return AnnouncementListResponse(
        announcements=[
            AnnouncementResponse(**a) for a in result["announcements"]
        ],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        has_more=result["has_more"],
    )


@router.get("/sources", response_model=List[SourceInfo])
async def get_sources(
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of available government sources.
    """
    service = AnnouncementService(db)
    sources = await service.get_sources()
    return [SourceInfo(**s) for s in sources]


@router.get("/{announcement_id}", response_model=AnnouncementResponse)
async def get_announcement(
    announcement_id: str,
    fetch_content: bool = Query(default=False, description="Fetch full content if not already loaded"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single announcement by ID.

    Use fetch_content=true to load full content and attachments.
    """
    service = AnnouncementService(db)

    if fetch_content:
        result = await service.fetch_announcement_content(announcement_id)
    else:
        result = await service.get_announcement(announcement_id)

    if not result:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return AnnouncementResponse(**result)


@router.post("/{announcement_id}/read")
async def mark_as_read(
    announcement_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst),
):
    """
    Mark an announcement as read.
    """
    service = AnnouncementService(db)
    success = await service.mark_as_read(announcement_id)

    if not success:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"status": "ok", "id": announcement_id}


@router.post("/mark-all-read")
async def mark_all_as_read(
    source: Optional[str] = Query(default=None, description="Only mark from specific source"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst),
):
    """
    Mark all announcements as read.
    """
    service = AnnouncementService(db)
    count = await service.mark_all_as_read(source=source)

    return {"status": "ok", "count": count}


@router.post("/refresh", response_model=List[IngestionStats])
async def refresh_announcements(
    sources: Optional[List[str]] = Query(default=None, description="Sources to refresh (default: all)"),
    max_pages: int = Query(default=3, ge=1, le=10, description="Max pages per category"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Manually trigger announcement refresh from government sources.

    This endpoint is for admin/debugging purposes. Announcements are
    automatically refreshed every 3 hours by the scheduler.

    Supported sources:
    - moha.gov.np: Ministry of Home Affairs
    - opmcm.gov.np: Prime Minister's Office
    - mofa.gov.np: Ministry of Foreign Affairs
    - election.gov.np: Election Commission Nepal
    - provincial: All 7 provincial governments
    - dao: Priority DAO offices
    - {province}.gov.np: Specific provincial government
    - dao{district}.moha.gov.np: Specific DAO office
    """
    service = AnnouncementService(db)

    if sources:
        # Refresh specific sources
        all_stats = []
        if "moha.gov.np" in sources:
            stats = await service.ingest_moha(max_pages=max_pages)
            all_stats.append(stats)
        if "opmcm.gov.np" in sources:
            stats = await service.ingest_opmcm(max_pages=max_pages)
            all_stats.append(stats)
        if "mofa.gov.np" in sources:
            stats = await service.ingest_mofa(max_pages=max_pages)
            all_stats.append(stats)
        if "election.gov.np" in sources:
            stats = await service.ingest_ecn(max_pages=max_pages)
            all_stats.append(stats)

        # Provincial governments
        if "provincial" in sources:
            prov_stats = await service.ingest_all_provincial(max_pages=max_pages)
            all_stats.extend(prov_stats)

        # DAO offices
        if "dao" in sources:
            dao_stats = await service.ingest_priority_daos(max_pages=max_pages)
            all_stats.extend(dao_stats)

        # Check for specific provincial sources (e.g., koshi.gov.np)
        from app.ingestion.provincial_scraper import ProvincialScraper
        for province in ProvincialScraper.PROVINCES.keys():
            if f"{province}.gov.np" in sources:
                stats = await service.ingest_provincial(province, max_pages=max_pages)
                all_stats.append(stats)

        # Check for specific DAO sources (e.g., daokathmandu.moha.gov.np)
        from app.ingestion.dao_scraper import DAOScraper
        for district in DAOScraper.DISTRICTS.keys():
            if f"dao{district}.moha.gov.np" in sources:
                stats = await service.ingest_dao(district, max_pages=max_pages)
                all_stats.append(stats)

        return all_stats if all_stats else await service.ingest_all_sources(max_pages=max_pages)
    else:
        # Refresh all sources
        return await service.ingest_all_sources(max_pages=max_pages)


@router.post("/refresh-provincial", response_model=List[IngestionStats])
async def refresh_provincial_announcements(
    provinces: Optional[List[str]] = Query(default=None, description="Provinces to refresh (default: all)"),
    max_pages: int = Query(default=2, ge=1, le=5, description="Max pages per category"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Refresh announcements from provincial government websites.

    Available provinces: koshi, madhesh, bagmati, gandaki, lumbini, karnali, sudurpashchim
    """
    service = AnnouncementService(db)

    if provinces:
        all_stats = []
        for province in provinces:
            stats = await service.ingest_provincial(province.lower(), max_pages=max_pages)
            all_stats.append(stats)
        return all_stats
    else:
        return await service.ingest_all_provincial(max_pages=max_pages)


@router.post("/refresh-dao", response_model=List[IngestionStats])
async def refresh_dao_announcements(
    districts: Optional[List[str]] = Query(default=None, description="Districts to refresh (default: priority)"),
    max_pages: int = Query(default=2, ge=1, le=5, description="Max pages per category"),
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh announcements from DAO (District Administration Office) websites.

    Priority districts: kathmandu, lalitpur, bhaktapur, kaski, morang, sunsari, parsa, chitwan, rupandehi, kailali, banke, dang, jhapa, sarlahi

    DAO offices issue important local orders including curfews.
    """
    service = AnnouncementService(db)

    if districts:
        all_stats = []
        for district in districts:
            stats = await service.ingest_dao(district.lower(), max_pages=max_pages)
            all_stats.append(stats)
        return all_stats
    else:
        return await service.ingest_priority_daos(max_pages=max_pages)


@router.post("/refresh-ministries", response_model=List[IngestionStats])
async def refresh_ministry_announcements(
    ministries: Optional[List[str]] = Query(default=None, description="Ministries to refresh (default: all)"),
    max_pages: int = Query(default=2, ge=1, le=5, description="Max pages per endpoint"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Refresh announcements from federal ministry websites.

    Available ministries: mof, moe, moh, moics, moltm, mofaga, moewri, moest, moys,
    moless, mowcsc, mofsc, mopit, moiad, mocit, moics, moud, moljpa, moha

    Most ministries have press-release and notice categories.
    """
    service = AnnouncementService(db)

    if ministries:
        all_stats = []
        for ministry in ministries:
            stats = await service.ingest_ministry(ministry.lower(), max_pages=max_pages)
            all_stats.append(stats)
        return all_stats
    else:
        return await service.ingest_all_ministries(max_pages=max_pages)


@router.post("/refresh-constitutional", response_model=List[IngestionStats])
async def refresh_constitutional_announcements(
    bodies: Optional[List[str]] = Query(default=None, description="Constitutional bodies to refresh (default: all)"),
    max_pages: int = Query(default=2, ge=1, le=5, description="Max pages per endpoint"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Refresh announcements from constitutional body websites.

    Available bodies: ciaa, oag, psc, nhrc, nwc, nrb, sebon, nib, nta, nerc, caan, dda, supremecourt, jc

    Constitutional bodies include CIAA, AG Office, PSC, NHRC, regulatory bodies, and judiciary.
    """
    service = AnnouncementService(db)

    if bodies:
        all_stats = []
        for body in bodies:
            stats = await service.ingest_constitutional_body(body.lower(), max_pages=max_pages)
            all_stats.append(stats)
        return all_stats
    else:
        return await service.ingest_all_constitutional_bodies(max_pages=max_pages)


@router.post("/refresh-municipalities", response_model=List[IngestionStats])
async def refresh_municipality_announcements(
    municipalities: Optional[List[str]] = Query(default=None, description="Municipalities to refresh (default: all)"),
    max_pages: int = Query(default=2, ge=1, le=5, description="Max pages per endpoint"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Refresh announcements from municipality websites.

    Available municipalities: kathmandu, lalitpur, pokhara, bharatpur, biratnagar, birgunj,
    dharan, itahari, hetauda, janakpur, nepalgunj, butwal, dhangadhi, tulsipur, ghorahi,
    siddharthanagar, birendranagar

    Includes all 6 metropolitan cities and 11 sub-metropolitan cities.
    """
    service = AnnouncementService(db)

    if municipalities:
        all_stats = []
        for mun in municipalities:
            stats = await service.ingest_municipality(mun.lower(), max_pages=max_pages)
            all_stats.append(stats)
        return all_stats
    else:
        return await service.ingest_all_municipalities(max_pages=max_pages)


@router.post("/refresh-all", response_model=List[IngestionStats])
async def refresh_all_announcements(
    max_pages: int = Query(default=2, ge=1, le=5, description="Max pages per endpoint"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """
    Refresh announcements from ALL government sources.

    This is a comprehensive refresh that includes:
    - Key sources (MOHA, OPMCM, MOFA, ECN)
    - All federal ministries (18+)
    - All provincial governments (7)
    - All constitutional bodies (14+)
    - All metropolitan/sub-metropolitan cities (17)
    - Priority DAO offices (14)

    WARNING: This is a long-running operation that may take several minutes.
    Use sparingly and prefer targeted refresh endpoints.
    """
    service = AnnouncementService(db)
    return await service.ingest_all_sources(max_pages=max_pages)


@router.post("/ingest/security", response_model=List[IngestionStats])
async def ingest_security_announcements(
    source_ids: Optional[List[str]] = Query(default=None, description="Specific security source IDs to ingest"),
    max_pages: int = Query(default=2, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """Ingest official Nepal security service announcements into announcements + graph evidence."""
    service = AnnouncementService(db)
    return await service.ingest_security_sources(source_ids=source_ids, max_pages=max_pages)


@router.get("/security/status")
async def get_security_ingest_status(
    db: AsyncSession = Depends(get_db),
):
    """Get configured security sources with ingestion counters."""
    service = AnnouncementService(db)
    return {
        "items": await service.get_security_source_status(),
    }
