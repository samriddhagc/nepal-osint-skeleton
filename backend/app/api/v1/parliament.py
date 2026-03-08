"""Parliament API endpoints for MP Performance Index.

Provides endpoints for:
- MP profiles with performance scores
- Bills and legislation
- Committee data
- Rankings and comparisons
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_dev
from app.repositories.parliament import (
    MPPerformanceRepository,
    BillRepository,
    CommitteeRepository,
    QuestionRepository,
    AttendanceRepository,
)
from app.schemas.parliament import (
    MPPerformanceResponse,
    MPPerformanceListResponse,
    MPPerformanceSummary,
    BillResponse,
    BillListResponse,
    BillSummary,
    CommitteeResponse,
    CommitteeListResponse,
    CommitteeSummary,
    QuestionListResponse,
    MPRankingResponse,
    MPRankingEntry,
    AttendanceStatsResponse,
    AttendanceRecordResponse,
)

router = APIRouter(prefix="/parliament", tags=["parliament"])


# ============== MP Endpoints ==============

@router.get("/members", response_model=MPPerformanceListResponse)
async def list_mps(
    chamber: Optional[str] = Query(default=None, regex="^(hor|na)$", description="Filter by chamber"),
    party: Optional[str] = Query(default=None, description="Filter by party name"),
    province_id: Optional[int] = Query(default=None, ge=1, le=7, description="Filter by province"),
    election_type: Optional[str] = Query(default=None, regex="^(fptp|pr)$", description="Filter by election type"),
    min_score: Optional[float] = Query(default=None, ge=0, le=100, description="Minimum performance score"),
    tier: Optional[str] = Query(default=None, description="Filter by performance tier"),
    q: Optional[str] = Query(default=None, description="Search by name, party, constituency, or MP ID"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    List all MPs with performance data.

    Supports filtering by chamber, party, province, election type, and score.
    Returns paginated results sorted by performance score.
    """
    repo = MPPerformanceRepository(db)
    mps, total = await repo.list_mps(
        chamber=chamber,
        party=party,
        province_id=province_id,
        election_type=election_type,
        min_score=min_score,
        tier=tier,
        q=q,
        page=page,
        per_page=per_page,
    )

    items = [MPPerformanceResponse(**mp.to_dict()) for mp in mps]

    return MPPerformanceListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page) < total,
    )


@router.get("/members/{mp_id}", response_model=MPPerformanceResponse)
async def get_mp_detail(
    mp_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed MP performance data.

    Includes all scores, percentiles, and peer rankings.
    """
    repo = MPPerformanceRepository(db)
    mp = await repo.get_by_id(mp_id)

    if not mp:
        raise HTTPException(status_code=404, detail="MP not found")

    return MPPerformanceResponse(**mp.to_dict())


@router.get("/members/{mp_id}/summary", response_model=MPPerformanceSummary)
async def get_mp_summary(
    mp_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get condensed MP performance summary.

    Optimized for dossier integration - includes key scores and recent bills.
    """
    mp_repo = MPPerformanceRepository(db)
    bill_repo = BillRepository(db)

    mp = await mp_repo.get_by_id(mp_id)
    if not mp:
        raise HTTPException(status_code=404, detail="MP not found")

    # Get recent bills
    recent_bills = await bill_repo.list_by_mp(mp_id, limit=5)
    bill_summaries = [
        BillSummary(
            id=str(bill.id),
            title_en=bill.title_en,
            status=bill.status,
            presented_date=bill.presented_date,
            passed_date=bill.passed_date,
        )
        for bill in recent_bills
    ]

    return MPPerformanceSummary(
        id=str(mp.id),
        name_en=mp.name_en,
        name_ne=mp.name_ne,
        party=mp.party,
        chamber=mp.chamber,
        performance_score=mp.performance_score,
        performance_percentile=mp.performance_percentile,
        performance_tier=mp.performance_tier,
        legislative_score=mp.legislative_score,
        legislative_percentile=mp.legislative_percentile,
        participation_score=mp.participation_score,
        participation_percentile=mp.participation_percentile,
        accountability_score=mp.accountability_score,
        accountability_percentile=mp.accountability_percentile,
        committee_score=mp.committee_score,
        committee_percentile=mp.committee_percentile,
        bills_introduced=mp.bills_introduced,
        bills_passed=mp.bills_passed,
        session_attendance_pct=mp.session_attendance_pct,
        questions_asked=mp.questions_asked,
        committee_memberships=mp.committee_memberships,
        committee_leadership_roles=mp.committee_leadership_roles,
        peer_group=mp.peer_group,
        peer_rank=mp.peer_rank,
        peer_total=mp.peer_total,
        recent_bills=bill_summaries,
    )


@router.get("/members/by-candidate/{candidate_id}", response_model=MPPerformanceSummary)
async def get_mp_by_candidate(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get MP performance data linked to an election candidate.

    For dossier integration - returns parliament record for a candidate.
    """
    mp_repo = MPPerformanceRepository(db)
    bill_repo = BillRepository(db)

    mp = await mp_repo.get_by_candidate_id(candidate_id)
    if not mp:
        raise HTTPException(status_code=404, detail="No parliament record found for this candidate")

    # Get recent bills
    recent_bills = await bill_repo.list_by_mp(mp.id, limit=5)
    bill_summaries = [
        BillSummary(
            id=str(bill.id),
            title_en=bill.title_en,
            status=bill.status,
            presented_date=bill.presented_date,
            passed_date=bill.passed_date,
        )
        for bill in recent_bills
    ]

    return MPPerformanceSummary(
        id=str(mp.id),
        name_en=mp.name_en,
        name_ne=mp.name_ne,
        party=mp.party,
        chamber=mp.chamber,
        performance_score=mp.performance_score,
        performance_percentile=mp.performance_percentile,
        performance_tier=mp.performance_tier,
        legislative_score=mp.legislative_score,
        legislative_percentile=mp.legislative_percentile,
        participation_score=mp.participation_score,
        participation_percentile=mp.participation_percentile,
        accountability_score=mp.accountability_score,
        accountability_percentile=mp.accountability_percentile,
        committee_score=mp.committee_score,
        committee_percentile=mp.committee_percentile,
        bills_introduced=mp.bills_introduced,
        bills_passed=mp.bills_passed,
        session_attendance_pct=mp.session_attendance_pct,
        questions_asked=mp.questions_asked,
        committee_memberships=mp.committee_memberships,
        committee_leadership_roles=mp.committee_leadership_roles,
        peer_group=mp.peer_group,
        peer_rank=mp.peer_rank,
        peer_total=mp.peer_total,
        recent_bills=bill_summaries,
    )


@router.get("/members/{mp_id}/bills", response_model=BillListResponse)
async def get_mp_bills(
    mp_id: UUID,
    status: Optional[str] = Query(default=None, description="Filter by bill status"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get bills introduced by this MP."""
    mp_repo = MPPerformanceRepository(db)
    bill_repo = BillRepository(db)

    mp = await mp_repo.get_by_id(mp_id)
    if not mp:
        raise HTTPException(status_code=404, detail="MP not found")

    bills, total = await bill_repo.list_bills(
        presenting_mp_id=mp_id,
        status=status,
        page=page,
        per_page=per_page,
    )

    items = [
        BillResponse(
            id=str(bill.id),
            external_id=bill.external_id,
            title_en=bill.title_en,
            title_ne=bill.title_ne,
            bill_type=bill.bill_type,
            status=bill.status,
            presented_date=bill.presented_date,
            passed_date=bill.passed_date,
            presenting_mp_id=str(mp_id),
            presenting_mp_name=mp.name_en,
            ministry=bill.ministry,
            chamber=bill.chamber,
            term=bill.term,
            pdf_url=bill.pdf_url,
        )
        for bill in bills
    ]

    return BillListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page) < total,
    )


@router.get("/members/{mp_id}/committees")
async def get_mp_committees(
    mp_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get committee memberships for this MP."""
    mp_repo = MPPerformanceRepository(db)
    committee_repo = CommitteeRepository(db)

    mp = await mp_repo.get_by_id(mp_id)
    if not mp:
        raise HTTPException(status_code=404, detail="MP not found")

    committees = await committee_repo.list_by_mp(mp_id)

    return {
        "mp_id": str(mp_id),
        "mp_name": mp.name_en,
        "committees": [
            CommitteeSummary(
                id=c["committee"]["id"],
                name_en=c["committee"]["name_en"],
                role=c["role"],
                attendance_pct=c["attendance_pct"],
                meetings_attended=c["meetings_attended"],
                meetings_total=c["meetings_total"],
            )
            for c in committees
        ],
        "total": len(committees),
    }


@router.get("/members/{mp_id}/attendance", response_model=AttendanceStatsResponse)
async def get_mp_attendance(
    mp_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get attendance statistics for this MP."""
    mp_repo = MPPerformanceRepository(db)
    attendance_repo = AttendanceRepository(db)

    mp = await mp_repo.get_by_id(mp_id)
    if not mp:
        raise HTTPException(status_code=404, detail="MP not found")

    stats = await attendance_repo.get_attendance_stats(mp_id)
    recent = await attendance_repo.list_by_mp(mp_id, limit=20)

    return AttendanceStatsResponse(
        mp_id=str(mp_id),
        sessions_total=stats["sessions_total"],
        sessions_attended=stats["sessions_attended"],
        attendance_pct=stats["attendance_pct"],
        recent_records=[
            AttendanceRecordResponse(
                session_date=r.session_date,
                session_type=r.session_type,
                present=r.present,
                chamber=r.chamber,
            )
            for r in recent
        ],
    )


# ============== Rankings Endpoints ==============

@router.get("/rankings", response_model=MPRankingResponse)
async def get_rankings(
    category: str = Query(
        default="overall",
        regex="^(overall|legislative|participation|accountability|committee)$",
        description="Ranking category",
    ),
    peer_group: Optional[str] = Query(default=None, description="Filter by peer group"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get MP rankings by category.

    Categories: overall, legislative, participation, accountability, committee.
    Can filter by peer group (e.g., 'fptp_1', 'pr_3', 'minister', 'na').
    """
    repo = MPPerformanceRepository(db)
    mps = await repo.get_rankings(
        category=category,
        peer_group=peer_group,
        limit=limit,
    )

    # Build ranking entries
    rankings = []
    for rank, mp in enumerate(mps, 1):
        score = getattr(mp, f"{category}_score") if category != "overall" else mp.performance_score
        percentile = getattr(mp, f"{category}_percentile") if category != "overall" else mp.performance_percentile

        rankings.append(MPRankingEntry(
            id=str(mp.id),
            name_en=mp.name_en,
            name_ne=mp.name_ne,
            party=mp.party,
            constituency=mp.constituency,
            photo_url=mp.photo_url,
            score=score,
            percentile=percentile,
            rank=rank,
        ))

    return MPRankingResponse(
        category=category,
        peer_group=peer_group,
        rankings=rankings,
        total_mps=len(mps),
    )


@router.get("/peer-groups")
async def get_peer_groups(
    db: AsyncSession = Depends(get_db),
):
    """Get list of available peer groups for ranking filters."""
    repo = MPPerformanceRepository(db)
    groups = await repo.get_peer_groups()

    return {
        "peer_groups": groups,
        "descriptions": {
            "minister": "Cabinet Ministers",
            "na": "National Assembly Members",
            "fptp_1": "FPTP - Koshi Province",
            "fptp_2": "FPTP - Madhesh Province",
            "fptp_3": "FPTP - Bagmati Province",
            "fptp_4": "FPTP - Gandaki Province",
            "fptp_5": "FPTP - Lumbini Province",
            "fptp_6": "FPTP - Karnali Province",
            "fptp_7": "FPTP - Sudurpashchim Province",
            "pr_1": "PR - Koshi Province",
            "pr_2": "PR - Madhesh Province",
            "pr_3": "PR - Bagmati Province",
            "pr_4": "PR - Gandaki Province",
            "pr_5": "PR - Lumbini Province",
            "pr_6": "PR - Karnali Province",
            "pr_7": "PR - Sudurpashchim Province",
        },
    }


# ============== Bills Endpoints ==============

@router.get("/bills", response_model=BillListResponse)
async def list_bills(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    bill_type: Optional[str] = Query(default=None, description="Filter by bill type"),
    chamber: Optional[str] = Query(default=None, regex="^(hor|na)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all parliamentary bills with filters."""
    repo = BillRepository(db)
    bills, total = await repo.list_bills(
        status=status,
        bill_type=bill_type,
        chamber=chamber,
        page=page,
        per_page=per_page,
    )

    items = [
        BillResponse(
            id=str(bill.id),
            external_id=bill.external_id,
            title_en=bill.title_en,
            title_ne=bill.title_ne,
            bill_type=bill.bill_type,
            status=bill.status,
            presented_date=bill.presented_date,
            passed_date=bill.passed_date,
            presenting_mp_id=str(bill.presenting_mp_id) if bill.presenting_mp_id else None,
            ministry=bill.ministry,
            chamber=bill.chamber,
            term=bill.term,
            pdf_url=bill.pdf_url,
        )
        for bill in bills
    ]

    return BillListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page) < total,
    )


@router.get("/bills/{bill_id}", response_model=BillResponse)
async def get_bill_detail(
    bill_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get bill details."""
    repo = BillRepository(db)
    bill = await repo.get_by_id(bill_id)

    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    return BillResponse(
        id=str(bill.id),
        external_id=bill.external_id,
        title_en=bill.title_en,
        title_ne=bill.title_ne,
        bill_type=bill.bill_type,
        status=bill.status,
        presented_date=bill.presented_date,
        passed_date=bill.passed_date,
        presenting_mp_id=str(bill.presenting_mp_id) if bill.presenting_mp_id else None,
        ministry=bill.ministry,
        chamber=bill.chamber,
        term=bill.term,
        pdf_url=bill.pdf_url,
    )


# ============== Committees Endpoints ==============

@router.get("/committees", response_model=CommitteeListResponse)
async def list_committees(
    chamber: Optional[str] = Query(default=None, regex="^(hor|na|joint)$"),
    is_active: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    """List parliamentary committees."""
    repo = CommitteeRepository(db)
    committees = await repo.list_committees(
        chamber=chamber,
        is_active=is_active,
    )

    items = [
        CommitteeResponse(**c.to_dict())
        for c in committees
    ]

    return CommitteeListResponse(
        items=items,
        total=len(items),
    )


@router.get("/committees/{committee_id}", response_model=CommitteeResponse)
async def get_committee_detail(
    committee_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get committee details with members."""
    repo = CommitteeRepository(db)
    committee = await repo.get_by_id(committee_id)

    if not committee:
        raise HTTPException(status_code=404, detail="Committee not found")

    return CommitteeResponse(**committee.to_dict())


# ============== Admin Endpoints ==============

@router.post("/admin/sync", tags=["parliament-admin"])
async def trigger_parliament_sync(
    scope: str = Query(
        default="score",
        description="What to sync: 'all', 'members', 'bills', 'committees', 'videos', 'score'"
    ),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_dev),  # Dev-only
):
    """
    Trigger parliament data sync (dev-only).

    Scopes:
    - all: Full pipeline (members -> committees -> bills -> videos -> scores)
    - members: Scrape MP profiles
    - bills: Scrape bills with presenter details
    - committees: Scrape committees and members
    - videos: Match video speakers to MPs
    - score: Recalculate performance scores only
    """
    from app.services.parliament_scorer import PerformanceScorer

    if scope == 'score':
        scorer = PerformanceScorer(db)
        stats = await scorer.calculate_all_scores()
        return {"message": "Scores recalculated", "stats": stats}

    # Map scope to scheduler functions
    import asyncio
    from app.tasks.scheduler import (
        poll_parliament_members, poll_parliament_bills,
        poll_parliament_committees, poll_parliament_videos,
        recalculate_parliament_scores, run_full_parliament_sync,
    )

    scope_map = {
        'all': run_full_parliament_sync,
        'members': poll_parliament_members,
        'bills': poll_parliament_bills,
        'committees': poll_parliament_committees,
        'videos': poll_parliament_videos,
    }

    fn = scope_map.get(scope)
    if not fn:
        raise HTTPException(status_code=400, detail=f"Unknown scope: {scope}")

    # Run as fire-and-forget background coroutine
    asyncio.create_task(fn())

    return {
        "message": f"Parliament sync '{scope}' triggered. Check logs for progress.",
        "hint": "Use GET /parliament/admin/stats to check data quality after sync."
    }


@router.get("/admin/stats", tags=["parliament-admin"])
async def get_parliament_stats(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_dev),  # Dev-only
):
    """Get parliament data quality statistics (dev-only)."""
    from sqlalchemy import text

    result = await db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN bills_introduced > 0 THEN 1 END) as has_bills,
            COUNT(CASE WHEN speeches_count > 0 THEN 1 END) as has_speeches,
            COUNT(CASE WHEN committee_memberships > 0 THEN 1 END) as has_committees,
            COUNT(CASE WHEN session_attendance_pct > 0 THEN 1 END) as has_attendance,
            COUNT(CASE WHEN questions_asked > 0 THEN 1 END) as has_questions,
            ROUND(AVG(performance_score)::numeric, 1) as avg_score,
            MAX(performance_score) as max_score
        FROM mp_performance
        WHERE is_current_member = true
    """))
    row = result.fetchone()

    return {
        "total_mps": row[0],
        "data_coverage": {
            "bills": {"count": row[1], "pct": round(row[1] * 100 / max(row[0], 1), 1)},
            "speeches": {"count": row[2], "pct": round(row[2] * 100 / max(row[0], 1), 1)},
            "committees": {"count": row[3], "pct": round(row[3] * 100 / max(row[0], 1), 1)},
            "attendance": {"count": row[4], "pct": round(row[4] * 100 / max(row[0], 1), 1)},
            "questions": {"count": row[5], "pct": round(row[5] * 100 / max(row[0], 1), 1)},
        },
        "scores": {
            "avg": float(row[6]) if row[6] else 0,
            "max": float(row[7]) if row[7] else 0,
        },
    }
