"""Seismic activity API - earthquake data from BIPAD Portal."""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.disaster import DisasterAlert

router = APIRouter(prefix="/seismic", tags=["seismic"])


@router.get("/stats")
async def get_seismic_stats(
    hours: int = Query(default=24, ge=1, le=168, description="Hours to look back"),
    min_magnitude: float = Query(default=0.0, ge=0.0, le=10.0, description="Minimum magnitude filter"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get seismic activity statistics from BIPAD earthquake data.

    Returns:
    - events_24h: Total earthquake events in the time window
    - max_magnitude: Highest magnitude recorded
    - avg_depth: Average depth in km
    - recent_events: List of recent earthquakes with details
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Build base query for earthquakes
    base_filter = and_(
        DisasterAlert.alert_type == "earthquake",
        DisasterAlert.issued_at >= cutoff,
    )

    if min_magnitude > 0:
        base_filter = and_(base_filter, DisasterAlert.magnitude >= min_magnitude)

    # Get aggregate stats
    stats_query = select(
        func.count(DisasterAlert.id).label("count"),
        func.max(DisasterAlert.magnitude).label("max_mag"),
        func.avg(DisasterAlert.magnitude).label("avg_mag"),
        func.avg(DisasterAlert.depth_km).label("avg_depth"),
    ).where(base_filter)

    stats_result = await db.execute(stats_query)
    stats_row = stats_result.one()

    event_count = stats_row.count or 0
    max_magnitude = round(float(stats_row.max_mag), 1) if stats_row.max_mag else 0.0
    avg_magnitude = round(float(stats_row.avg_mag), 1) if stats_row.avg_mag else 0.0
    avg_depth = round(float(stats_row.avg_depth), 1) if stats_row.avg_depth else 0.0

    # Get recent events list (limit to 10 for widget display)
    events_query = (
        select(DisasterAlert)
        .where(base_filter)
        .order_by(DisasterAlert.issued_at.desc())
        .limit(10)
    )

    events_result = await db.execute(events_query)
    events = events_result.scalars().all()

    recent_events = [
        {
            "id": str(eq.id),
            "magnitude": eq.magnitude,
            "depth_km": eq.depth_km,
            "location": eq.location_name or eq.district or "Unknown",
            "district": eq.district,
            "alert_level": eq.alert_level,
            "issued_at": eq.issued_at.isoformat() if eq.issued_at else None,
            "coordinates": [eq.longitude, eq.latitude] if eq.longitude and eq.latitude else None,
        }
        for eq in events
    ]

    # Determine overall status based on recent activity
    if max_magnitude >= 6.0:
        status = "CRITICAL"
    elif max_magnitude >= 5.0:
        status = "HIGH"
    elif max_magnitude >= 4.0:
        status = "ELEVATED"
    elif event_count > 0:
        status = "NORMAL"
    else:
        status = "QUIET"

    return {
        "status": status,
        "events_count": event_count,
        "max_magnitude": max_magnitude,
        "avg_magnitude": avg_magnitude,
        "avg_depth_km": avg_depth,
        "recent_events": recent_events,
        "lookback_hours": hours,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/events")
async def list_seismic_events(
    hours: int = Query(default=72, ge=1, le=720, description="Hours to look back"),
    min_magnitude: float = Query(default=0.0, ge=0.0, le=10.0, description="Minimum magnitude"),
    limit: int = Query(default=50, ge=1, le=200, description="Max events to return"),
    db: AsyncSession = Depends(get_db)
):
    """
    List seismic events with full details.

    Returns paginated list of earthquake events for detailed views.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    query = (
        select(DisasterAlert)
        .where(
            DisasterAlert.alert_type == "earthquake",
            DisasterAlert.issued_at >= cutoff,
        )
    )

    if min_magnitude > 0:
        query = query.where(DisasterAlert.magnitude >= min_magnitude)

    query = query.order_by(DisasterAlert.issued_at.desc()).limit(limit)

    result = await db.execute(query)
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": str(eq.id),
                "bipad_id": eq.bipad_id,
                "title": eq.title,
                "magnitude": eq.magnitude,
                "depth_km": eq.depth_km,
                "location": eq.location_name,
                "district": eq.district,
                "province": eq.province,
                "alert_level": eq.alert_level,
                "is_active": eq.is_active,
                "issued_at": eq.issued_at.isoformat() if eq.issued_at else None,
                "coordinates": [eq.longitude, eq.latitude] if eq.longitude and eq.latitude else None,
            }
            for eq in events
        ],
        "total": len(events),
        "lookback_hours": hours,
    }


@router.get("/map")
async def get_seismic_map_data(
    hours: int = Query(default=72, ge=1, le=720, description="Hours to look back"),
    min_magnitude: float = Query(default=3.0, ge=0.0, le=10.0, description="Minimum magnitude for map"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get seismic events for map visualization.

    Returns events with coordinates in [lng, lat] format for Leaflet.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    query = (
        select(DisasterAlert)
        .where(
            DisasterAlert.alert_type == "earthquake",
            DisasterAlert.issued_at >= cutoff,
            DisasterAlert.longitude.isnot(None),
            DisasterAlert.latitude.isnot(None),
        )
    )

    if min_magnitude > 0:
        query = query.where(DisasterAlert.magnitude >= min_magnitude)

    query = query.order_by(DisasterAlert.issued_at.desc()).limit(100)

    result = await db.execute(query)
    events = result.scalars().all()

    return {
        "features": [
            {
                "id": str(eq.id),
                "magnitude": eq.magnitude,
                "depth_km": eq.depth_km,
                "location": eq.location_name or eq.district,
                "alert_level": eq.alert_level,
                "issued_at": eq.issued_at.isoformat() if eq.issued_at else None,
                "coordinates": [eq.longitude, eq.latitude],
            }
            for eq in events
        ],
        "total": len(events),
    }
