"""Weather forecast repository for database operations."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.weather import WeatherForecast


class WeatherForecastRepository:
    """Repository for WeatherForecast database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, forecast_id: UUID) -> Optional[WeatherForecast]:
        """Get forecast by ID."""
        result = await self.db.execute(
            select(WeatherForecast).where(WeatherForecast.id == forecast_id)
        )
        return result.scalar_one_or_none()

    async def get_by_dhm_id(self, dhm_id: str) -> Optional[WeatherForecast]:
        """Get forecast by DHM ID."""
        result = await self.db.execute(
            select(WeatherForecast).where(WeatherForecast.dhm_id == dhm_id)
        )
        return result.scalar_one_or_none()

    async def get_latest(self) -> Optional[WeatherForecast]:
        """Get the most recent weather forecast."""
        result = await self.db.execute(
            select(WeatherForecast)
            .order_by(desc(WeatherForecast.issue_date))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_history(self, days: int = 7, limit: int = 10) -> list[WeatherForecast]:
        """Get forecast history for the past N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            select(WeatherForecast)
            .where(WeatherForecast.issue_date >= cutoff)
            .order_by(desc(WeatherForecast.issue_date))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, forecast: WeatherForecast) -> WeatherForecast:
        """Create a new forecast."""
        self.db.add(forecast)
        await self.db.commit()
        await self.db.refresh(forecast)
        return forecast

    async def upsert(
        self,
        dhm_id: str,
        issue_date: datetime,
        analysis_en: Optional[str] = None,
        analysis_np: Optional[str] = None,
        forecast_en_1: Optional[str] = None,
        forecast_np_1: Optional[str] = None,
        forecast_en_2: Optional[str] = None,
        forecast_np_2: Optional[str] = None,
        special_notice: Optional[str] = None,
        issued_by: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> tuple[WeatherForecast, bool]:
        """
        Create or update a forecast by DHM ID.
        Returns (forecast, created) tuple.
        """
        existing = await self.get_by_dhm_id(dhm_id)

        if existing:
            # Update existing forecast
            existing.issue_date = issue_date
            existing.analysis_en = analysis_en
            existing.analysis_np = analysis_np
            existing.forecast_en_1 = forecast_en_1
            existing.forecast_np_1 = forecast_np_1
            existing.forecast_en_2 = forecast_en_2
            existing.forecast_np_2 = forecast_np_2
            existing.special_notice = special_notice
            existing.issued_by = issued_by
            existing.updated_by = updated_by
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            return existing, False

        # Create new forecast
        forecast = WeatherForecast(
            dhm_id=dhm_id,
            issue_date=issue_date,
            analysis_en=analysis_en,
            analysis_np=analysis_np,
            forecast_en_1=forecast_en_1,
            forecast_np_1=forecast_np_1,
            forecast_en_2=forecast_en_2,
            forecast_np_2=forecast_np_2,
            special_notice=special_notice,
            issued_by=issued_by,
            updated_by=updated_by,
        )
        self.db.add(forecast)
        await self.db.commit()
        await self.db.refresh(forecast)
        return forecast, True

    async def cleanup_old_forecasts(self, days: int = 30) -> int:
        """Delete forecasts older than specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            select(WeatherForecast).where(WeatherForecast.issue_date < cutoff)
        )
        forecasts = result.scalars().all()

        count = len(forecasts)
        for forecast in forecasts:
            await self.db.delete(forecast)

        await self.db.commit()
        return count
