"""Disaster API endpoints for BIPAD Portal integration."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_dev
from app.repositories.disaster import DisasterIncidentRepository, DisasterAlertRepository
from app.services.disaster_service import DisasterIngestionService
from app.schemas.disaster import (
    DisasterIncidentResponse,
    DisasterIncidentListResponse,
    DisasterAlertResponse,
    DisasterAlertListResponse,
    DisasterSummaryResponse,
    SignificantIncidentResponse,
    IngestionStatsResponse,
    MapEventsResponse,
)

router = APIRouter(prefix="/disasters", tags=["disasters"])


# ============== Incident Endpoints ==============

@router.get("/incidents", response_model=DisasterIncidentListResponse)
async def list_incidents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    hazard_type: Optional[str] = Query(None, description="Filter by hazard type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    district: Optional[str] = Query(None, description="Filter by district"),
    from_date: Optional[datetime] = Query(None, description="Incidents after this date"),
    to_date: Optional[datetime] = Query(None, description="Incidents before this date"),
    db: AsyncSession = Depends(get_db),
):
    """
    List disaster incidents with pagination and filtering.

    Filter by hazard type (flood, landslide, earthquake, etc.),
    severity (critical, high, medium, low), or district.
    """
    repo = DisasterIncidentRepository(db)
    incidents, total = await repo.list_incidents(
        page=page,
        page_size=page_size,
        hazard_type=hazard_type,
        severity=severity,
        district=district,
        from_date=from_date,
        to_date=to_date,
    )

    return DisasterIncidentListResponse(
        items=[DisasterIncidentResponse.model_validate(i) for i in incidents],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/incidents/recent")
async def get_recent_incidents(
    hours: int = Query(72, ge=1, le=720, description="Time window in hours"),
    limit: int = Query(50, ge=1, le=200, description="Max incidents to return"),
    hazard_type: Optional[str] = Query(None, description="Filter by hazard type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    db: AsyncSession = Depends(get_db),
):
    """Get recent disaster incidents within time window."""
    repo = DisasterIncidentRepository(db)
    incidents = await repo.get_recent(
        hours=hours,
        limit=limit,
        hazard_type=hazard_type,
        severity=severity,
    )

    return [DisasterIncidentResponse.model_validate(i) for i in incidents]


@router.get("/incidents/significant")
async def get_significant_incidents(
    hours: int = Query(168, ge=1, le=720, description="Time window in hours (default 7 days)"),
    limit: int = Query(50, ge=1, le=100, description="Max incidents to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get significant incidents: deaths > 0 OR estimated_loss > 25 lakhs NPR.

    These are the incidents that meet the user-defined significance threshold.
    """
    repo = DisasterIncidentRepository(db)
    incidents = await repo.get_significant_incidents(hours=hours, limit=limit)

    return [DisasterIncidentResponse.model_validate(i) for i in incidents]


@router.get("/incidents/{incident_id}", response_model=DisasterIncidentResponse)
async def get_incident(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single disaster incident by ID."""
    repo = DisasterIncidentRepository(db)
    incident = await repo.get_by_id(incident_id)

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return DisasterIncidentResponse.model_validate(incident)


# ============== Alert Endpoints ==============

@router.get("/alerts", response_model=DisasterAlertListResponse)
async def list_alerts(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    alert_level: Optional[str] = Query(None, description="Filter by alert level"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    district: Optional[str] = Query(None, description="Filter by district"),
    db: AsyncSession = Depends(get_db),
):
    """
    List disaster alerts with pagination and filtering.

    Alert types: earthquake, river_alert, early_warning, weather_warning
    Alert levels: critical, high, medium, low
    """
    repo = DisasterAlertRepository(db)
    alerts, total = await repo.list_alerts(
        page=page,
        page_size=page_size,
        alert_type=alert_type,
        alert_level=alert_level,
        is_active=is_active,
        district=district,
    )

    return DisasterAlertListResponse(
        items=[DisasterAlertResponse.model_validate(a) for a in alerts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/alerts/active")
async def get_active_alerts(
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    alert_level: Optional[str] = Query(None, description="Filter by alert level"),
    limit: int = Query(50, ge=1, le=100, description="Max alerts to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get currently active disaster alerts."""
    repo = DisasterAlertRepository(db)
    alerts = await repo.get_active_alerts(
        alert_type=alert_type,
        alert_level=alert_level,
        limit=limit,
    )

    return [DisasterAlertResponse.model_validate(a) for a in alerts]


@router.get("/alerts/earthquakes")
async def get_recent_earthquakes(
    hours: int = Query(24, ge=1, le=720, description="Time window in hours"),
    min_magnitude: float = Query(4.0, ge=0, le=10, description="Minimum magnitude"),
    limit: int = Query(50, ge=1, le=100, description="Max earthquakes to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get recent earthquakes above minimum magnitude."""
    repo = DisasterAlertRepository(db)
    alerts = await repo.get_recent_earthquakes(
        hours=hours,
        min_magnitude=min_magnitude,
        limit=limit,
    )

    return [DisasterAlertResponse.model_validate(a) for a in alerts]


@router.get("/alerts/{alert_id}", response_model=DisasterAlertResponse)
async def get_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single disaster alert by ID."""
    repo = DisasterAlertRepository(db)
    alert = await repo.get_by_id(alert_id)

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return DisasterAlertResponse.model_validate(alert)


# ============== Map Endpoints ==============

@router.get("/map/events", response_model=MapEventsResponse)
async def get_map_events(
    hours: int = Query(72, ge=1, le=720, description="Time window in hours"),
    incident_limit: int = Query(200, ge=1, le=500, description="Max incidents"),
    alert_limit: int = Query(100, ge=1, le=200, description="Max alerts"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all disaster events for map display.

    Returns incidents and alerts with coordinates in [longitude, latitude] format
    suitable for Leaflet map rendering.
    """
    service = DisasterIngestionService(db)
    events = await service.get_map_events(
        hours=hours,
        incident_limit=incident_limit,
        alert_limit=alert_limit,
    )

    return events


# ============== Summary Endpoints ==============

@router.get("/summary", response_model=DisasterSummaryResponse)
async def get_summary(
    hours: int = Query(168, ge=1, le=720, description="Time window in hours (default 7 days)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get summary statistics for disasters.

    Includes total incidents/alerts, breakdowns by type and severity,
    total casualties, and economic loss.
    """
    service = DisasterIngestionService(db)
    return await service.get_summary(hours=hours)


# ============== Ingestion Endpoints ==============

@router.post("/ingest", response_model=IngestionStatsResponse, dependencies=[Depends(require_dev)])
async def trigger_ingestion(
    incident_limit: int = Query(100, ge=1, le=500, description="Max incidents to fetch"),
    earthquake_limit: int = Query(50, ge=1, le=200, description="Max earthquakes to fetch"),
    days_back: int = Query(30, ge=1, le=365, description="Fetch incidents from last N days"),
    filter_insignificant: bool = Query(True, description="Only store significant incidents"),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger BIPAD Portal ingestion.

    By default, only stores significant incidents (deaths > 0 OR loss > 25 lakhs NPR).
    Set filter_insignificant=false to store all incidents.
    """
    service = DisasterIngestionService(db)
    stats = await service.ingest_all(
        incident_limit=incident_limit,
        earthquake_limit=earthquake_limit,
        incident_days_back=days_back,
        filter_insignificant=filter_insignificant,
    )

    return IngestionStatsResponse(**stats)
