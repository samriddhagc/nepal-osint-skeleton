"""River monitoring repository for database operations."""
import math
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.river import RiverStation, RiverReading

CURRENT_READING_MAX_AGE_HOURS = 72
MIN_REASONABLE_WATER_LEVEL = -2.0
MAX_REASONABLE_WATER_LEVEL = 200.0


class RiverStationRepository:
    """Repository for RiverStation database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, station_id: UUID) -> Optional[RiverStation]:
        """Get station by ID."""
        result = await self.db.execute(
            select(RiverStation).where(RiverStation.id == station_id)
        )
        return result.scalar_one_or_none()

    async def get_by_bipad_id(self, bipad_id: int) -> Optional[RiverStation]:
        """Get station by BIPAD ID."""
        result = await self.db.execute(
            select(RiverStation).where(RiverStation.bipad_id == bipad_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        bipad_id: int,
        title: str,
        basin: Optional[str] = None,
        description: Optional[str] = None,
        longitude: Optional[float] = None,
        latitude: Optional[float] = None,
        danger_level: Optional[float] = None,
        warning_level: Optional[float] = None,
        image_url: Optional[str] = None,
    ) -> tuple[RiverStation, bool]:
        """Get existing station or create new one. Returns (station, created)."""
        station = await self.get_by_bipad_id(bipad_id)
        if station:
            # Update existing station with new data
            station.title = title
            station.basin = basin or station.basin
            station.description = description or station.description
            station.longitude = longitude or station.longitude
            station.latitude = latitude or station.latitude
            station.danger_level = danger_level or station.danger_level
            station.warning_level = warning_level or station.warning_level
            station.image_url = image_url or station.image_url
            station.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            return station, False

        # Create new station
        station = RiverStation(
            bipad_id=bipad_id,
            title=title,
            basin=basin,
            description=description,
            longitude=longitude,
            latitude=latitude,
            danger_level=danger_level,
            warning_level=warning_level,
            image_url=image_url,
        )
        self.db.add(station)
        await self.db.commit()
        await self.db.refresh(station)
        return station, True

    async def list_active(self, basin: Optional[str] = None) -> list[RiverStation]:
        """List all active stations, optionally filtered by basin."""
        query = select(RiverStation).where(RiverStation.is_active == True)
        if basin:
            query = query.where(RiverStation.basin == basin)
        query = query.order_by(RiverStation.title)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_all_with_latest_reading(self) -> list[dict]:
        """Get all stations with their latest reading."""
        # Get all active stations
        stations = await self.list_active()

        result = []
        now_utc = datetime.now(timezone.utc)
        for station in stations:
            # Get a few latest readings so we can skip stale/anomalous values.
            reading_result = await self.db.execute(
                select(RiverReading)
                .where(RiverReading.station_id == station.id)
                .order_by(desc(RiverReading.reading_at))
                .limit(5)
            )
            reading_candidates = list(reading_result.scalars().all())
            latest_observed = reading_candidates[0] if reading_candidates else None
            latest_reading = next(
                (
                    reading
                    for reading in reading_candidates
                    if self._is_usable_current_reading(station, reading, now_utc)
                ),
                None,
            )

            station_dict = station.to_dict()
            station_dict["latest_observed_at"] = (
                latest_observed.reading_at.isoformat() if latest_observed and latest_observed.reading_at else None
            )
            station_dict["is_stale"] = bool(
                latest_observed and self._is_stale(latest_observed.reading_at, now_utc)
            )
            station_dict["is_anomalous"] = bool(
                latest_observed and not self._is_plausible_water_level(
                    station=station,
                    water_level=latest_observed.water_level,
                )
            )
            if latest_reading:
                station_dict["latest_reading"] = latest_reading.to_dict()
                station_dict["current_level"] = latest_reading.water_level
                station_dict["current_status"] = latest_reading.status
                station_dict["current_trend"] = latest_reading.trend
            else:
                station_dict["latest_reading"] = None
                station_dict["current_level"] = None
                station_dict["current_status"] = None
                station_dict["current_trend"] = None

            result.append(station_dict)

        return result

    @staticmethod
    def _is_stale(reading_at: Optional[datetime], now_utc: datetime) -> bool:
        """True when reading is older than the allowed freshness window."""
        if reading_at is None:
            return True
        if reading_at.tzinfo is None:
            reading_at = reading_at.replace(tzinfo=timezone.utc)
        return reading_at < (now_utc - timedelta(hours=CURRENT_READING_MAX_AGE_HOURS))

    def _is_plausible_water_level(self, station: RiverStation, water_level: Optional[float]) -> bool:
        """Guard against obvious sensor/data corruption values."""
        if water_level is None or not math.isfinite(water_level):
            return False
        if water_level < MIN_REASONABLE_WATER_LEVEL:
            return False

        dynamic_ceiling = MAX_REASONABLE_WATER_LEVEL
        threshold_candidates = [
            level
            for level in (station.warning_level, station.danger_level)
            if level is not None and level > 0
        ]
        if threshold_candidates:
            dynamic_ceiling = max(dynamic_ceiling, max(threshold_candidates) * 8.0)

        return water_level <= dynamic_ceiling

    def _is_usable_current_reading(
        self,
        station: RiverStation,
        reading: RiverReading,
        now_utc: datetime,
    ) -> bool:
        """Reading must be fresh and plausible to be used as current status."""
        if reading is None:
            return False
        if self._is_stale(reading.reading_at, now_utc):
            return False
        return self._is_plausible_water_level(station, reading.water_level)

    async def get_basins(self) -> list[str]:
        """Get list of unique basins."""
        result = await self.db.execute(
            select(RiverStation.basin)
            .where(RiverStation.basin.isnot(None))
            .distinct()
            .order_by(RiverStation.basin)
        )
        return [row[0] for row in result.all()]

    async def count_by_status(self) -> dict[str, int]:
        """Count stations by their latest reading status."""
        stations = await self.get_all_with_latest_reading()
        counts = {"danger": 0, "warning": 0, "normal": 0, "unknown": 0}
        for s in stations:
            status = (s.get("current_status") or "").upper()
            # Check for exact matches first, then partial
            if status == "DANGER":
                counts["danger"] += 1
            elif status == "WARNING":
                counts["warning"] += 1
            elif "BELOW" in status or status:
                # BELOW WARNING LEVEL is normal
                counts["normal"] += 1
            else:
                counts["unknown"] += 1
        return counts


class RiverReadingRepository:
    """Repository for RiverReading database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def exists_by_bipad_id(self, bipad_reading_id: int) -> bool:
        """Check if reading already exists."""
        result = await self.db.execute(
            select(func.count(RiverReading.id)).where(
                RiverReading.bipad_reading_id == bipad_reading_id
            )
        )
        return (result.scalar() or 0) > 0

    async def create(self, reading: RiverReading) -> RiverReading:
        """Create a new reading."""
        self.db.add(reading)
        await self.db.commit()
        await self.db.refresh(reading)
        return reading

    async def get_latest_for_station(self, station_id: UUID) -> Optional[RiverReading]:
        """Get the most recent reading for a station."""
        result = await self.db.execute(
            select(RiverReading)
            .where(RiverReading.station_id == station_id)
            .order_by(desc(RiverReading.reading_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_history(
        self,
        station_id: UUID,
        hours: int = 24,
        limit: int = 100,
    ) -> list[RiverReading]:
        """Get reading history for a station within time window."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(RiverReading)
            .where(
                RiverReading.station_id == station_id,
                RiverReading.reading_at >= cutoff,
            )
            .order_by(desc(RiverReading.reading_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_danger_readings(self, hours: int = 24) -> list[dict]:
        """Get readings that are at danger or warning level."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(RiverReading)
            .where(
                RiverReading.reading_at >= cutoff,
                RiverReading.status.in_(["DANGER", "WARNING"]),
            )
            .order_by(desc(RiverReading.reading_at))
        )
        readings = result.scalars().all()

        # Join with station data
        output = []
        for reading in readings:
            station_result = await self.db.execute(
                select(RiverStation).where(RiverStation.id == reading.station_id)
            )
            station = station_result.scalar_one_or_none()
            if station:
                output.append({
                    **reading.to_dict(),
                    "station": station.to_dict(),
                })
        return output

    async def cleanup_old_readings(self, days: int = 30) -> int:
        """Delete readings older than specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(RiverReading).where(RiverReading.reading_at < cutoff)
        )
        readings = result.scalars().all()

        count = len(readings)
        for reading in readings:
            await self.db.delete(reading)

        await self.db.commit()
        return count
