"""Disaster alerts API endpoints - matching frontend expectations."""
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_dev
from app.core.database import get_db
from app.core.redis import get_redis
from app.repositories.disaster import DisasterIncidentRepository, DisasterAlertRepository
from app.services.disaster_service import DisasterIngestionService
from app.models.disaster import HazardType

router = APIRouter(prefix="/disaster-alerts", tags=["disaster-alerts"])


@router.get("/active")
async def get_active_alerts(
    severity: Optional[str] = None,
    hazard_type: Optional[str] = None,
    district: Optional[str] = None,
    hours: int = Query(default=72, le=720),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get active disaster alerts within time window (by event time, not ingestion time)."""
    # Calculate time cutoff based on event time (issued_at), not ingestion time
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get recent incidents (filter by incident_on - when event happened)
    incident_repo = DisasterIncidentRepository(db)
    incidents = await incident_repo.get_for_map(hours=hours, limit=limit)

    # Get recent alerts (filter by issued_at - when event happened)
    alert_repo = DisasterAlertRepository(db)
    alerts = await alert_repo.get_recent_by_event_time(hours=hours, limit=limit)

    # Combine and transform to frontend format
    result = []

    # Add incidents as alerts (they are disasters too)
    for inc in incidents:
        inc_severity = _map_severity(inc.get("severity"))
        if severity and inc_severity != severity:
            continue
        if hazard_type and inc.get("hazard_type") != hazard_type:
            continue
        if district and inc.get("district"):
            if district.lower() not in inc["district"].lower():
                continue

        result.append({
            "id": inc["id"],
            "external_id": str(inc["bipad_id"]),
            "title": inc["title"],
            "title_ne": None,
            "description": None,
            "hazard_type": inc["hazard_type"],
            "severity": inc_severity,
            "latitude": inc["coordinates"][1] if inc.get("coordinates") else None,
            "longitude": inc["coordinates"][0] if inc.get("coordinates") else None,
            "district": inc.get("district"),
            "magnitude": None,
            "deaths": inc.get("deaths", 0),
            "injured": inc.get("injured", 0),
            "is_active": True,
            "verified": inc.get("verified", False),
            "started_at": inc.get("incident_on"),
            "expires_at": None,
            "created_at": inc.get("incident_on"),
        })

    # Add earthquake alerts
    for alert in alerts:
        alert_severity = _map_alert_level_to_severity(alert.get("alert_level", "low"))
        if severity and alert_severity != severity:
            continue
        if hazard_type and alert.get("alert_type") != hazard_type:
            continue
        if district and alert.get("district"):
            if district.lower() not in alert["district"].lower():
                continue

        result.append({
            "id": alert["id"],
            "external_id": str(alert["bipad_id"]),
            "title": alert["title"],
            "title_ne": None,
            "description": None,
            "hazard_type": alert["alert_type"],
            "severity": alert_severity,
            "latitude": alert["coordinates"][1] if alert.get("coordinates") else None,
            "longitude": alert["coordinates"][0] if alert.get("coordinates") else None,
            "district": alert.get("district"),
            "magnitude": alert.get("magnitude"),
            "is_active": alert.get("is_active", True),
            "verified": True,
            "started_at": alert.get("issued_at"),
            "expires_at": None,
            "created_at": alert.get("issued_at"),
        })

    # Sort by event time (most recent first)
    result.sort(key=lambda x: x.get("started_at") or "", reverse=True)

    return result[:limit]


@router.get("/incidents")
async def get_recent_incidents(
    days: int = Query(default=7, le=90),
    hazard_type: Optional[str] = None,
    district: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get recent disaster incidents."""
    repo = DisasterIncidentRepository(db)
    incidents = await repo.get_recent(
        hours=days * 24,
        limit=limit,
        hazard_type=hazard_type,
    )

    # Transform to frontend expected format
    return [
        {
            "id": str(inc.id),
            "external_id": str(inc.bipad_id),
            "title": inc.title,
            "title_ne": inc.title_ne,
            "description": None,
            "hazard_type": inc.hazard_type,
            "latitude": inc.latitude,
            "longitude": inc.longitude,
            "province": str(inc.province) if inc.province else None,
            "district": inc.district,
            "municipality": inc.street_address,
            "location_text": inc.street_address,
            "deaths": inc.deaths,
            "injured": inc.injured,
            "missing": inc.missing,
            "affected_families": inc.affected_families,
            "houses_destroyed": None,
            "houses_damaged": None,
            "estimated_loss_npr": inc.estimated_loss,
            "verified": inc.verified,
            "incident_date": inc.incident_on.isoformat() if inc.incident_on else None,
            "created_at": inc.created_at.isoformat() if inc.created_at else None,
        }
        for inc in incidents
        if not district or (inc.district and district.lower() in inc.district.lower())
    ]


@router.get("/stats")
async def get_alert_stats(
    hours: int = Query(default=72, le=720),
    db: AsyncSession = Depends(get_db),
):
    """Get disaster alert statistics within time window."""
    # Redis cache (5 min TTL)
    cache_key = f"nepalosint:disaster_stats:{hours}"
    try:
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass  # Redis unavailable, compute fresh

    alert_repo = DisasterAlertRepository(db)
    incident_repo = DisasterIncidentRepository(db)

    # AsyncSession is not safe for concurrent queries via asyncio.gather.
    active_alerts = await alert_repo.count_total(hours=hours)
    alerts_by_type = await alert_repo.count_by_type(hours=hours)
    incidents_in_window = await incident_repo.count_total(hours=hours)
    incidents_by_type = await incident_repo.count_by_type(hours=hours)
    incidents_by_severity = await incident_repo.count_by_severity(hours=hours)
    recent_24h = await incident_repo.count_total(hours=24)
    recent_7d = await incident_repo.count_total(hours=168)

    # Count by severity level
    danger_count = incidents_by_severity.get("critical", 0)
    warning_count = incidents_by_severity.get("high", 0)

    result = {
        "active_alerts": active_alerts,
        "danger_alerts": danger_count,
        "warning_alerts": warning_count,
        "by_severity": {
            "danger": incidents_by_severity.get("critical", 0),
            "warning": incidents_by_severity.get("high", 0),
            "watch": incidents_by_severity.get("medium", 0),
            "normal": incidents_by_severity.get("low", 0),
        },
        "by_hazard": {**incidents_by_type, **alerts_by_type},
        "recent_incidents_24h": recent_24h,
        "recent_incidents_7d": recent_7d,
        "incidents_in_window": incidents_in_window,
        "hours": hours,
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache result
    try:
        redis = await get_redis()
        await redis.set(cache_key, json.dumps(result), ex=300)  # 5 min
    except Exception:
        pass

    return result


@router.get("/map-data")
async def get_map_data(
    include_alerts: bool = True,
    include_incidents: bool = True,
    days: int = Query(default=7, le=30),
    db: AsyncSession = Depends(get_db),
):
    """Get disaster data for map display."""
    alerts_data = []
    incidents_data = []

    if include_alerts:
        alert_repo = DisasterAlertRepository(db)
        alerts = await alert_repo.get_for_map(hours=days * 24, limit=200)
        alerts_data = [
            {
                "id": alert["id"],
                "title": alert["title"],
                "hazard_type": alert["alert_type"],
                "severity": _map_alert_level_to_severity(alert["alert_level"]),
                "lat": alert["coordinates"][1] if alert["coordinates"] else None,
                "lng": alert["coordinates"][0] if alert["coordinates"] else None,
                "district": alert["district"],
            }
            for alert in alerts
            if alert["coordinates"] and alert["coordinates"][0] and alert["coordinates"][1]
        ]

    if include_incidents:
        incident_repo = DisasterIncidentRepository(db)
        incidents = await incident_repo.get_for_map(hours=days * 24, limit=200)
        incidents_data = [
            {
                "id": inc["id"],
                "title": inc["title"],
                "hazard_type": inc["hazard_type"],
                "severity": _map_severity(inc["severity"]),
                "lat": inc["coordinates"][1] if inc["coordinates"] else None,
                "lng": inc["coordinates"][0] if inc["coordinates"] else None,
                "district": inc["district"],
                "deaths": inc["deaths"],
                "injured": inc["injured"],
                "incident_date": inc["incident_on"],
            }
            for inc in incidents
            if inc["coordinates"] and inc["coordinates"][0] and inc["coordinates"][1]
        ]

    return {
        "alerts": alerts_data,
        "incidents": incidents_data,
    }


@router.get("/hazard-types")
async def get_hazard_types():
    """Get list of hazard types."""
    return [
        {"code": "flood", "name": "Flood", "name_ne": "बाढी", "icon": "flood"},
        {"code": "landslide", "name": "Landslide", "name_ne": "पहिरो", "icon": "landslide"},
        {"code": "earthquake", "name": "Earthquake", "name_ne": "भूकम्प", "icon": "earthquake"},
        {"code": "fire", "name": "Fire", "name_ne": "आगलागी", "icon": "fire"},
        {"code": "lightning", "name": "Lightning", "name_ne": "चट्याङ", "icon": "lightning"},
        {"code": "drought", "name": "Drought", "name_ne": "खडेरी", "icon": "drought"},
        {"code": "cold_wave", "name": "Cold Wave", "name_ne": "चिसो लहर", "icon": "cold_wave"},
        {"code": "epidemic", "name": "Epidemic", "name_ne": "महामारी", "icon": "epidemic"},
        {"code": "avalanche", "name": "Avalanche", "name_ne": "हिउँ पहिरो", "icon": "avalanche"},
        {"code": "windstorm", "name": "Windstorm", "name_ne": "हावाहुरी", "icon": "wind_storm"},
    ]


@router.post("/sync", dependencies=[Depends(require_dev)])
async def sync_bipad_data(
    fetch_alerts: bool = True,
    fetch_incidents: bool = True,
    incident_limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Trigger manual sync with BIPAD Portal."""
    service = DisasterIngestionService(db)
    stats = await service.ingest_all(
        incident_limit=incident_limit,
        earthquake_limit=50,
        incident_days_back=30,
        earthquake_days_back=7,
        filter_insignificant=False,
    )

    return {
        "status": "success",
        "message": f"Synced {stats.get('incidents_new', 0)} incidents and {stats.get('alerts_new', 0)} alerts",
        "stats": stats,
    }


def _map_alert_level_to_severity(level: str) -> str:
    """Map internal alert level to frontend severity."""
    mapping = {
        "critical": "danger",
        "high": "warning",
        "medium": "watch",
        "low": "normal",
    }
    return mapping.get(level, "normal")


def _map_severity(severity: Optional[str]) -> str:
    """Map internal severity to frontend severity."""
    if not severity:
        return "normal"
    mapping = {
        "critical": "danger",
        "high": "warning",
        "medium": "watch",
        "low": "normal",
    }
    return mapping.get(severity, "normal")
