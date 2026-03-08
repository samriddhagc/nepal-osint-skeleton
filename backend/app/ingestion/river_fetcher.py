"""BIPAD Portal river monitoring API fetcher."""
import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# BIPAD Portal river monitoring endpoints
BIPAD_RIVER_URLS = [
    "https://bipadportal.gov.np/api/v1/river-stations/",
    "https://bipadportal.gov.np/api/v1/river/",
]

# Default fetch page size and hard page cap.
# Keep a cap because BIPAD reports a bogus "count" value on some endpoints.
DEFAULT_LIMIT = 250
MAX_PAGES = 8

# Request settings
REQUEST_TIMEOUT = 30


@dataclass
class RiverStationData:
    """Parsed river station data from BIPAD."""
    bipad_id: int
    bipad_reading_id: int
    title: str
    basin: Optional[str]
    description: Optional[str]
    longitude: Optional[float]
    latitude: Optional[float]
    water_level: float
    danger_level: Optional[float]
    warning_level: Optional[float]
    status: str
    trend: str
    image_url: Optional[str]
    reading_at: datetime


@dataclass
class RiverFetchResult:
    """Result of fetching river data."""
    stations: list[RiverStationData]
    errors: list[str]
    source_url: Optional[str]


class RiverFetcher:
    """Async fetcher for BIPAD river monitoring data."""

    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._working_url: Optional[str] = None

    async def fetch_all(self) -> RiverFetchResult:
        """Fetch all river monitoring data from BIPAD Portal."""
        errors = []

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # Try the working URL first if we have one
            urls_to_try = [self._working_url] if self._working_url else []
            urls_to_try.extend([u for u in BIPAD_RIVER_URLS if u != self._working_url])

            for url in urls_to_try:
                if not url:
                    continue
                try:
                    result = await self._fetch_from_url(session, url)
                    if result.stations:
                        self._working_url = url
                        logger.info(f"Fetched {len(result.stations)} river stations from {url}")
                        return result
                except Exception as e:
                    errors.append(f"{url}: {str(e)}")
                    logger.warning(f"Failed to fetch from {url}: {e}")
                    continue

            logger.error(f"All BIPAD river URLs failed: {errors}")
            return RiverFetchResult(stations=[], errors=errors, source_url=None)

    async def _fetch_from_url(self, session: aiohttp.ClientSession, url: str) -> RiverFetchResult:
        """Fetch river data from a specific URL."""
        stations = []
        errors = []
        seen_readings = set()

        try:
            next_url = f"{url}?limit={DEFAULT_LIMIT}"
            page_count = 0

            while next_url and page_count < MAX_PAGES:
                page_count += 1
                async with session.get(next_url) as response:
                    if response.status != 200:
                        raise Exception(f"HTTP {response.status}")

                    data = await response.json()
                    results = data.get("results", [])
                    if not results:
                        break

                    for item in results:
                        try:
                            station = self._parse_station(item)
                            if not station:
                                continue
                            if station.bipad_reading_id in seen_readings:
                                continue
                            seen_readings.add(station.bipad_reading_id)
                            stations.append(station)
                        except Exception as e:
                            errors.append(f"Parse error for station {item.get('id', 'unknown')}: {e}")

                    next_url = data.get("next")

            if page_count >= MAX_PAGES and next_url:
                errors.append(f"Stopped after {MAX_PAGES} pages to avoid runaway pagination")

            return RiverFetchResult(stations=stations, errors=errors, source_url=url)

        except asyncio.TimeoutError:
            raise Exception("Request timeout")
        except aiohttp.ClientError as e:
            raise Exception(f"Network error: {e}")

    def _parse_station(self, item: dict) -> Optional[RiverStationData]:
        """Parse a single station record from BIPAD response."""
        try:
            station_id_raw = item.get("station") or item.get("stationSeriesId") or item.get("id")
            station_id = self._coerce_int(station_id_raw)
            if station_id is None:
                return None

            water_level_raw = item.get("waterLevel")
            reading_at_str = (
                item.get("waterLevelOn")
                or item.get("measuredOn")
                or item.get("modifiedOn")
                or item.get("createdOn")
            )
            # Skip records that don't carry an actual reading payload.
            if water_level_raw is None and not reading_at_str:
                return None

            # Extract coordinates from GeoJSON point
            point = item.get("point", {})
            coords = point.get("coordinates", [None, None]) if point else [None, None]
            longitude = coords[0] if len(coords) > 0 else None
            latitude = coords[1] if len(coords) > 1 else None

            # Parse reading timestamp
            reading_at = self._parse_datetime(reading_at_str)
            if reading_at is None:
                reading_at = datetime.now(timezone.utc)

            # API IDs vary by endpoint:
            # - /river/ often exposes per-reading IDs
            # - /river-stations/ exposes station IDs
            # Build a stable per-reading key from station + reading timestamp.
            reading_signature = f"{station_id}:{reading_at.isoformat()}"
            bipad_reading_id = self._stable_int64(reading_signature)
            if bipad_reading_id == 0:
                bipad_reading_id = 1

            return RiverStationData(
                bipad_id=station_id,
                bipad_reading_id=bipad_reading_id,
                title=item.get("title", "Unknown Station"),
                basin=item.get("basin"),
                description=item.get("description"),
                longitude=longitude,
                latitude=latitude,
                water_level=float(water_level_raw or 0),
                danger_level=float(item.get("dangerLevel")) if item.get("dangerLevel") else None,
                warning_level=float(item.get("warningLevel")) if item.get("warningLevel") else None,
                status=item.get("status", "UNKNOWN"),
                trend=item.get("steady", "UNKNOWN"),
                image_url=item.get("image"),
                reading_at=reading_at,
            )
        except Exception as e:
            logger.warning(f"Failed to parse station data: {e}")
            return None

    @staticmethod
    def _coerce_int(value: object) -> Optional[int]:
        """Best-effort conversion to int."""
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _stable_int64(text: str) -> int:
        """Create a deterministic signed-64-bit-compatible positive integer."""
        digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, byteorder="big", signed=False) & 0x7FFFFFFFFFFFFFFF

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        """Parse ISO-ish datetime strings returned by BIPAD."""
        if not value:
            return None

        cleaned = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)


# Singleton instance
_fetcher: Optional[RiverFetcher] = None


def get_river_fetcher() -> RiverFetcher:
    """Get or create the river fetcher singleton."""
    global _fetcher
    if _fetcher is None:
        _fetcher = RiverFetcher()
    return _fetcher
