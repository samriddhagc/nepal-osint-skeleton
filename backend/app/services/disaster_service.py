"""Disaster ingestion and processing service."""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.bipad_fetcher import (
    BIPADFetcher,
    FetchedIncident,
    FetchedAlert,
)
from app.models.disaster import DisasterIncident, DisasterAlert
from app.repositories.disaster import DisasterIncidentRepository, DisasterAlertRepository
from app.core.realtime_bus import publish_news

logger = logging.getLogger(__name__)


# Significance thresholds per user requirements
DEATH_THRESHOLD = 0       # Store if deaths > 0
LOSS_THRESHOLD = 2_500_000  # Store if loss > 25 lakhs NPR


class DisasterIngestionService:
    """
    Service for ingesting disaster data from BIPAD Portal.

    Handles:
    - Fetching from BIPAD API
    - Deduplication by BIPAD ID
    - Significance filtering (deaths > 0 OR loss > 25 lakhs)
    - Severity calculation
    - Database storage with coordinates
    - WebSocket broadcast for real-time updates
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.incident_repo = DisasterIncidentRepository(db)
        self.alert_repo = DisasterAlertRepository(db)

    async def ingest_all(
        self,
        incident_limit: int = 100,
        earthquake_limit: int = 50,
        fire_limit: int = 50,
        incident_days_back: int = 30,
        earthquake_days_back: int = 7,
        min_earthquake_magnitude: float = 4.0,
        filter_insignificant: bool = False,  # Changed to False to capture fire incidents
    ) -> dict:
        """
        Ingest all disaster data from BIPAD Portal.

        Args:
            incident_limit: Max incidents to fetch from general endpoint
            earthquake_limit: Max earthquakes to fetch
            fire_limit: Max fires to fetch from dedicated fire endpoint
            incident_days_back: Fetch incidents from last N days
            earthquake_days_back: Fetch earthquakes from last N days
            min_earthquake_magnitude: Minimum earthquake magnitude
            filter_insignificant: If True, only store incidents with deaths/loss

        Returns:
            Statistics dictionary with counts
        """
        stats = {
            "incidents_fetched": 0,
            "incidents_new": 0,
            "incidents_duplicate": 0,
            "incidents_filtered": 0,
            "alerts_fetched": 0,
            "alerts_new": 0,
            "alerts_duplicate": 0,
            "alerts_expired": 0,
            "errors": [],
        }

        new_incidents = []
        new_alerts = []

        async with BIPADFetcher() as fetcher:
            results = await fetcher.fetch_all(
                incident_limit=incident_limit,
                earthquake_limit=earthquake_limit,
                fire_limit=fire_limit,
                incident_days_back=incident_days_back,
                earthquake_days_back=earthquake_days_back,
                min_earthquake_magnitude=min_earthquake_magnitude,
            )

            for result in results:
                if not result.success:
                    stats["errors"].append(f"{result.endpoint}: {result.error}")
                    continue

                # Process incidents
                for fetched in result.incidents:
                    stats["incidents_fetched"] += 1
                    process_result, incident = await self._process_incident(
                        fetched, filter_insignificant
                    )
                    if process_result == "new" and incident:
                        stats["incidents_new"] += 1
                        new_incidents.append(incident)
                    elif process_result == "duplicate":
                        stats["incidents_duplicate"] += 1
                    elif process_result == "filtered":
                        stats["incidents_filtered"] += 1

                # Process alerts (earthquakes)
                for fetched in result.alerts:
                    stats["alerts_fetched"] += 1
                    process_result, alert = await self._process_alert(fetched)
                    if process_result == "new" and alert:
                        stats["alerts_new"] += 1
                        new_alerts.append(alert)
                    elif process_result == "duplicate":
                        stats["alerts_duplicate"] += 1

        # Deactivate expired alerts
        stats["alerts_expired"] = await self.alert_repo.deactivate_expired()

        # Broadcast new disasters via WebSocket
        await self._broadcast_new_disasters(new_incidents, new_alerts)

        logger.info(
            f"BIPAD ingestion complete: {stats['incidents_new']} new incidents, "
            f"{stats['alerts_new']} new alerts, {stats['incidents_filtered']} filtered"
        )

        return stats

    async def _process_incident(
        self,
        fetched: FetchedIncident,
        filter_insignificant: bool = True,
    ) -> tuple[str, Optional[DisasterIncident]]:
        """
        Process a fetched incident.

        Returns:
            Tuple of (status, incident) where status is "new", "duplicate", or "filtered"
        """
        # Check for duplicate
        if await self.incident_repo.exists_by_bipad_id(fetched.bipad_id):
            return "duplicate", None

        # Check significance threshold if filtering enabled
        if filter_insignificant and not self._is_significant_incident(fetched):
            return "filtered", None

        # Calculate severity
        severity = DisasterIncident.calculate_severity(
            deaths=fetched.deaths,
            injured=fetched.injured,
            estimated_loss=fetched.estimated_loss,
        )

        # Create incident record with coordinates
        incident = DisasterIncident(
            bipad_id=fetched.bipad_id,
            title=fetched.title,
            title_ne=fetched.title_ne,
            hazard_type=fetched.hazard_type,
            hazard_id=fetched.hazard_id,
            longitude=fetched.longitude,
            latitude=fetched.latitude,
            street_address=fetched.street_address,
            ward_ids=fetched.ward_ids,
            district=fetched.district,
            province=fetched.province,
            deaths=fetched.deaths,
            injured=fetched.injured,
            missing=fetched.missing,
            affected_families=fetched.affected_families,
            estimated_loss=fetched.estimated_loss,
            verified=fetched.verified,
            severity=severity,
            incident_on=fetched.incident_on,
            raw_data=fetched.raw_data,
        )

        incident = await self.incident_repo.create(incident)
        return "new", incident

    async def _process_alert(
        self,
        fetched: FetchedAlert,
    ) -> tuple[str, Optional[DisasterAlert]]:
        """
        Process a fetched alert.

        Returns:
            Tuple of (status, alert) where status is "new" or "duplicate"
        """
        # Check for duplicate
        if await self.alert_repo.exists_by_bipad_id(fetched.bipad_id):
            return "duplicate", None

        # Create alert record with coordinates
        alert = DisasterAlert(
            bipad_id=fetched.bipad_id,
            title=fetched.title,
            description=fetched.description,
            alert_type=fetched.alert_type,
            alert_level=fetched.alert_level,
            longitude=fetched.longitude,
            latitude=fetched.latitude,
            location_name=fetched.location_name,
            district=fetched.district,
            magnitude=fetched.magnitude,
            depth_km=fetched.depth_km,
            is_active=True,
            expires_at=fetched.expires_at,
            issued_at=fetched.issued_at or datetime.now(timezone.utc),
            raw_data=fetched.raw_data,
        )

        alert = await self.alert_repo.create(alert)
        return "new", alert

    def _is_significant_incident(self, incident: FetchedIncident) -> bool:
        """
        Check if incident meets significance threshold.

        User requirement: deaths > 0 OR estimated_loss > 25 lakhs (2.5M NPR)
        """
        return incident.deaths > DEATH_THRESHOLD or incident.estimated_loss > LOSS_THRESHOLD

    async def _broadcast_new_disasters(
        self,
        incidents: list[DisasterIncident],
        alerts: list[DisasterAlert],
    ) -> None:
        """Publish new disasters to Redis for WebSocket broadcast."""
        try:
            # Broadcast new incidents
            for incident in incidents:
                await publish_news(
                    {
                        "type": "new_disaster_incident",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": {
                            "id": str(incident.id),
                            "bipad_id": incident.bipad_id,
                            "title": incident.title,
                            "hazard_type": incident.hazard_type,
                            "district": incident.district,
                            "deaths": incident.deaths,
                            "injured": incident.injured,
                            "estimated_loss": incident.estimated_loss,
                            "severity": incident.severity,
                            "incident_on": incident.incident_on.isoformat() if incident.incident_on else None,
                            "coordinates": [incident.longitude, incident.latitude] if incident.longitude else None,
                        },
                    }
                )

            # Broadcast new alerts
            for alert in alerts:
                await publish_news(
                    {
                        "type": "new_disaster_alert",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": {
                            "id": str(alert.id),
                            "bipad_id": alert.bipad_id,
                            "title": alert.title,
                            "alert_type": alert.alert_type,
                            "alert_level": alert.alert_level,
                            "magnitude": alert.magnitude,
                            "is_active": alert.is_active,
                            "issued_at": alert.issued_at.isoformat() if alert.issued_at else None,
                            "coordinates": [alert.longitude, alert.latitude] if alert.longitude else None,
                        },
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to broadcast disasters: {e}")

    async def get_summary(self, hours: int = 168) -> dict:
        """
        Get summary statistics for disasters.

        Args:
            hours: Time window in hours (default 7 days)
        """
        total_incidents = await self.incident_repo.count_total(hours=hours)
        total_alerts = await self.alert_repo.count_total(hours=hours)
        active_alerts = await self.alert_repo.count_total(active_only=True)
        incidents_by_type = await self.incident_repo.count_by_type(hours=hours)
        incidents_by_severity = await self.incident_repo.count_by_severity(hours=hours)
        casualties = await self.incident_repo.get_total_casualties(hours=hours)

        # Count recent significant earthquakes
        recent_earthquakes = await self.alert_repo.get_recent_earthquakes(
            hours=hours,
            min_magnitude=4.0,
            limit=100,
        )

        return {
            "total_incidents": total_incidents,
            "total_alerts": total_alerts,
            "active_alerts": active_alerts,
            "incidents_by_type": incidents_by_type,
            "incidents_by_severity": incidents_by_severity,
            "total_deaths": casualties["deaths"],
            "total_injured": casualties["injured"],
            "total_loss_npr": casualties["estimated_loss"],
            "recent_earthquakes": len(recent_earthquakes),
        }

    async def get_map_events(
        self,
        hours: int = 72,
        incident_limit: int = 200,
        alert_limit: int = 100,
    ) -> dict:
        """
        Get all disaster events for map display.

        Returns incidents and alerts with coordinates in Leaflet format.
        """
        incidents = await self.incident_repo.get_for_map(hours=hours, limit=incident_limit)
        alerts = await self.alert_repo.get_for_map(hours=hours, limit=alert_limit)

        # Transform to map event format
        incident_events = [
            {
                "id": inc["id"],
                "type": "incident",
                "title": inc["title"],
                "coordinates": inc["coordinates"],
                "severity": inc["severity"] or "low",
                "timestamp": inc["incident_on"],
                "hazard_type": inc["hazard_type"],
                "loss": {
                    "deaths": inc["deaths"],
                    "injured": inc["injured"],
                    "missing": inc["missing"],
                    "estimated_loss": inc["estimated_loss"],
                },
                "district": inc["district"],
                "verified": inc["verified"],
            }
            for inc in incidents
        ]

        alert_events = [
            {
                "id": alert["id"],
                "type": "alert" if alert["alert_type"] != "earthquake" else "earthquake",
                "title": alert["title"],
                "coordinates": alert["coordinates"],
                "severity": alert["alert_level"],
                "timestamp": alert["issued_at"],
                "alert_type": alert["alert_type"],
                "alert_level": alert["alert_level"],
                "magnitude": alert["magnitude"],
                "depth_km": alert["depth_km"],
                "is_active": alert["is_active"],
            }
            for alert in alerts
        ]

        return {
            "incidents": incident_events,
            "alerts": alert_events,
            "total_incidents": len(incident_events),
            "total_alerts": len(alert_events),
        }
