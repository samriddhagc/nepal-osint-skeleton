"""Energy data API endpoints for NEA power grid data."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_dev
from app.core.database import get_db
from app.core.redis import get_redis
from app.services.energy_service import EnergyService

router = APIRouter(prefix="/energy", tags=["Energy / Power Grid"])


class EnergyIndicator(BaseModel):
    """Single energy indicator."""
    value: float
    unit: str
    change: float
    change_amount: float
    source: str
    data_date: Optional[str]


class TotalSupply(BaseModel):
    """Total power supply."""
    value: float
    unit: str


class EnergySummaryResponse(BaseModel):
    """Energy summary response for dashboard widget."""
    nea_subsidiary: Optional[EnergyIndicator] = None
    ipp: Optional[EnergyIndicator] = None
    import_: Optional[EnergyIndicator] = None  # 'import' is reserved in Python
    interruption: Optional[EnergyIndicator] = None
    total_demand: Optional[EnergyIndicator] = None
    total_supply: Optional[TotalSupply] = None
    grid_status: str
    updated_at: Optional[str]

    class Config:
        # Map 'import_' field to 'import' in JSON
        populate_by_name = True


class IngestResponse(BaseModel):
    """Response for ingest operations."""
    status: str
    details: dict


@router.get("/summary")
async def get_energy_summary(
    db: AsyncSession = Depends(get_db),
):
    """
    Get energy summary for dashboard Power Grid widget.

    Returns current values for:
    - NEA Subsidiary Companies (MWh)
    - IPP - Independent Power Producers (MWh)
    - Import from India (MWh)
    - Interruption/Outages (MWh)
    - Total Energy Demand (MWh)
    - Total Supply (calculated)
    - Grid Status (STABLE, SURPLUS, STRAINED, CRITICAL)

    Data is cached for 30 minutes. Use /energy/refresh to force update.
    """
    redis = await get_redis()
    service = EnergyService(db, redis)
    summary = await service.get_energy_summary()

    # Check if we have any data
    has_data = any(
        summary.get(k) for k in ["nea_subsidiary", "ipp", "import", "total_demand"]
    )

    if not has_data:
        # No data in database, try fetching fresh data
        result = await service.ingest_all()

        # If fetch failed, seed demo data so widget can display something
        if not result.get("fetched") or result.get("saved", 0) == 0:
            await service.seed_demo_data()

        summary = await service.get_energy_summary()

    # Rename 'import' to 'import_' for response (Python reserved word handling)
    if "import" in summary:
        summary["import_"] = summary.pop("import")

    return summary


@router.post("/refresh", response_model=IngestResponse, dependencies=[Depends(require_dev)])
async def refresh_energy_data(
    db: AsyncSession = Depends(get_db),
):
    """
    Manually refresh energy data from NEA website.

    Fetches latest power grid data including:
    - NEA Subsidiary Companies production
    - IPP (Independent Power Producers) production
    - Import from India
    - System interruptions
    - Total energy demand

    Use for debugging/admin purposes.
    """
    redis = await get_redis()
    service = EnergyService(db, redis)
    results = await service.ingest_all()

    # Invalidate cache after refresh
    await service.invalidate_cache()

    # Check overall status
    success = results.get("fetched") and results.get("saved", 0) > 0

    return IngestResponse(
        status="ok" if success else "error",
        details=results,
    )
