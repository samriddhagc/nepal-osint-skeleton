"""Election API endpoints."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_analyst, get_current_user
from app.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.services.election_service import ElectionService
# CandidateProfileResolver excluded from skeleton
from app.repositories.story import StoryRepository
from app.repositories.parliament import MPPerformanceRepository
from app.schemas.election import (
    ElectionListResponse,
    ElectionResponse,
    ElectionSnapshotResponse,
    ConstituencyListResponse,
    ConstituencyDetailResponse,
    NationalSummaryResponse,
    DistrictMapDataResponse,
    WatchlistResponse,
    WatchlistItemResponse,
    WatchlistItemRequest,
    SwingAnalysisResponse,
    CandidateDossierResponse,
    CandidateStoriesResponse,
    CandidateResponse,
    StoryMentionResponse,
    PreviousRunResponse,
    ParliamentRecordSummary,
    CandidateWikiLeaksResponse,
    WikiLeaksDocumentResponse,
    LeadershipProfileResponse,
)
# wikileaks_service and leadership_profile_service excluded from skeleton
get_wikileaks_service = None
generate_leadership_profile = None
profile_to_dict = None
clear_profile_cache = None
from app.repositories.ministerial_position import MinisterialPositionRepository

router = APIRouter(prefix="/elections", tags=["elections"])
settings = get_settings()


def _candidate_response_with_resolved_profile(
    candidate,
    resolved_profile: dict,
) -> CandidateResponse:
    """Build CandidateResponse with unified precedence-applied profile fields."""
    return CandidateResponse(
        id=str(candidate.id),
        external_id=candidate.external_id,
        name_en=candidate.name_en,
        name_ne=candidate.name_ne,
        name_en_roman=resolved_profile.get("name_en_roman", getattr(candidate, "name_en_roman", None)),
        party=candidate.party,
        party_ne=candidate.party_ne,
        votes=candidate.votes,
        vote_pct=candidate.vote_pct,
        rank=candidate.rank,
        is_winner=candidate.is_winner,
        is_notable=getattr(candidate, "is_notable", None),
        photo_url=candidate.photo_url,
        age=resolved_profile.get("age", candidate.age),
        gender=resolved_profile.get("gender", candidate.gender),
        education=resolved_profile.get("education", candidate.education),
        education_institution=resolved_profile.get("education_institution", candidate.education_institution),
        biography=resolved_profile.get("biography", getattr(candidate, "biography", None)),
        biography_source=resolved_profile.get("biography_source", getattr(candidate, "biography_source", None)),
        biography_source_label=resolved_profile.get("biography_source_label"),
        profile_origin=resolved_profile.get("profile_origin"),
        aliases=resolved_profile.get("aliases", getattr(candidate, "aliases", None)),
        previous_positions=resolved_profile.get("previous_positions", getattr(candidate, "previous_positions", None)),
        linked_entity_id=resolved_profile.get("linked_entity_id"),
        entity_link_confidence=resolved_profile.get("entity_link_confidence", candidate.entity_link_confidence),
        entity_summary=resolved_profile.get("entity_summary"),
    )


# ============== Election Endpoints ==============

@router.get("/", response_model=ElectionListResponse)
async def list_elections(db: AsyncSession = Depends(get_db)):
    """List all elections (2074, 2079, 2082 BS)."""
    service = ElectionService(db)
    elections = await service.get_elections_list()
    return ElectionListResponse(elections=elections)


@router.get("/{year}/results", response_model=NationalSummaryResponse)
async def get_national_results(
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """Get national summary for an election year.

    Returns declared/counting/pending counts, turnout, and party seats.
    """
    service = ElectionService(db)
    summary = await service.get_national_summary(year)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Election year {year} not found")
    return summary


@router.get("/{year}/snapshot", response_model=ElectionSnapshotResponse)
async def get_election_snapshot(
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """Get full election snapshot for unified candidate reads."""
    if settings.unified_candidate_read_mode == "json_only":
        raise HTTPException(
            status_code=503,
            detail="Unified DB snapshot disabled (json_only mode)",
        )

    service = ElectionService(db)
    snapshot = await service.get_election_snapshot(
        year_bs=year,
        source_mode=settings.unified_candidate_read_mode,
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Election year {year} not found")
    return snapshot


# ============== Constituency Endpoints ==============

@router.get("/{year}/constituencies", response_model=ConstituencyListResponse)
async def list_constituencies(
    year: int,
    province: Optional[str] = Query(default=None, description="Filter by province name"),
    province_id: Optional[int] = Query(default=None, ge=1, le=7, description="Filter by province ID (1-7)"),
    district: Optional[str] = Query(default=None, description="Filter by district name"),
    status: Optional[str] = Query(default=None, description="Filter by status (pending/counting/declared)"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List constituencies with optional filters.

    Supports filtering by province, district, and status.
    """
    service = ElectionService(db)
    items, total = await service.get_constituencies(
        year_bs=year,
        province=province,
        province_id=province_id,
        district=district,
        status=status,
        page=page,
        per_page=per_page,
    )

    return ConstituencyListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page) < total,
    )


@router.get("/{year}/constituencies/{code}", response_model=ConstituencyDetailResponse)
async def get_constituency_detail(
    year: int,
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed constituency information with candidates.

    Code format: district-number (e.g., kathmandu-1, lalitpur-2)
    """
    service = ElectionService(db)
    detail = await service.get_constituency_detail(year_bs=year, code=code)
    if not detail:
        raise HTTPException(
            status_code=404,
            detail=f"Constituency '{code}' not found for year {year}",
        )
    return detail


# ============== Map Data Endpoints ==============

@router.get("/{year}/districts", response_model=DistrictMapDataResponse)
async def get_district_map_data(
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """Get district-level election data for map display.

    Returns aggregated data per district including:
    - Total constituencies
    - Declared/counting/pending counts
    - Dominant party (most seats won)
    - Party seat distribution
    - Total votes cast

    Optimized for DistrictPolygonsLayer integration.
    """
    service = ElectionService(db)
    data = await service.get_district_map_data(year)
    if not data:
        raise HTTPException(status_code=404, detail=f"Election year {year} not found")
    return data


# ============== Analytics Endpoints ==============

@router.get("/{year}/swing", response_model=SwingAnalysisResponse)
async def get_swing_analysis(
    year: int,
    vs_year: int = Query(..., description="Previous year to compare against"),
    db: AsyncSession = Depends(get_db),
):
    """Get swing analysis between two election years.

    Compares seat changes for each party between current and previous election.
    """
    service = ElectionService(db)
    analysis = await service.get_swing_analysis(current_year=year, previous_year=vs_year)
    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=f"Could not compute swing analysis for {year} vs {vs_year}",
        )
    return analysis


# ============== Watchlist Endpoints ==============

@router.get("/watchlist", response_model=WatchlistResponse)
async def get_watchlist(
    current_user: User = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Get user's constituency watchlist.

    Returns all tracked constituencies with their current status.
    """
    user_id = str(current_user.id)
    service = ElectionService(db)
    return await service.get_user_watchlist(user_id)


@router.post("/watchlist/{constituency_id}", response_model=WatchlistItemResponse)
async def add_to_watchlist(
    constituency_id: UUID,
    body: WatchlistItemRequest = WatchlistItemRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Add a constituency to user's watchlist.

    Allows tracking specific constituencies during elections.
    """
    user_id = str(current_user.id)
    service = ElectionService(db)

    # Verify constituency exists
    constituency = await service.constituency_repo.get_by_id(constituency_id)
    if not constituency:
        raise HTTPException(status_code=404, detail="Constituency not found")

    return await service.add_to_watchlist(
        user_id=user_id,
        constituency_id=constituency_id,
        alert_level=body.alert_level,
        notes=body.notes,
    )


@router.delete("/watchlist/{constituency_id}")
async def remove_from_watchlist(
    constituency_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Remove a constituency from user's watchlist."""
    user_id = str(current_user.id)
    service = ElectionService(db)

    removed = await service.remove_from_watchlist(user_id, constituency_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    return {"status": "removed", "constituency_id": str(constituency_id)}


@router.get("/watchlist/check/{constituency_id}")
async def check_watchlist(
    constituency_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Check if a constituency is on user's watchlist."""
    user_id = str(current_user.id)
    service = ElectionService(db)

    is_watched = await service.is_on_watchlist(user_id, constituency_id)
    return {"is_on_watchlist": is_watched, "constituency_id": str(constituency_id)}


# ============== Candidate Dossier Endpoints ==============

@router.get("/candidates/{external_id}")
async def get_candidate_detail(
    external_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Compatibility endpoint for legacy candidate detail consumers."""
    service = ElectionService(db)
    candidate = await service.candidate_repo.get_by_external_id(external_id)
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate with ID '{external_id}' not found",
        )

    election = await service.election_repo.get_by_id(candidate.election_id)
    election_year = election.year_bs if election else 2082

    profile_resolver = CandidateProfileResolver(db)
    overrides = await profile_resolver.get_active_overrides_map([candidate.external_id])
    resolved = profile_resolver.resolve_candidate_profile(
        candidate,
        overrides.get(candidate.external_id, {}),
    )

    previous_runs_data = await service.candidate_repo.find_previous_runs(
        name_en=candidate.name_en,
        name_ne=candidate.name_ne,
        current_election_id=candidate.election_id,
        current_year_bs=election_year,
        name_en_roman=getattr(candidate, "name_en_roman", None),
        aliases=getattr(candidate, "aliases", None),
    )

    story_repo = StoryRepository(db)
    stories = await story_repo.search_by_name(
        name=candidate.name_en,
        name_ne=candidate.name_ne,
        hours=720,
        limit=20,
    )

    return {
        "candidate": _candidate_response_with_resolved_profile(candidate, resolved),
        "previous_runs": [
            {
                "election_year": run["election_year"],
                "party_name": run["party_name"],
                "constituency_name": run["constituency_name"],
                "is_winner": run["is_winner"],
                "votes_received": run["votes_received"],
            }
            for run in previous_runs_data
        ],
        "mentions": [
            {
                "story_title": s.title,
                "source_name": s.source_name,
                "published_at": s.published_at,
                "story_url": s.url,
            }
            for s in stories
        ],
    }

@router.get("/candidates/{external_id}/dossier", response_model=CandidateDossierResponse)
async def get_candidate_dossier(
    external_id: str,
    year: int = Query(default=2082, description="Election year (BS)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get candidate intelligence dossier.

    Returns:
    - Candidate details (name, party, votes, education, etc.)
    - Constituency info and rivals
    - Previous election runs
    - Story mention count

    The external_id is the candidate's ID from the election data (e.g., "340111").
    """
    service = ElectionService(db)

    # Get candidate by external_id
    candidate = await service.candidate_repo.get_by_external_id(external_id)
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate with ID '{external_id}' not found",
        )

    # Get constituency with all candidates (for rivals)
    constituency = await service.constituency_repo.get_by_id(candidate.constituency_id)
    if not constituency:
        raise HTTPException(status_code=404, detail="Constituency not found")

    # Get election year for this candidate
    election = await service.election_repo.get_by_id(constituency.election_id)
    election_year = election.year_bs if election else 2082

    # UPGRADE: If this is an older record, try to find the latest version of this person.
    # This ensures clicking a 2079 candidate shows their 2082 data if available.
    is_running_2082 = election_year == 2082
    if not is_running_2082:
        latest_election = await service.election_repo.get_latest()
        if latest_election and latest_election.year_bs > election_year:
            matching_latest = await service.candidate_repo.find_by_name_in_election(
                name_en=candidate.name_en,
                name_ne=candidate.name_ne,
                election_id=latest_election.id,
                constituency_code=constituency.constituency_code,
                name_en_roman=getattr(candidate, 'name_en_roman', None),
                aliases=getattr(candidate, 'aliases', None),
            )
            if matching_latest:
                # Upgrade to the latest record
                candidate = matching_latest
                constituency = await service.constituency_repo.get_by_id(candidate.constituency_id)
                if not constituency:
                    raise HTTPException(status_code=404, detail="Constituency not found")
                election = await service.election_repo.get_by_id(constituency.election_id)
                election_year = election.year_bs if election else latest_election.year_bs
                is_running_2082 = election_year == latest_election.year_bs

    # Get rivals (other candidates in same constituency)
    all_candidates = await service.candidate_repo.list_by_constituency(candidate.constituency_id)
    profile_resolver = CandidateProfileResolver(db)
    overrides = await profile_resolver.get_active_overrides_map(
        [c.external_id for c in all_candidates]
    )
    rivals = [
        _candidate_response_with_resolved_profile(
            c,
            profile_resolver.resolve_candidate_profile(
                c,
                overrides.get(c.external_id, {}),
            ),
        )
        for c in sorted(all_candidates, key=lambda x: x.votes, reverse=True)
        if c.id != candidate.id
    ][:5]

    # Get story count for this candidate
    story_repo = StoryRepository(db)
    stories = await story_repo.search_by_name(
        name=candidate.name_en,
        name_ne=candidate.name_ne,
        hours=720,  # 30 days
        limit=100,
    )
    story_count = len(stories)

    # Get previous election runs
    previous_runs_data = await service.candidate_repo.find_previous_runs(
        name_en=candidate.name_en,
        name_ne=candidate.name_ne,
        current_election_id=candidate.election_id,
        current_year_bs=election_year,
        name_en_roman=getattr(candidate, 'name_en_roman', None),
        aliases=getattr(candidate, 'aliases', None),
    )

    # Calculate rank
    rank = 1
    for c in all_candidates:
        if c.votes > candidate.votes:
            rank += 1

    # Get parliamentary record if linked
    parliamentary_record = None
    mp_repo = MPPerformanceRepository(db)
    mp = await mp_repo.get_by_candidate_id(candidate.id)

    # Fallback: search by name if no direct link (for upcoming elections)
    if not mp and candidate.name_ne:
        mps = await mp_repo.search_by_name(candidate.name_ne, limit=1)
        if mps:
            mp = mps[0]

    if mp:
        parliamentary_record = ParliamentRecordSummary(
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
            speeches_count=getattr(mp, 'speeches_count', 0) or 0,
            peer_group=mp.peer_group,
            peer_rank=mp.peer_rank,
            peer_total=mp.peer_total,
            # Prime Minister history (sourced from OPMCM)
            is_former_pm=getattr(mp, 'is_former_pm', False) or False,
            pm_terms=getattr(mp, 'pm_terms', 0) or 0,
            notable_roles=getattr(mp, 'notable_roles', None),
        )

    return CandidateDossierResponse(
        candidate=_candidate_response_with_resolved_profile(
            candidate,
            profile_resolver.resolve_candidate_profile(
                candidate,
                overrides.get(candidate.external_id, {}),
            ),
        ),
        constituency_code=constituency.constituency_code,
        constituency_name=constituency.name_en,
        district=constituency.district,
        province=constituency.province,
        province_id=constituency.province_id,
        rivals=rivals,
        previous_runs=[
            PreviousRunResponse(
                election_year=run["election_year"],
                party_name=run["party_name"],
                constituency_name=run["constituency_name"],
                is_winner=run["is_winner"],
                votes_received=run["votes_received"],
            )
            for run in previous_runs_data
        ],
        story_count=story_count,
        constituency_rank=rank,
        election_year=election_year,
        is_running_2082=is_running_2082,
        parliamentary_record=parliamentary_record,
    )


@router.get("/candidates/{external_id}/stories", response_model=CandidateStoriesResponse)
async def get_candidate_stories(
    external_id: str,
    hours: int = Query(default=720, ge=1, le=8760, description="Time window in hours"),
    limit: int = Query(default=50, ge=1, le=200, description="Max stories to return"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get news stories mentioning a candidate.

    Searches story titles and content for the candidate's name (EN and NE).
    Returns stories sorted by publication date.
    """
    service = ElectionService(db)

    # Get candidate
    candidate = await service.candidate_repo.get_by_external_id(external_id)
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate with ID '{external_id}' not found",
        )

    # Search stories mentioning this candidate
    story_repo = StoryRepository(db)
    stories = await story_repo.search_by_name(
        name=candidate.name_en,
        name_ne=candidate.name_ne,
        hours=hours,
        limit=limit,
        category=category,
    )

    return CandidateStoriesResponse(
        candidate_id=external_id,
        candidate_name=candidate.name_en,
        stories=[
            StoryMentionResponse(
                story_id=str(s.id),
                story_title=s.title,
                story_url=s.url,
                published_at=s.published_at,
                source_name=s.source_name,
                category=s.category,
                severity=s.severity,
            )
            for s in stories
        ],
        total=len(stories),
        hours=hours,
    )


@router.get("/candidates/{external_id}/wikileaks", response_model=CandidateWikiLeaksResponse)
async def get_candidate_wikileaks(
    external_id: str,
    max_results: int = Query(default=20, ge=1, le=50, description="Max documents to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search WikiLeaks for diplomatic cables and leaked documents mentioning a candidate.

    This searches the WikiLeaks public archive for documents related to the candidate,
    including diplomatic cables from Cable Gate and other leaked documents.

    Results are cached for 24 hours to avoid excessive requests.

    **Use cases:**
    - Find diplomatic context about senior politicians
    - Uncover international perspectives on candidates
    - Research historical intelligence on public figures
    """
    service = ElectionService(db)

    # Get candidate
    candidate = await service.candidate_repo.get_by_external_id(external_id)
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate with ID '{external_id}' not found",
        )

    # WikiLeaks search excluded from skeleton
    raise HTTPException(
        status_code=501,
        detail="WikiLeaks search not available in open-source skeleton",
    )

    return CandidateWikiLeaksResponse(
        candidate_id=external_id,
        candidate_name=candidate.name_en,
        query="",
        documents=[
            WikiLeaksDocumentResponse(
                title="",
                url=doc.url,
                collection=doc.collection,
                snippet=doc.snippet,
                date_created=doc.date_created,
                date_released=doc.date_released,
                relevance_score=doc.relevance_score,
            )
            for doc in result.documents
        ],
        total_results=result.total_results,
        searched_at=result.searched_at,
        cache_hit=result.cache_hit,
    )


# ============== AI Leadership Profile ==============

@router.get("/candidates/{external_id}/profile", response_model=LeadershipProfileResponse)
async def get_candidate_leadership_profile(
    external_id: str,
    force_regenerate: bool = Query(default=False, description="Force regenerate (ignore cache)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get AI-generated leadership profile for a candidate.

    Uses Claude Haiku to synthesize all available data into an actionable
    intelligence product answering: "What kind of leader is this person?"

    **Data sources analyzed:**
    - Education and qualifications
    - Election history and performance
    - Parliamentary record (if available)
    - News mentions and sentiment
    - WikiLeaks diplomatic cables (if available)

    **Output includes:**
    - Leadership style classification
    - Key strengths and concerns
    - Policy priorities
    - Controversy summary
    - International perception (from WikiLeaks)
    - Executive summary

    Results are cached for 24 hours. Use `force_regenerate=true` to refresh.
    """
    service = ElectionService(db)

    # Get candidate
    candidate = await service.candidate_repo.get_by_external_id(external_id)
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate with ID '{external_id}' not found",
        )

    # Get constituency
    constituency = await service.constituency_repo.get_by_id(candidate.constituency_id)
    constituency_name = f"{constituency.name_en}, {constituency.district}" if constituency else None

    # Get election year for previous runs filtering
    election = await service.election_repo.get_by_id(candidate.election_id)
    profile_election_year = election.year_bs if election else 2082

    # Get election history (previous runs)
    previous_runs = await service.candidate_repo.find_previous_runs(
        name_en=candidate.name_en,
        name_ne=candidate.name_ne,
        current_election_id=candidate.election_id,
        current_year_bs=profile_election_year,
        name_en_roman=getattr(candidate, 'name_en_roman', None),
        aliases=getattr(candidate, 'aliases', None),
    )
    election_history = [
        {
            "election_year": run["election_year"],
            "party_name": run["party_name"],
            "constituency_name": run["constituency_name"],
            "votes_received": run["votes_received"],
            "is_winner": run["is_winner"],
        }
        for run in previous_runs
    ]

    # Get parliamentary record
    mp_repo = MPPerformanceRepository(db)
    mp = await mp_repo.get_by_candidate_id(candidate.id)
    if not mp and candidate.name_ne:
        mps = await mp_repo.search_by_name(candidate.name_ne, limit=1)
        if mps:
            mp = mps[0]

    parliamentary_record = None
    if mp:
        parliamentary_record = {
            "performance_score": mp.performance_score,
            "bills_introduced": mp.bills_introduced,
            "questions_asked": mp.questions_asked,
            "speeches_count": getattr(mp, 'speeches_count', 0) or 0,
            "committee_memberships": mp.committee_memberships,
            "is_former_pm": getattr(mp, 'is_former_pm', False) or False,
            "pm_terms": getattr(mp, 'pm_terms', 0) or 0,
            "notable_roles": getattr(mp, 'notable_roles', None),
        }

    # Get recent news stories
    story_repo = StoryRepository(db)
    stories = await story_repo.search_by_name(
        name=candidate.name_en,
        name_ne=candidate.name_ne,
        hours=720,  # 30 days
        limit=30,
    )
    news_stories = [
        {
            "title": s.title,
            "category": getattr(s, 'category', 'general'),
            "source_name": getattr(s, 'source_name', None),
            "published_at": s.published_at.isoformat() if s.published_at else None,
        }
        for s in stories
    ]

    # Get WikiLeaks documents
    wikileaks_docs = []
    try:
        # WikiLeaks search excluded from skeleton
        wikileaks_docs = [
            {
                "title": doc.title,
                "collection": doc.collection,
                "snippet": doc.snippet,
            }
            for doc in result.documents
        ]
    except Exception as e:
        # WikiLeaks is optional, don't fail if unavailable
        import logging
        logging.getLogger(__name__).warning(f"WikiLeaks search failed: {e}")

    # Get ministerial positions (executive branch experience)
    ministerial_positions = []
    try:
        ministerial_repo = MinisterialPositionRepository(db)
        positions = await ministerial_repo.search_by_name(
            name_en=candidate.name_en,
            name_ne=candidate.name_ne,
            limit=20,
        )
        ministerial_positions = [
            {
                "position_type": pos.position_type,
                "ministry": pos.ministry,
                "start_date": pos.start_date.isoformat() if pos.start_date else None,
                "end_date": pos.end_date.isoformat() if pos.end_date else None,
                "is_current": pos.is_current,
                "government_name": pos.government_name,
                "prime_minister": pos.prime_minister,
                "party_at_appointment": pos.party_at_appointment,
                "notes": pos.notes,
            }
            for pos in positions
        ]
        if ministerial_positions:
            import logging
            logging.getLogger(__name__).info(
                f"Found {len(ministerial_positions)} ministerial positions for {candidate.name_en}"
            )
    except Exception as e:
        # Ministerial positions are optional, don't fail if unavailable
        import logging
        logging.getLogger(__name__).warning(f"Ministerial positions lookup failed: {e}")

    # AI profile generation excluded from skeleton
    raise HTTPException(
        status_code=501,
        detail="Leadership profile generation not available in open-source skeleton",
    )

    from datetime import datetime as dt
    profile = await generate_leadership_profile(
        candidate_id=external_id,
        candidate_name=candidate.name_en,
        candidate_name_ne=candidate.name_ne,
        education=candidate.education,
        party=candidate.party,
        age=candidate.age,
        gender=candidate.gender,
        constituency=constituency_name,
        election_history=election_history,
        parliamentary_record=parliamentary_record,
        news_stories=news_stories,
        wikileaks_docs=wikileaks_docs,
        ministerial_positions=ministerial_positions,
        force_regenerate=force_regenerate,
    )

    return LeadershipProfileResponse(
        candidate_id=profile.candidate_id,
        candidate_name=profile.candidate_name,
        leadership_style=profile.leadership_style,
        key_strengths=profile.key_strengths,
        key_concerns=profile.key_concerns,
        ideological_position=profile.ideological_position,
        policy_priorities=profile.policy_priorities,
        experience_summary=profile.experience_summary,
        controversy_summary=profile.controversy_summary,
        international_perception=profile.international_perception,
        analyst_summary=profile.analyst_summary,
        confidence_level=profile.confidence_level,
        generated_at=dt.fromisoformat(profile.generated_at),
        data_sources=profile.data_sources,
        cache_hit=not force_regenerate and profile.generated_at != dt.utcnow().isoformat()[:10],
    )


# ============== Candidate Correction Submission (Authenticated) ==============

@router.post("/candidates/{external_id}/corrections")
async def submit_candidate_correction(
    external_id: str,
    request: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submit a correction suggestion for a candidate. Any authenticated user.

    Body: { "field": "name_en_roman", "new_value": "...", "reason": "..." }
    """
    field = request.get("field", "")
    new_value = request.get("new_value", "")
    reason = request.get("reason", "")

    if not field or not new_value or not reason:
        raise HTTPException(status_code=400, detail="field, new_value, and reason are required")
    if len(reason) < 10:
        raise HTTPException(status_code=400, detail="Reason must be at least 10 characters")

    # Correction service excluded from skeleton
    raise HTTPException(
        status_code=501,
        detail="Candidate corrections not available in open-source skeleton",
    )
