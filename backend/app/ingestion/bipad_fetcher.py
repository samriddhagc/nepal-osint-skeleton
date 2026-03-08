"""Async BIPAD Portal API fetcher with connection pooling."""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp

from app.config import get_settings
from app.models.disaster import BIPAD_HAZARD_MAP, HazardType

logger = logging.getLogger(__name__)
settings = get_settings()


# BIPAD API base URL
BIPAD_BASE_URL = "https://bipadportal.gov.np/api/v1"


@dataclass
class FetchedIncident:
    """Normalized disaster incident from BIPAD."""
    bipad_id: int
    title: str
    title_ne: Optional[str] = None
    hazard_type: str = "other"
    hazard_id: Optional[int] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    street_address: Optional[str] = None
    ward_ids: Optional[list] = None
    district: Optional[str] = None
    province: Optional[int] = None
    deaths: int = 0
    injured: int = 0
    missing: int = 0
    affected_families: int = 0
    estimated_loss: float = 0.0
    verified: bool = False
    incident_on: Optional[datetime] = None
    raw_data: Optional[dict] = None


@dataclass
class FetchedAlert:
    """Normalized disaster alert from BIPAD."""
    bipad_id: int
    title: str
    description: Optional[str] = None
    alert_type: str = "early_warning"
    alert_level: str = "medium"
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    location_name: Optional[str] = None
    district: Optional[str] = None
    province: Optional[int] = None
    magnitude: Optional[float] = None
    depth_km: Optional[float] = None
    expires_at: Optional[datetime] = None
    issued_at: Optional[datetime] = None
    raw_data: Optional[dict] = None


@dataclass
class BIPADFetchResult:
    """Result of fetching from BIPAD API."""
    endpoint: str
    success: bool
    incidents: list[FetchedIncident] = field(default_factory=list)
    alerts: list[FetchedAlert] = field(default_factory=list)
    error: Optional[str] = None
    fetch_time_ms: float = 0.0
    total_count: int = 0


class BIPADFetcher:
    """Async BIPAD Portal API client with connection pooling and rate limiting."""

    def __init__(
        self,
        max_concurrent: int = 5,
        timeout: int = 30,
        per_host_limit: int = 2,
    ):
        self.max_concurrent = max_concurrent
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.per_host_limit = per_host_limit
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def __aenter__(self) -> "BIPADFetcher":
        """Create session and semaphore on context entry."""
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent * 2,
            limit_per_host=self.per_host_limit,
            ttl_dns_cache=300,
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            headers={
                "User-Agent": "NepalOSINT/5.0 (BIPAD Portal Integration)",
                "Accept": "application/json",
            },
        )
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self

    async def __aexit__(self, *args) -> None:
        """Close session on context exit."""
        if self._session:
            await self._session.close()
            self._session = None

    async def fetch_incidents(
        self,
        limit: int = 100,
        offset: int = 0,
        days_back: int = 30,
    ) -> BIPADFetchResult:
        """
        Fetch disaster incidents from BIPAD Portal.

        Args:
            limit: Max incidents to fetch
            offset: Pagination offset
            days_back: Fetch incidents from last N days
        """
        start_time = time.monotonic()
        endpoint = f"{BIPAD_BASE_URL}/incident/"

        # Calculate date filter
        from_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        from_date_str = from_date.strftime("%Y-%m-%d")

        params = {
            "limit": limit,
            "offset": offset,
            "ordering": "-incident_on",  # Most recent first
            "incident_on__gte": from_date_str,
        }

        async with self._semaphore:
            try:
                async with self._session.get(endpoint, params=params) as response:
                    if response.status != 200:
                        return BIPADFetchResult(
                            endpoint="incidents",
                            success=False,
                            error=f"HTTP {response.status}",
                            fetch_time_ms=(time.monotonic() - start_time) * 1000,
                        )

                    data = await response.json()

                # Parse results
                results = data.get("results", [])
                incidents = []

                for item in results:
                    incident = self._parse_incident(item)
                    if incident:
                        incidents.append(incident)

                return BIPADFetchResult(
                    endpoint="incidents",
                    success=True,
                    incidents=incidents,
                    total_count=data.get("count", len(incidents)),
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )

            except asyncio.TimeoutError:
                return BIPADFetchResult(
                    endpoint="incidents",
                    success=False,
                    error="Timeout",
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )
            except Exception as e:
                logger.exception(f"Error fetching BIPAD incidents: {e}")
                return BIPADFetchResult(
                    endpoint="incidents",
                    success=False,
                    error=str(e),
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )

    async def fetch_earthquakes(
        self,
        limit: int = 50,
        min_magnitude: float = 4.0,
        days_back: int = 7,
    ) -> BIPADFetchResult:
        """
        Fetch earthquake data from BIPAD Portal.

        Args:
            limit: Max earthquakes to fetch
            min_magnitude: Minimum magnitude to include
            days_back: Fetch earthquakes from last N days
        """
        start_time = time.monotonic()
        endpoint = f"{BIPAD_BASE_URL}/earthquake/"

        # Calculate date filter
        from_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        from_date_str = from_date.strftime("%Y-%m-%dT%H:%M:%S")

        params = {
            "limit": limit,
            "ordering": "-created_on",
            "magnitude__gte": min_magnitude,
            "created_on__gte": from_date_str,
        }

        async with self._semaphore:
            try:
                async with self._session.get(endpoint, params=params) as response:
                    if response.status != 200:
                        return BIPADFetchResult(
                            endpoint="earthquakes",
                            success=False,
                            error=f"HTTP {response.status}",
                            fetch_time_ms=(time.monotonic() - start_time) * 1000,
                        )

                    data = await response.json()

                # Parse results
                results = data.get("results", [])
                alerts = []

                for item in results:
                    alert = self._parse_earthquake(item)
                    if alert:
                        alerts.append(alert)

                return BIPADFetchResult(
                    endpoint="earthquakes",
                    success=True,
                    alerts=alerts,
                    total_count=data.get("count", len(alerts)),
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )

            except asyncio.TimeoutError:
                return BIPADFetchResult(
                    endpoint="earthquakes",
                    success=False,
                    error="Timeout",
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )
            except Exception as e:
                logger.exception(f"Error fetching BIPAD earthquakes: {e}")
                return BIPADFetchResult(
                    endpoint="earthquakes",
                    success=False,
                    error=str(e),
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )

    async def fetch_fires(
        self,
        limit: int = 50,
    ) -> BIPADFetchResult:
        """
        Fetch fire incidents from BIPAD Portal's dedicated fire endpoint.
        This endpoint has more recent data than the general incident endpoint.
        """
        start_time = time.monotonic()
        endpoint = f"{BIPAD_BASE_URL}/fire/"

        params = {
            "limit": limit,
            "ordering": "-createdOn",
        }

        async with self._semaphore:
            try:
                async with self._session.get(endpoint, params=params) as response:
                    if response.status != 200:
                        return BIPADFetchResult(
                            endpoint="fires",
                            success=False,
                            error=f"HTTP {response.status}",
                            fetch_time_ms=(time.monotonic() - start_time) * 1000,
                        )

                    data = await response.json()

                results = data.get("results", [])
                incidents = []

                for item in results:
                    incident = self._parse_fire_incident(item)
                    if incident:
                        incidents.append(incident)

                return BIPADFetchResult(
                    endpoint="fires",
                    success=True,
                    incidents=incidents,
                    total_count=len(incidents),
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )

            except asyncio.TimeoutError:
                return BIPADFetchResult(
                    endpoint="fires",
                    success=False,
                    error="Timeout",
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )
            except Exception as e:
                logger.warning(f"Error fetching BIPAD fires: {e}")
                return BIPADFetchResult(
                    endpoint="fires",
                    success=False,
                    error=str(e),
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )

    def _parse_fire_incident(self, data: dict) -> Optional[FetchedIncident]:
        """Parse BIPAD fire endpoint response into FetchedIncident."""
        try:
            bipad_id = data.get("id")
            if not bipad_id:
                return None

            title = data.get("title") or f"Fire Incident #{bipad_id}"

            # Parse coordinates
            longitude, latitude = None, None
            point = data.get("point")
            if point and isinstance(point, dict):
                coords = point.get("coordinates", [])
                if len(coords) >= 2:
                    longitude, latitude = coords[0], coords[1]

            # Parse location from title (format: "Forest Fire at Location-Ward, District")
            district = None
            street_address = title
            if " at " in title:
                location_part = title.split(" at ", 1)[1]
                if ", " in location_part:
                    parts = location_part.rsplit(", ", 1)
                    street_address = parts[0]
                    district = parts[1] if len(parts) > 1 else None

            # Parse date
            incident_on = None
            created_str = data.get("createdOn")
            if created_str:
                incident_on = self._parse_datetime(created_str)

            return FetchedIncident(
                bipad_id=bipad_id,
                title=title,
                hazard_type="fire",
                hazard_id=10,  # BIPAD fire hazard ID
                longitude=longitude,
                latitude=latitude,
                street_address=street_address,
                district=district,
                incident_on=incident_on,
                raw_data=data,
            )
        except Exception as e:
            logger.warning(f"Error parsing BIPAD fire: {e}")
            return None

    async def fetch_all(
        self,
        incident_limit: int = 100,
        earthquake_limit: int = 50,
        fire_limit: int = 50,
        incident_days_back: int = 30,
        earthquake_days_back: int = 7,
        min_earthquake_magnitude: float = 4.0,
    ) -> list[BIPADFetchResult]:
        """
        Fetch all disaster data from BIPAD Portal concurrently.

        Returns list of fetch results for each endpoint.
        Now includes dedicated fire endpoint which has more recent data.
        """
        tasks = [
            self.fetch_incidents(
                limit=incident_limit,
                days_back=incident_days_back,
            ),
            self.fetch_earthquakes(
                limit=earthquake_limit,
                min_magnitude=min_earthquake_magnitude,
                days_back=earthquake_days_back,
            ),
            self.fetch_fires(
                limit=fire_limit,
            ),
        ]

        return await asyncio.gather(*tasks)

    def _parse_incident(self, data: dict) -> Optional[FetchedIncident]:
        """Parse BIPAD incident response into FetchedIncident."""
        try:
            bipad_id = data.get("id")
            if not bipad_id:
                return None

            # Parse title
            title = data.get("title") or data.get("title_en") or f"Incident #{bipad_id}"
            title_ne = data.get("titleNe") or data.get("title_ne")

            # Parse hazard type - BIPAD uses integer IDs
            hazard_id = data.get("hazard")
            if isinstance(hazard_id, int):
                hazard_type = BIPAD_HAZARD_MAP.get(hazard_id, HazardType.OTHER).value
            else:
                hazard_type = HazardType.OTHER.value

            # Parse coordinates from GeoJSON point
            longitude, latitude = None, None
            point = data.get("point")
            if point and isinstance(point, dict):
                coords = point.get("coordinates", [])
                if len(coords) >= 2:
                    longitude, latitude = coords[0], coords[1]

            # Note: BIPAD incident API returns loss as an ID reference, not the actual data
            # The loss details would need a separate API call to /api/v1/loss/{id}/
            # For now, we set these to 0 - the background task can fetch loss details later
            loss_id = data.get("loss")
            deaths = 0
            injured = 0
            missing = 0
            affected_families = 0
            estimated_loss = 0.0

            # If loss is a dict (in case API changes), try to extract data
            if isinstance(loss_id, dict):
                deaths = loss_id.get("peopleDeathCount", 0) or loss_id.get("death", 0) or 0
                injured = loss_id.get("peopleInjuredCount", 0) or loss_id.get("injured", 0) or 0
                missing = loss_id.get("peopleMissingCount", 0) or loss_id.get("missing", 0) or 0
                affected_families = loss_id.get("familyAffectedCount", 0) or loss_id.get("affected_family", 0) or 0
                estimated_loss = float(loss_id.get("estimatedLoss", 0) or loss_id.get("estimated_loss", 0) or 0)

            # Parse location - streetAddress in BIPAD format
            street_address = data.get("streetAddress") or data.get("street_address")
            ward_ids = data.get("wards") or data.get("ward_ids")

            # District and province are integer IDs in BIPAD, not objects
            district = None
            province = None

            # Try to extract district name from title or streetAddress
            if street_address:
                district = street_address

            if data.get("district"):
                if isinstance(data["district"], dict):
                    district = data["district"].get("title") or data["district"].get("name")
                # If it's an integer, we don't have the name

            if data.get("province"):
                if isinstance(data["province"], dict):
                    province = data["province"].get("id")
                elif isinstance(data["province"], int):
                    province = data["province"]

            # Parse incident date
            incident_on = None
            incident_str = data.get("incidentOn") or data.get("incident_on")
            if incident_str:
                incident_on = self._parse_datetime(incident_str)

            return FetchedIncident(
                bipad_id=bipad_id,
                title=title,
                title_ne=title_ne,
                hazard_type=hazard_type,
                hazard_id=hazard_id,
                longitude=longitude,
                latitude=latitude,
                street_address=street_address,
                ward_ids=ward_ids,
                district=district,
                province=province,
                deaths=deaths,
                injured=injured,
                missing=missing,
                affected_families=affected_families,
                estimated_loss=estimated_loss,
                verified=data.get("verified", False),
                incident_on=incident_on,
                raw_data=data,
            )
        except Exception as e:
            logger.warning(f"Error parsing BIPAD incident: {e}")
            return None

    def _parse_earthquake(self, data: dict) -> Optional[FetchedAlert]:
        """Parse BIPAD earthquake response into FetchedAlert."""
        try:
            bipad_id = data.get("id")
            if not bipad_id:
                return None

            # Parse magnitude and create title
            magnitude = data.get("magnitude")
            location = data.get("address") or data.get("location") or data.get("title") or "Unknown location"
            title = f"Earthquake M{magnitude:.1f}" if magnitude else f"Earthquake at {location}"

            # Parse coordinates from GeoJSON point
            longitude, latitude = None, None
            point = data.get("point")
            if point and isinstance(point, dict):
                coords = point.get("coordinates", [])
                if len(coords) >= 2:
                    longitude, latitude = coords[0], coords[1]

            # Alternative coordinate formats if point not found
            if longitude is None:
                coords = data.get("coordinates", {}) or {}
                if isinstance(coords, dict):
                    longitude = coords.get("longitude")
                    latitude = coords.get("latitude")
                elif isinstance(coords, list) and len(coords) >= 2:
                    longitude, latitude = coords[0], coords[1]

            if longitude is None:
                longitude = data.get("longitude") or data.get("lng")
            if latitude is None:
                latitude = data.get("latitude") or data.get("lat")

            # Parse issued date - try eventOn first (when earthquake happened)
            issued_at = None
            timestamp = data.get("eventOn") or data.get("timestamp") or data.get("createdOn")
            if timestamp:
                issued_at = self._parse_datetime(timestamp)
            if not issued_at:
                issued_at = datetime.now(timezone.utc)

            # Calculate alert level based on magnitude
            alert_level = "medium"
            if magnitude:
                if magnitude >= 6.0:
                    alert_level = "critical"
                elif magnitude >= 5.0:
                    alert_level = "high"
                elif magnitude >= 4.0:
                    alert_level = "medium"
                else:
                    alert_level = "low"

            # Parse district - could be ID or object
            district = location  # Use address/location as fallback
            if data.get("district"):
                if isinstance(data["district"], dict):
                    district = data["district"].get("title") or data["district"].get("name")
                elif isinstance(data["district"], int):
                    # It's just an ID, use address as district name
                    district = location

            return FetchedAlert(
                bipad_id=bipad_id,
                title=title,
                description=f"Earthquake of magnitude {magnitude} detected at {location}",
                alert_type="earthquake",
                alert_level=alert_level,
                longitude=longitude,
                latitude=latitude,
                location_name=location,
                district=district,
                magnitude=magnitude,
                depth_km=data.get("depth"),
                issued_at=issued_at,
                raw_data=data,
            )
        except Exception as e:
            logger.warning(f"Error parsing BIPAD earthquake: {e}")
            return None

    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """Parse datetime string from BIPAD API."""
        if not dt_str:
            return None

        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(dt_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        return None
