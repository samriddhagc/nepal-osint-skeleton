"""API endpoints for situation briefs (Analyst Agent output)."""
from typing import Optional
from uuid import UUID
import json

import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError, OperationalError

from app.api.deps import get_db, require_dev
from app.repositories.brief_repository import BriefRepository
from app.models.situation_brief import SituationBrief, ProvinceSitrep, FakeNewsFlag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefs", tags=["briefs"])


# ── Response schemas ──


class HotspotResponse(BaseModel):
    province: Optional[str] = None
    district: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    confidence: Optional[str] = None


class FlagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    story_id: Optional[UUID] = None
    headline: str
    source_name: Optional[str] = None
    flag_reason: str
    verdict: Optional[str] = None
    verdict_reasoning: Optional[str] = None
    confidence: Optional[float] = None
    created_at: datetime


class SitrepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    province_id: int
    province_name: str
    bluf: Optional[str] = None
    security: Optional[str] = None
    political: Optional[str] = None
    economic: Optional[str] = None
    disaster: Optional[str] = None
    election: Optional[str] = None
    threat_level: Optional[str] = None
    threat_trajectory: Optional[str] = None
    hotspots: Optional[list] = None
    flagged_stories: Optional[list] = None
    story_count: int = 0
    created_at: datetime


class BriefSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_number: int
    period_start: datetime
    period_end: datetime
    national_summary: Optional[str] = None
    trend_vs_previous: Optional[str] = None
    key_judgment: Optional[str] = None
    stories_analyzed: int = 0
    clusters_analyzed: int = 0
    claude_calls: int = 0
    duration_seconds: Optional[float] = None
    status: str
    created_at: datetime


class BriefDetailResponse(BriefSummaryResponse):
    national_analysis: Optional[dict] = None
    hotspots: Optional[list] = None
    province_sitreps: list[SitrepResponse] = []
    fake_news_flags: list[FlagResponse] = []


# ── Ingest schemas (for local agent → VPS pipeline) ──


class SitrepIngest(BaseModel):
    """Province SITREP data from local agent."""
    province_id: int = Field(ge=0, le=7)
    province_name: str
    bluf: Optional[str] = None
    security: Optional[str] = None
    political: Optional[str] = None
    economic: Optional[str] = None
    disaster: Optional[str] = None
    election: Optional[str] = None
    threat_level: Optional[str] = None
    threat_trajectory: Optional[str] = None
    hotspots: Optional[list] = None
    flagged_stories: Optional[list] = None
    story_count: int = 0


class FlagIngest(BaseModel):
    """Fake news flag data from local agent."""
    story_id: Optional[str] = None
    headline: str
    source_name: Optional[str] = None
    flag_reason: str
    evidence: Optional[dict] = None
    verdict: Optional[str] = None
    verdict_reasoning: Optional[str] = None
    confidence: Optional[float] = None


class BriefIngest(BaseModel):
    """Complete brief payload from local agent."""
    period_start: datetime
    period_end: datetime
    national_summary: Optional[str] = None
    national_analysis: Optional[dict] = None
    hotspots: Optional[list] = None
    trend_vs_previous: Optional[str] = "stable"
    key_judgment: Optional[str] = None
    stories_analyzed: int = 0
    clusters_analyzed: int = 0
    claude_calls: int = 0
    duration_seconds: Optional[float] = None
    province_sitreps: list[SitrepIngest] = []
    fake_news_flags: list[FlagIngest] = []


# ── Endpoints ──


@router.get("/latest", response_model=Optional[BriefDetailResponse])
async def get_latest_brief(db: AsyncSession = Depends(get_db)):
    """Get the most recent completed situation brief."""
    try:
        repo = BriefRepository(db)
        brief = await repo.get_latest()
        if not brief:
            return None
        return BriefDetailResponse.model_validate(brief)
    except (ProgrammingError, OperationalError):
        # Table doesn't exist yet (migration not run) — return null gracefully
        logger.warning("situation_briefs table not found — run migration 052")
        return None


@router.get("/history", response_model=list[BriefSummaryResponse])
async def list_brief_history(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get situation brief history."""
    try:
        repo = BriefRepository(db)
        briefs = await repo.list_history(limit=limit)
        return [BriefSummaryResponse.model_validate(b) for b in briefs]
    except (ProgrammingError, OperationalError):
        return []


@router.get("/flags", response_model=list[FlagResponse])
async def list_fake_news_flags(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get recent fake news flags."""
    try:
        repo = BriefRepository(db)
        flags = await repo.list_recent_flags(limit=limit)
        return [FlagResponse.model_validate(f) for f in flags]
    except (ProgrammingError, OperationalError):
        return []


@router.get("/province/{province_id}", response_model=Optional[SitrepResponse])
async def get_province_sitrep(
    province_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get the latest SITREP for a specific province (1-7)."""
    if province_id < 0 or province_id > 7:
        raise HTTPException(status_code=400, detail="Province ID must be 0-7")
    try:
        repo = BriefRepository(db)
        sitrep = await repo.get_province_sitrep(province_id)
        if not sitrep:
            return None
        return SitrepResponse.model_validate(sitrep)
    except (ProgrammingError, OperationalError):
        return None


@router.get("/{brief_id}", response_model=BriefDetailResponse)
async def get_brief(
    brief_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific situation brief by ID."""
    try:
        repo = BriefRepository(db)
        brief = await repo.get_by_id(brief_id)
        if not brief:
            raise HTTPException(status_code=404, detail="Brief not found")
        return BriefDetailResponse.model_validate(brief)
    except (ProgrammingError, OperationalError):
        raise HTTPException(status_code=404, detail="Brief not found")


# ── Ingest endpoint (local agent → VPS) ──


@router.post("/ingest", response_model=BriefDetailResponse)
async def ingest_brief(
    payload: BriefIngest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_dev),
):
    """Ingest a completed situation brief from a local agent.

    Accepts the full brief with province sitreps and fake news flags,
    assigns a run_number, persists to DB, and publishes Redis notification.
    Requires dev role authentication.
    """
    try:
        # Get next run number
        result = await db.execute(
            select(func.coalesce(func.max(SituationBrief.run_number), 0))
        )
        next_run = (result.scalar() or 0) + 1

        # Create the brief
        brief = SituationBrief(
            run_number=next_run,
            period_start=payload.period_start,
            period_end=payload.period_end,
            national_summary=payload.national_summary,
            national_analysis=payload.national_analysis,
            hotspots=payload.hotspots,
            trend_vs_previous=payload.trend_vs_previous or "stable",
            key_judgment=payload.key_judgment,
            stories_analyzed=payload.stories_analyzed,
            clusters_analyzed=payload.clusters_analyzed,
            claude_calls=payload.claude_calls,
            duration_seconds=payload.duration_seconds,
            status="completed",
        )
        db.add(brief)
        await db.flush()

        # Create province sitreps
        for s in payload.province_sitreps:
            sitrep = ProvinceSitrep(
                brief_id=brief.id,
                province_id=s.province_id,
                province_name=s.province_name,
                bluf=s.bluf,
                security=s.security,
                political=s.political,
                economic=s.economic,
                disaster=s.disaster,
                election=s.election,
                threat_level=s.threat_level,
                threat_trajectory=s.threat_trajectory,
                hotspots=s.hotspots,
                flagged_stories=s.flagged_stories,
                story_count=s.story_count,
            )
            db.add(sitrep)

        # Create fake news flags
        for f in payload.fake_news_flags:
            story_uuid = None
            if f.story_id:
                try:
                    story_uuid = UUID(f.story_id)
                except (ValueError, TypeError):
                    pass

            flag = FakeNewsFlag(
                brief_id=brief.id,
                story_id=story_uuid,
                headline=f.headline,
                source_name=f.source_name,
                flag_reason=f.flag_reason,
                evidence=f.evidence,
                verdict=f.verdict,
                verdict_reasoning=f.verdict_reasoning,
                confidence=f.confidence,
            )
            db.add(flag)

        await db.commit()

        # Notify via Redis
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            await redis.publish("news:updates", json.dumps({
                "type": "situation_brief",
                "brief_id": str(brief.id),
                "run_number": brief.run_number,
                "national_summary": brief.national_summary,
                "trend": brief.trend_vs_previous,
                "status": "completed",
                "source": "local_agent",
            }))
        except Exception as e:
            logger.warning("Redis notification failed: %s", e)

        logger.info(
            "Ingested brief #%d from local agent: %d sitreps, %d flags",
            next_run, len(payload.province_sitreps), len(payload.fake_news_flags),
        )

        # Reload with relationships for response
        repo = BriefRepository(db)
        brief = await repo.get_by_id(brief.id)
        return BriefDetailResponse.model_validate(brief)

    except (ProgrammingError, OperationalError) as e:
        logger.error("DB error ingesting brief: %s", e)
        raise HTTPException(status_code=500, detail="Database error")
