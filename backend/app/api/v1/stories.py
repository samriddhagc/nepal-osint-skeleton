"""Stories API endpoints."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_dev
from app.models.story import Story
from app.repositories.story import StoryRepository
from app.schemas.story import StoryResponse, StoryListResponse

router = APIRouter(prefix="/stories", tags=["stories"])


def _parse_districts_param(districts_param: Optional[str]) -> List[str]:
    """
    Parse comma-separated districts parameter into a list.
    Returns empty list if None or empty.
    Normalizes to proper case for matching.
    """
    if not districts_param:
        return []
    return [d.strip().title() for d in districts_param.split(",") if d.strip()]


def _filter_stories_by_districts(
    stories: List,
    districts: List[str],
) -> List:
    """
    Filter stories by district names.
    Checks both the story.districts field and falls back to title matching.
    """
    if not districts:
        return stories

    districts_lower = [d.lower() for d in districts]

    filtered = []
    for story in stories:
        # Check the districts field on the story
        if story.districts:
            story_districts_lower = [d.lower() for d in story.districts]
            if any(d in story_districts_lower for d in districts_lower):
                filtered.append(story)
                continue

        # Fallback: check if district name appears in title
        title_lower = story.title.lower()
        if any(d in title_lower for d in districts_lower):
            filtered.append(story)

    return filtered


@router.get("", response_model=StoryListResponse)
async def list_stories(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    source_id: Optional[str] = Query(None, description="Filter by source ID"),
    source_ids: Optional[str] = Query(
        None,
        description="Comma-separated source IDs (multi-select filter)",
    ),
    category: Optional[str] = Query(None, description="Filter by story category"),
    from_date: Optional[datetime] = Query(None, description="Stories after this date"),
    to_date: Optional[datetime] = Query(None, description="Stories before this date"),
    nepal_only: bool = Query(True, description="Only Nepal-relevant stories"),
    multi_source_only: bool = Query(
        False,
        description="Only stories belonging to clusters with source_count > 1",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    List stories with pagination and filtering.

    By default, returns only Nepal-relevant stories.
    """
    repo = StoryRepository(db)
    parsed_source_ids = (
        [source.strip() for source in source_ids.split(",") if source.strip()]
        if source_ids
        else None
    )
    stories, total = await repo.list_stories(
        page=page,
        page_size=page_size,
        source_id=source_id,
        source_ids=parsed_source_ids,
        category=category,
        from_date=from_date,
        to_date=to_date,
        nepal_only=nepal_only,
        multi_source_only=multi_source_only,
    )

    return StoryListResponse(
        items=[StoryResponse.model_validate(s) for s in stories],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/sources")
async def list_story_sources(
    category: Optional[str] = Query(None, description="Optional category filter"),
    from_date: Optional[datetime] = Query(None, description="Source activity after this date"),
    to_date: Optional[datetime] = Query(None, description="Source activity before this date"),
    nepal_only: bool = Query(True, description="Only Nepal-relevant stories"),
    multi_source_only: bool = Query(
        False,
        description="Only sources having multi-source-cluster stories in the filter window",
    ),
    limit: int = Query(200, ge=1, le=500, description="Maximum source rows to return"),
    db: AsyncSession = Depends(get_db),
):
    """List distinct story sources and counts for stories feed filtering."""
    repo = StoryRepository(db)
    return await repo.list_sources(
        category=category,
        from_date=from_date,
        to_date=to_date,
        nepal_only=nepal_only,
        multi_source_only=multi_source_only,
        limit=limit,
    )


@router.get("/recent")
async def get_recent_stories(
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    limit: int = Query(50, ge=1, le=200, description="Max stories to return"),
    districts: Optional[str] = Query(None, description="Comma-separated district names to filter by"),
    db: AsyncSession = Depends(get_db),
):
    """Get recent Nepal-relevant stories, optionally filtered by districts."""
    repo = StoryRepository(db)

    # Parse districts parameter
    district_list = _parse_districts_param(districts)

    # Fetch more stories if filtering by district
    fetch_limit = limit * 3 if district_list else limit

    stories = await repo.get_recent(hours=hours, limit=fetch_limit, nepal_only=True)

    # Filter by districts if specified
    if district_list:
        stories = _filter_stories_by_districts(stories, district_list)
        stories = stories[:limit]

    return [StoryResponse.model_validate(s) for s in stories]


@router.get("/export")
async def export_stories_for_agent(
    hours: int = Query(4, ge=1, le=48, description="Time window in hours"),
    limit: int = Query(200, ge=1, le=1000, description="Max stories"),
    db: AsyncSession = Depends(get_db),
):
    """Export stories with metadata for external analysis.

    Returns stories with basic metadata and cluster info.
    """
    from sqlalchemy import desc
    from datetime import timezone, timedelta

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(Story)
        .where(Story.created_at >= since)
        .order_by(desc(func.coalesce(Story.published_at, Story.created_at)))
        .limit(limit)
    )
    stories = result.scalars().all()

    items = []
    for s in stories:
        items.append({
            "id": str(s.id),
            "title": s.title,
            "source_name": s.source_name or s.source_id,
            "published_at": s.published_at.isoformat() if s.published_at else None,
            "category": s.category,
            "severity": s.severity,
            "nepal_relevance": s.nepal_relevance,
            "ai_summary": s.ai_summary,
            "provinces": s.provinces,
            "districts": s.districts or [],
            "cluster_id": str(s.cluster_id) if s.cluster_id else None,
        })

    return {"stories": items, "total": len(items), "since": since.isoformat()}


# ── Local Haiku runner endpoints (must be before /{story_id} catch-all) ──

class HaikuResultItem(BaseModel):
    story_id: str
    relevant: Optional[bool] = None
    ai_summary: Optional[dict] = None


class HaikuResultsPayload(BaseModel):
    task: str
    results: List[HaikuResultItem]


@router.get("/pending-haiku", dependencies=[Depends(require_dev)])
async def get_pending_haiku(
    limit: int = Query(20, ge=1, le=100),
    task: str = Query("relevance", description="relevance or summary"),
    db: AsyncSession = Depends(get_db),
):
    """Get stories needing Haiku processing (for local CLI runner)."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)

    if task == "relevance":
        cutoff = now - timedelta(hours=6)
        stmt = (
            select(Story.id, Story.title, Story.summary, Story.source_name,
                   Story.relevance_score, Story.relevance_triggers)
            .where(Story.created_at >= cutoff)
            .where(Story.relevance_score < 0.75)
            .where(Story.ai_summary.is_(None))
            .order_by(Story.created_at.desc())
            .limit(limit)
        )
    else:
        cutoff = now - timedelta(hours=12)
        stmt = (
            select(Story.id, Story.title, Story.summary, Story.source_name,
                   Story.category, Story.severity)
            .where(Story.created_at >= cutoff)
            .where(Story.nepal_relevance == "NEPAL_DOMESTIC")
            .where(Story.ai_summary.is_(None))
            .order_by(Story.created_at.desc())
            .limit(limit)
        )

    result = await db.execute(stmt)
    rows = result.all()
    return {
        "task": task,
        "count": len(rows),
        "stories": [
            {"id": str(r.id), "title": r.title, "summary": r.summary, "source_name": r.source_name}
            for r in rows
        ],
    }


@router.post("/haiku-results", dependencies=[Depends(require_dev)])
async def post_haiku_results(
    payload: HaikuResultsPayload,
    db: AsyncSession = Depends(get_db),
):
    """Ingest Haiku results from local CLI runner."""
    updated = 0
    now = datetime.now(timezone.utc)

    for item in payload.results:
        try:
            sid = UUID(item.story_id)
        except ValueError:
            continue

        if payload.task == "relevance" and item.relevant is not None:
            if not item.relevant:
                await db.execute(
                    update(Story).where(Story.id == sid).values(nepal_relevance="INTERNATIONAL")
                )
            updated += 1
        elif payload.task == "summary" and item.ai_summary:
            await db.execute(
                update(Story).where(Story.id == sid).values(ai_summary=item.ai_summary, ai_summary_at=now)
            )
            updated += 1

    await db.commit()
    return {"task": payload.task, "updated": updated, "total": len(payload.results)}


@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(
    story_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single story by ID."""
    repo = StoryRepository(db)
    story = await repo.get_by_id(story_id)

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    return StoryResponse.model_validate(story)


