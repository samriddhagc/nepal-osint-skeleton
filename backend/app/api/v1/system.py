"""System health and API monitoring endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_dev
from app.core.database import get_db
from app.models.user import User
from app.services.system_health_service import SystemHealthService

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def get_system_status(
    user: User = Depends(require_dev),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive system health status. DEV only."""
    service = SystemHealthService(db)
    return await service.get_full_status()


@router.get("/metrics")
async def get_api_metrics(
    period: str = Query(default="24h", pattern="^(1h|6h|24h|7d)$"),
    user: User = Depends(require_dev),
    db: AsyncSession = Depends(get_db),
):
    """Get API metrics for the specified period. DEV only."""
    service = SystemHealthService(db)
    return await service.get_api_metrics(period)
