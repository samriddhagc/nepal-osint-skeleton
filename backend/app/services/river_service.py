"""River monitoring service with real-time WebSocket broadcasts."""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.river_fetcher import get_river_fetcher, RiverStationData
from app.models.river import RiverStation, RiverReading
from app.repositories.river import RiverStationRepository, RiverReadingRepository

logger = logging.getLogger(__name__)

# WebSocket manager - imported lazily to avoid circular imports
_news_manager = None


def get_news_manager():
    """Get the news WebSocket manager (lazy import)."""
    global _news_manager
    if _news_manager is None:
        try:
            from app.api.v1.websocket import news_manager
            _news_manager = news_manager
        except ImportError:
            logger.warning("WebSocket manager not available")
    return _news_manager


class RiverMonitoringService:
    """Service for river monitoring operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.station_repo = RiverStationRepository(db)
        self.reading_repo = RiverReadingRepository(db)
        self.fetcher = get_river_fetcher()

    async def ingest_all(self) -> dict:
        """Fetch and ingest all river data from BIPAD."""
        stats = {
            "stations_fetched": 0,
            "stations_new": 0,
            "stations_updated": 0,
            "readings_new": 0,
            "readings_duplicate": 0,
            "danger_alerts": 0,
            "warning_alerts": 0,
            "errors": [],
        }

        try:
            result = await self.fetcher.fetch_all()
            stats["stations_fetched"] = len(result.stations)
            stats["errors"] = result.errors

            for station_data in result.stations:
                try:
                    await self._process_station(station_data, stats)
                except Exception as e:
                    logger.error(f"Error processing station {station_data.title}: {e}")
                    stats["errors"].append(f"Station {station_data.title}: {e}")

            logger.info(
                f"River ingestion complete: {stats['stations_fetched']} fetched, "
                f"{stats['readings_new']} new readings, "
                f"{stats['danger_alerts']} danger, {stats['warning_alerts']} warning"
            )

        except Exception as e:
            logger.error(f"River ingestion failed: {e}")
            stats["errors"].append(str(e))

        return stats

    async def _process_station(self, data: RiverStationData, stats: dict) -> None:
        """Process a single station and its reading."""
        # Get or create the station
        station, created = await self.station_repo.get_or_create(
            bipad_id=data.bipad_id,
            title=data.title,
            basin=data.basin,
            description=data.description,
            longitude=data.longitude,
            latitude=data.latitude,
            danger_level=data.danger_level,
            warning_level=data.warning_level,
            image_url=data.image_url,
        )

        if created:
            stats["stations_new"] += 1
        else:
            stats["stations_updated"] += 1

        # Check if reading already exists
        if await self.reading_repo.exists_by_bipad_id(data.bipad_reading_id):
            stats["readings_duplicate"] += 1
            return

        # Create new reading
        reading = RiverReading(
            station_id=station.id,
            bipad_reading_id=data.bipad_reading_id,
            water_level=data.water_level,
            status=data.status,
            trend=data.trend,
            reading_at=data.reading_at,
        )
        await self.reading_repo.create(reading)
        stats["readings_new"] += 1

        # Track danger/warning levels (exact match, not partial)
        status_upper = data.status.upper()
        if status_upper == "DANGER":
            stats["danger_alerts"] += 1
            await self._broadcast_alert(station, reading, "danger")
        elif status_upper == "WARNING":
            stats["warning_alerts"] += 1
            await self._broadcast_alert(station, reading, "warning")

        # Broadcast new reading via WebSocket
        await self._broadcast_reading(station, reading)

    async def _broadcast_reading(self, station: RiverStation, reading: RiverReading) -> None:
        """Broadcast new reading via WebSocket."""
        manager = get_news_manager()
        if manager:
            try:
                await manager.broadcast({
                    "type": "river_reading",
                    "data": {
                        "station_id": str(station.id),
                        "station_title": station.title,
                        "basin": station.basin,
                        "water_level": reading.water_level,
                        "danger_level": station.danger_level,
                        "warning_level": station.warning_level,
                        "status": reading.status,
                        "trend": reading.trend,
                        "coordinates": [station.longitude, station.latitude],
                        "reading_at": reading.reading_at.isoformat() if reading.reading_at else None,
                    },
                })
            except Exception as e:
                logger.warning(f"Failed to broadcast river reading: {e}")

    async def _broadcast_alert(
        self,
        station: RiverStation,
        reading: RiverReading,
        alert_level: str,
    ) -> None:
        """Broadcast danger/warning alert via WebSocket."""
        manager = get_news_manager()
        if manager:
            try:
                await manager.broadcast({
                    "type": "river_alert",
                    "data": {
                        "alert_level": alert_level,
                        "station_id": str(station.id),
                        "station_title": station.title,
                        "basin": station.basin,
                        "water_level": reading.water_level,
                        "danger_level": station.danger_level,
                        "warning_level": station.warning_level,
                        "status": reading.status,
                        "coordinates": [station.longitude, station.latitude],
                        "reading_at": reading.reading_at.isoformat() if reading.reading_at else None,
                    },
                })
            except Exception as e:
                logger.warning(f"Failed to broadcast river alert: {e}")

    async def get_all_stations(self, basin: Optional[str] = None) -> list[dict]:
        """Get all stations with current readings."""
        return await self.station_repo.get_all_with_latest_reading()

    async def get_station_history(
        self,
        station_id: str,
        hours: int = 24,
    ) -> dict:
        """Get station details with reading history."""
        from uuid import UUID
        station = await self.station_repo.get_by_id(UUID(station_id))
        if not station:
            return None

        readings = await self.reading_repo.get_history(station.id, hours=hours)

        return {
            "station": station.to_dict(),
            "readings": [r.to_dict() for r in readings],
        }

    async def get_danger_stations(self, hours: int = 24) -> list[dict]:
        """Get stations with danger or warning readings."""
        return await self.reading_repo.get_danger_readings(hours=hours)

    async def get_stats(self) -> dict:
        """Get river monitoring statistics."""
        status_counts = await self.station_repo.count_by_status()
        basins = await self.station_repo.get_basins()
        stations_with_latest = await self.station_repo.get_all_with_latest_reading()

        latest_reading_at: Optional[datetime] = None
        for station in stations_with_latest:
            raw_ts = station.get("latest_observed_at")
            if not raw_ts:
                reading = station.get("latest_reading")
                raw_ts = reading.get("reading_at") if reading else None
            if not raw_ts:
                continue
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if latest_reading_at is None or ts > latest_reading_at:
                latest_reading_at = ts

        return {
            "total_stations": len(stations_with_latest),
            "danger_count": status_counts.get("danger", 0),
            "warning_count": status_counts.get("warning", 0),
            "normal_count": status_counts.get("normal", 0),
            "basins": basins,
            "last_updated": (latest_reading_at or datetime.now(timezone.utc)).isoformat(),
        }

    async def get_map_data(self) -> list[dict]:
        """Get all stations formatted for map display."""
        stations = await self.station_repo.get_all_with_latest_reading()

        return [
            {
                "id": s["id"],
                "title": s["title"],
                "basin": s["basin"],
                "coordinates": s["coordinates"],
                "water_level": s.get("current_level"),
                "danger_level": s.get("danger_level"),
                "warning_level": s.get("warning_level"),
                "status": s.get("current_status"),
                "trend": s.get("current_trend"),
            }
            for s in stations
            if s.get("coordinates")
        ]
