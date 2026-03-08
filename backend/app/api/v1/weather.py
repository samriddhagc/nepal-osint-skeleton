"""Weather API endpoints for DHM Nepal data."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_dev
from app.core.database import get_db
from app.core.redis import get_redis
from app.services.weather_service import WeatherService
from app.schemas.weather import (
    WeatherForecastResponse,
    WeatherSummaryResponse,
    WeatherHistoryResponse,
)

router = APIRouter(prefix="/weather", tags=["Weather"])


@router.get("/current", response_model=WeatherForecastResponse)
async def get_current_weather(
    db: AsyncSession = Depends(get_db),
):
    """
    Get current weather forecast for Nepal.

    Returns the latest weather bulletin from DHM (Department of Hydrology
    and Meteorology) Nepal with bilingual forecasts (English/Nepali).
    """
    redis = await get_redis()
    service = WeatherService(db, redis)
    forecast = await service.get_current_forecast()

    if not forecast:
        raise HTTPException(status_code=503, detail="Weather data temporarily unavailable")

    return forecast


@router.get("/summary", response_model=WeatherSummaryResponse)
async def get_weather_summary(
    db: AsyncSession = Depends(get_db),
):
    """
    Get weather summary for dashboard widget.

    Returns a simplified weather summary with derived condition,
    icon code, and forecast text optimized for display.
    """
    redis = await get_redis()
    service = WeatherService(db, redis)
    summary = await service.get_weather_summary()

    if not summary:
        raise HTTPException(status_code=503, detail="Weather data temporarily unavailable")

    return summary


@router.get("/history", response_model=WeatherHistoryResponse)
async def get_weather_history(
    days: int = Query(default=7, ge=1, le=30, description="Number of days of history"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get historical weather forecasts.

    Returns weather forecasts from the past N days.
    """
    redis = await get_redis()
    service = WeatherService(db, redis)
    forecasts = await service.get_forecast_history(days=days)

    return WeatherHistoryResponse(
        forecasts=forecasts,
        total=len(forecasts),
    )


@router.post("/refresh", dependencies=[Depends(require_dev)])
async def refresh_weather(
    db: AsyncSession = Depends(get_db),
):
    """
    Manually refresh weather data from DHM API.

    Fetches the latest forecast from DHM and updates the database.
    Used for debugging/admin purposes.
    """
    redis = await get_redis()
    service = WeatherService(db, redis)
    stats = await service.ingest_forecast()

    return {
        "status": "ok" if stats["fetched"] else "error",
        "created": stats["created"],
        "updated": stats["updated"],
        "error": stats["error"],
    }
