"""Market data API endpoints for NEPSE, forex, gold/silver, and fuel prices."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_dev
from app.core.database import get_db
from app.core.redis import get_redis
from app.services.market_service import MarketService

router = APIRouter(prefix="/market", tags=["Market Data"])


class MarketIndicator(BaseModel):
    """Single market indicator."""
    value: float
    unit: str
    change: float
    change_amount: float
    source: str
    data_date: Optional[str]


class MarketSummaryResponse(BaseModel):
    """Market summary response for dashboard widget."""
    nepse: Optional[MarketIndicator] = None
    usd_npr: Optional[MarketIndicator] = None
    gold: Optional[MarketIndicator] = None
    silver: Optional[MarketIndicator] = None
    petrol: Optional[MarketIndicator] = None
    diesel: Optional[MarketIndicator] = None
    updated_at: Optional[str]


class IngestResponse(BaseModel):
    """Response for ingest operations."""
    status: str
    details: dict


@router.get("/summary", response_model=MarketSummaryResponse)
async def get_market_summary(
    db: AsyncSession = Depends(get_db),
):
    """
    Get market summary for dashboard widget.

    Returns current values for:
    - NEPSE index
    - USD/NPR exchange rate
    - Gold price per tola
    - Silver price per tola
    - Petrol price per litre
    - Diesel price per litre

    Data is cached for 1 hour. Use /market/refresh to force update.
    """
    redis = await get_redis()
    service = MarketService(db, redis)
    summary = await service.get_market_summary()

    # Check if we have any data
    has_data = any(
        summary.get(k) for k in ["nepse", "usd_npr", "gold", "silver", "petrol", "diesel"]
    )

    if not has_data:
        # No data in database, try fetching fresh data
        await service.ingest_all()
        summary = await service.get_market_summary()

    return summary


@router.post("/refresh", response_model=IngestResponse, dependencies=[Depends(require_dev)])
async def refresh_market_data(
    db: AsyncSession = Depends(get_db),
):
    """
    Manually refresh market data from all sources.

    Fetches latest data from:
    - Nepal Rastra Bank (forex)
    - FENEGOSIDA (gold/silver)
    - Nepal Oil Corporation (fuel)
    - NEPSE/merolagani.com (stock index)

    Use for debugging/admin purposes.
    """
    redis = await get_redis()
    service = MarketService(db, redis)
    results = await service.ingest_all()

    # Invalidate cache after refresh
    await service.invalidate_cache()

    # Check overall status
    all_fetched = all(
        r.get("fetched") or r.get("saved")
        for r in results.values()
        if isinstance(r, dict) and not r.get("error")
    )

    return IngestResponse(
        status="ok" if all_fetched else "partial",
        details=results,
    )


@router.post("/refresh/forex", dependencies=[Depends(require_dev)])
async def refresh_forex(
    db: AsyncSession = Depends(get_db),
):
    """Refresh USD/NPR exchange rate from NRB."""
    redis = await get_redis()
    service = MarketService(db, redis)
    result = await service.ingest_forex()
    await service.invalidate_cache()
    return result


@router.post("/refresh/gold-silver", dependencies=[Depends(require_dev)])
async def refresh_gold_silver(
    db: AsyncSession = Depends(get_db),
):
    """Refresh gold and silver prices from FENEGOSIDA."""
    redis = await get_redis()
    service = MarketService(db, redis)
    result = await service.ingest_gold_silver()
    await service.invalidate_cache()
    return result


@router.post("/refresh/fuel", dependencies=[Depends(require_dev)])
async def refresh_fuel(
    db: AsyncSession = Depends(get_db),
):
    """Refresh fuel prices from Nepal Oil Corporation."""
    redis = await get_redis()
    service = MarketService(db, redis)
    result = await service.ingest_fuel()
    await service.invalidate_cache()
    return result


@router.post("/refresh/nepse", dependencies=[Depends(require_dev)])
async def refresh_nepse(
    db: AsyncSession = Depends(get_db),
):
    """Refresh NEPSE index from merolagani.com."""
    redis = await get_redis()
    service = MarketService(db, redis)
    result = await service.ingest_nepse()
    await service.invalidate_cache()
    return result
