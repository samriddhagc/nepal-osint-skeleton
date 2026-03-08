"""Aviation monitoring API — live aircraft tracking and airport traffic."""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aviation", tags=["aviation"])


@router.get("/live")
async def get_live_aircraft(
    military_only: bool = Query(False, description="Filter to military aircraft only"),
    db: AsyncSession = Depends(get_db),
):
    """Return live aircraft positions in Nepal airspace (cached 120s in Redis)."""
    from app.core.redis import get_redis

    redis = await get_redis()
    cache_key = f"aviation:live:{'mil' if military_only else 'all'}"

    # Check Redis cache
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    from app.services.aviation_service import AviationService

    service = AviationService(db)
    aircraft = await service.get_live_aircraft(military_only=military_only)

    result = {"aircraft": aircraft, "count": len(aircraft)}

    # Cache for 60 seconds (matches poll interval)
    await redis.set(cache_key, json.dumps(result, default=str), ex=60)

    return result


@router.get("/airports")
async def get_airports():
    """Return static list of Nepal airports (cached forever — static data)."""
    from app.data.nepal_airports import NEPAL_AIRPORTS

    return {"airports": NEPAL_AIRPORTS, "count": len(NEPAL_AIRPORTS)}


@router.get("/traffic")
async def get_airport_traffic(
    db: AsyncSession = Depends(get_db),
):
    """Return per-airport busyness comparison (cached 300s in Redis)."""
    from app.core.redis import get_redis

    redis = await get_redis()
    cache_key = "aviation:traffic"

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    from app.services.aviation_service import AviationService

    service = AviationService(db)
    traffic = await service.get_airport_traffic()

    result = {"traffic": traffic}

    # Cache for 300 seconds
    await redis.set(cache_key, json.dumps(result, default=str), ex=300)

    return result


@router.get("/history/{hex_code}")
async def get_aircraft_history(
    hex_code: str,
    hours: int = Query(24, ge=1, le=168, description="Hours of history to return"),
    db: AsyncSession = Depends(get_db),
):
    """Return 24h position history for a single aircraft."""
    from app.services.aviation_service import AviationService

    service = AviationService(db)
    positions = await service.get_aircraft_history(hex_code, hours=hours)

    return {"hex_code": hex_code, "positions": positions, "count": len(positions)}


# ── Analytics Endpoints ──────────────────────────────────────


@router.get("/analytics/hourly")
async def get_hourly_counts(
    days: int = Query(7, ge=1, le=30, description="Days of history"),
    db: AsyncSession = Depends(get_db),
):
    """Hourly aircraft counts (total + military) for charts."""
    from app.core.redis import get_redis

    redis = await get_redis()
    cache_key = f"aviation:analytics:hourly:{days}"

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    from app.services.aviation_service import AviationService

    service = AviationService(db)
    data = await service.get_hourly_counts(days=days)

    result = {"hourly": data, "count": len(data)}
    await redis.set(cache_key, json.dumps(result, default=str), ex=300)

    return result


@router.get("/analytics/military")
async def get_military_stats(
    days: int = Query(7, ge=1, le=30, description="Days of history"),
    db: AsyncSession = Depends(get_db),
):
    """Military aircraft stats with per-aircraft breakdown."""
    from app.core.redis import get_redis

    redis = await get_redis()
    cache_key = f"aviation:analytics:military:{days}"

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    from app.services.aviation_service import AviationService

    service = AviationService(db)
    data = await service.get_military_stats(days=days)

    await redis.set(cache_key, json.dumps(data, default=str), ex=300)

    return data


@router.get("/analytics/top-aircraft")
async def get_top_aircraft(
    days: int = Query(7, ge=1, le=30, description="Days of history"),
    limit: int = Query(20, ge=1, le=100, description="Number of aircraft to return"),
    db: AsyncSession = Depends(get_db),
):
    """Top aircraft by observation count."""
    from app.core.redis import get_redis

    redis = await get_redis()
    cache_key = f"aviation:analytics:top:{days}:{limit}"

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    from app.services.aviation_service import AviationService

    service = AviationService(db)
    data = await service.get_top_aircraft(days=days, limit=limit)

    result = {"aircraft": data, "count": len(data)}
    await redis.set(cache_key, json.dumps(result, default=str), ex=300)

    return result
