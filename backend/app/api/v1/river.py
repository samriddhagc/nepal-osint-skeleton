"""River monitoring API endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_dev
from app.core.database import get_db
from app.services.river_service import RiverMonitoringService

router = APIRouter(prefix="/river", tags=["river-monitoring"])

# River monitoring disabled — table too large, causes CPU spikes
_DISABLED = True


@router.get("/stations")
async def get_stations(
    basin: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get all river monitoring stations with current readings."""
    if _DISABLED:
        return []
    service = RiverMonitoringService(db)
    stations = await service.get_all_stations(basin=basin)

    # Filter by basin if specified
    if basin:
        stations = [s for s in stations if s.get("basin") == basin]

    return stations


@router.get("/stations/{station_id}")
async def get_station(
    station_id: str,
    hours: int = Query(default=24, le=168),
    db: AsyncSession = Depends(get_db),
):
    """Get station details with reading history."""
    if _DISABLED:
        raise HTTPException(status_code=404, detail="River monitoring disabled")
    service = RiverMonitoringService(db)
    result = await service.get_station_history(station_id, hours=hours)

    if not result:
        raise HTTPException(status_code=404, detail="Station not found")

    return result


@router.get("/alerts")
async def get_river_alerts(
    hours: int = Query(default=24, le=168),
    db: AsyncSession = Depends(get_db),
):
    """Get stations with danger or warning water levels."""
    if _DISABLED:
        return []
    service = RiverMonitoringService(db)
    return await service.get_danger_stations(hours=hours)


@router.get("/stats")
async def get_river_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get river monitoring statistics."""
    if _DISABLED:
        return {"total_stations": 0, "active_stations": 0, "basins": []}
    service = RiverMonitoringService(db)
    return await service.get_stats()


@router.get("/map-data")
async def get_map_data(
    db: AsyncSession = Depends(get_db),
):
    """Get river stations formatted for map display."""
    if _DISABLED:
        return []
    service = RiverMonitoringService(db)
    return await service.get_map_data()


@router.get("/basins")
async def get_basins(
    db: AsyncSession = Depends(get_db),
):
    """Get list of river basins."""
    if _DISABLED:
        return []
    service = RiverMonitoringService(db)
    stats = await service.get_stats()
    return stats.get("basins", [])


@router.post("/sync", dependencies=[Depends(require_dev)])
async def sync_river_data(
    db: AsyncSession = Depends(get_db),
):
    """Trigger manual sync of river monitoring data from BIPAD."""
    service = RiverMonitoringService(db)
    stats = await service.ingest_all()

    return {
        "status": "success",
        "message": f"Synced {stats.get('readings_new', 0)} new readings from {stats.get('stations_fetched', 0)} stations",
        "stats": stats,
    }
