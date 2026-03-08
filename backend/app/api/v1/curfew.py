"""Curfew alerts API endpoints."""
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_dev
from app.core.database import get_db
from app.repositories.curfew import CurfewRepository

router = APIRouter(prefix="/curfew", tags=["Curfew Alerts"])


# ============ Response Schemas ============

class CurfewAlertResponse(BaseModel):
    """Curfew alert response."""
    id: str
    district: str
    province: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    source_name: Optional[str] = None
    matched_keywords: List[str] = []
    detected_at: str
    expires_at: Optional[str] = None
    is_active: bool = True
    is_confirmed: bool = False
    severity: Optional[str] = None
    hours_remaining: Optional[float] = None


class ActiveCurfewsResponse(BaseModel):
    """Active curfews response."""
    alerts: List[CurfewAlertResponse]
    districts: List[str]
    count: int


class CurfewMapData(BaseModel):
    """Curfew map data for polygon highlighting."""
    districts: List[str]
    count: int


@router.get("/active", response_model=ActiveCurfewsResponse)
async def get_active_curfews(
    db: AsyncSession = Depends(get_db),
):
    """Get all active curfew alerts."""
    repo = CurfewRepository(db)
    alerts = await repo.get_active()

    return ActiveCurfewsResponse(
        alerts=[
            CurfewAlertResponse(
                id=str(a.id),
                district=a.district,
                province=a.province,
                title=a.title,
                source=a.source,
                source_name=a.source_name,
                matched_keywords=a.matched_keywords or [],
                detected_at=a.detected_at.isoformat() if a.detected_at else "",
                expires_at=a.expires_at.isoformat() if a.expires_at else "",
                is_active=a.is_active,
                is_confirmed=a.is_confirmed,
                severity=a.severity,
                hours_remaining=a.hours_remaining,
            )
            for a in alerts
        ],
        districts=[a.district for a in alerts],
        count=len(alerts),
    )


@router.get("/map-data", response_model=CurfewMapData)
async def get_curfew_map_data(
    db: AsyncSession = Depends(get_db),
):
    """Get curfew data optimized for map visualization."""
    repo = CurfewRepository(db)
    alerts = await repo.get_active()

    return CurfewMapData(
        districts=[a.district for a in alerts],
        count=len(alerts),
    )
