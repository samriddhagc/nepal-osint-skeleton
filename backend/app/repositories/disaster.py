"""Disaster repository for database operations."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.disaster import DisasterIncident, DisasterAlert


class DisasterIncidentRepository:
    """Repository for DisasterIncident database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, incident_id: UUID) -> Optional[DisasterIncident]:
        """Get incident by ID."""
        result = await self.db.execute(
            select(DisasterIncident).where(DisasterIncident.id == incident_id)
        )
        return result.scalar_one_or_none()

    async def get_by_bipad_id(self, bipad_id: int) -> Optional[DisasterIncident]:
        """Get incident by BIPAD ID."""
        result = await self.db.execute(
            select(DisasterIncident).where(DisasterIncident.bipad_id == bipad_id)
        )
        return result.scalar_one_or_none()

    async def exists_by_bipad_id(self, bipad_id: int) -> bool:
        """Check if incident exists by BIPAD ID."""
        result = await self.db.execute(
            select(func.count(DisasterIncident.id)).where(
                DisasterIncident.bipad_id == bipad_id
            )
        )
        return (result.scalar() or 0) > 0

    async def create(self, incident: DisasterIncident) -> DisasterIncident:
        """Create a new incident."""
        self.db.add(incident)
        await self.db.commit()
        await self.db.refresh(incident)
        return incident

    async def list_incidents(
        self,
        page: int = 1,
        page_size: int = 20,
        hazard_type: Optional[str] = None,
        severity: Optional[str] = None,
        district: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> tuple[list[DisasterIncident], int]:
        """List incidents with pagination and filters."""
        query = select(DisasterIncident)
        count_query = select(func.count(DisasterIncident.id))

        filters = []
        if hazard_type:
            filters.append(DisasterIncident.hazard_type == hazard_type)
        if severity:
            filters.append(DisasterIncident.severity == severity)
        if district:
            filters.append(DisasterIncident.district.ilike(f"%{district}%"))
        if from_date:
            filters.append(DisasterIncident.incident_on >= from_date)
        if to_date:
            filters.append(DisasterIncident.incident_on <= to_date)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = await self.db.scalar(count_query) or 0

        query = query.order_by(DisasterIncident.incident_on.desc().nullslast())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        incidents = list(result.scalars().all())

        return incidents, total

    async def get_recent(
        self,
        hours: int = 72,
        limit: int = 100,
        hazard_type: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> list[DisasterIncident]:
        """Get recent incidents within time window."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = select(DisasterIncident).where(DisasterIncident.created_at >= cutoff)

        if hazard_type:
            query = query.where(DisasterIncident.hazard_type == hazard_type)
        if severity:
            query = query.where(DisasterIncident.severity == severity)

        query = query.order_by(DisasterIncident.incident_on.desc().nullslast()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_significant_incidents(
        self,
        hours: int = 168,  # 7 days
        limit: int = 50,
    ) -> list[DisasterIncident]:
        """
        Get significant incidents (deaths > 0 OR estimated_loss > 25 lakhs).

        User requirement threshold: deaths > 0 OR loss > 2,500,000 NPR
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = (
            select(DisasterIncident)
            .where(
                DisasterIncident.created_at >= cutoff,
                (DisasterIncident.deaths > 0) | (DisasterIncident.estimated_loss > 2_500_000),
            )
            .order_by(DisasterIncident.severity.desc(), DisasterIncident.incident_on.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_for_map(
        self,
        hours: int = 72,
        limit: int = 200,
    ) -> list[dict]:
        """
        Get incidents with coordinates for map display.

        Filters by incident_on (event time), not created_at (ingestion time).
        Returns list of dicts with [longitude, latitude] format for Leaflet.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = (
            select(DisasterIncident)
            .where(
                DisasterIncident.incident_on >= cutoff,
                DisasterIncident.longitude.isnot(None),
                DisasterIncident.latitude.isnot(None),
            )
            .order_by(DisasterIncident.incident_on.desc().nullslast())
            .limit(limit)
        )

        result = await self.db.execute(query)
        incidents = result.scalars().all()

        return [
            {
                "id": str(inc.id),
                "bipad_id": inc.bipad_id,
                "title": inc.title,
                "hazard_type": inc.hazard_type,
                "district": inc.district,
                "deaths": inc.deaths,
                "injured": inc.injured,
                "missing": inc.missing,
                "estimated_loss": inc.estimated_loss,
                "severity": inc.severity,
                "verified": inc.verified,
                "incident_on": inc.incident_on.isoformat() if inc.incident_on else None,
                "coordinates": [inc.longitude, inc.latitude],
            }
            for inc in incidents
        ]

    async def count_total(self, hours: Optional[int] = None) -> int:
        """Count total incidents, optionally within time window (by event time)."""
        query = select(func.count(DisasterIncident.id))

        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            query = query.where(DisasterIncident.incident_on >= cutoff)

        return await self.db.scalar(query) or 0

    async def count_by_type(self, hours: int = 168) -> dict[str, int]:
        """Get incident count by hazard type within time window (by event time)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(DisasterIncident.hazard_type, func.count(DisasterIncident.id))
            .where(DisasterIncident.incident_on >= cutoff)
            .group_by(DisasterIncident.hazard_type)
            .order_by(func.count(DisasterIncident.id).desc())
        )

        return {row[0]: row[1] for row in result.all()}

    async def count_by_severity(self, hours: int = 168) -> dict[str, int]:
        """Get incident count by severity within time window (by event time)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(DisasterIncident.severity, func.count(DisasterIncident.id))
            .where(DisasterIncident.incident_on >= cutoff)
            .group_by(DisasterIncident.severity)
            .order_by(func.count(DisasterIncident.id).desc())
        )

        return {row[0] or "unknown": row[1] for row in result.all()}

    async def get_total_casualties(self, hours: int = 168) -> dict[str, int]:
        """Get total deaths and injuries within time window (by event time)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(
                func.coalesce(func.sum(DisasterIncident.deaths), 0).label("deaths"),
                func.coalesce(func.sum(DisasterIncident.injured), 0).label("injured"),
                func.coalesce(func.sum(DisasterIncident.estimated_loss), 0).label("loss"),
            ).where(DisasterIncident.incident_on >= cutoff)
        )

        row = result.first()
        return {
            "deaths": int(row.deaths) if row else 0,
            "injured": int(row.injured) if row else 0,
            "estimated_loss": float(row.loss) if row else 0.0,
        }


class DisasterAlertRepository:
    """Repository for DisasterAlert database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, alert_id: UUID) -> Optional[DisasterAlert]:
        """Get alert by ID."""
        result = await self.db.execute(
            select(DisasterAlert).where(DisasterAlert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def get_by_bipad_id(self, bipad_id: int) -> Optional[DisasterAlert]:
        """Get alert by BIPAD ID."""
        result = await self.db.execute(
            select(DisasterAlert).where(DisasterAlert.bipad_id == bipad_id)
        )
        return result.scalar_one_or_none()

    async def exists_by_bipad_id(self, bipad_id: int) -> bool:
        """Check if alert exists by BIPAD ID."""
        result = await self.db.execute(
            select(func.count(DisasterAlert.id)).where(
                DisasterAlert.bipad_id == bipad_id
            )
        )
        return (result.scalar() or 0) > 0

    async def create(self, alert: DisasterAlert) -> DisasterAlert:
        """Create a new alert."""
        self.db.add(alert)
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def list_alerts(
        self,
        page: int = 1,
        page_size: int = 20,
        alert_type: Optional[str] = None,
        alert_level: Optional[str] = None,
        is_active: Optional[bool] = None,
        district: Optional[str] = None,
    ) -> tuple[list[DisasterAlert], int]:
        """List alerts with pagination and filters."""
        query = select(DisasterAlert)
        count_query = select(func.count(DisasterAlert.id))

        filters = []
        if alert_type:
            filters.append(DisasterAlert.alert_type == alert_type)
        if alert_level:
            filters.append(DisasterAlert.alert_level == alert_level)
        if is_active is not None:
            filters.append(DisasterAlert.is_active == is_active)
        if district:
            filters.append(DisasterAlert.district.ilike(f"%{district}%"))

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = await self.db.scalar(count_query) or 0

        query = query.order_by(DisasterAlert.issued_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        alerts = list(result.scalars().all())

        return alerts, total

    async def get_active_alerts(
        self,
        alert_type: Optional[str] = None,
        alert_level: Optional[str] = None,
        limit: int = 50,
    ) -> list[DisasterAlert]:
        """Get currently active alerts."""
        query = select(DisasterAlert).where(DisasterAlert.is_active == True)

        if alert_type:
            query = query.where(DisasterAlert.alert_type == alert_type)
        if alert_level:
            query = query.where(DisasterAlert.alert_level == alert_level)

        query = query.order_by(DisasterAlert.issued_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_recent_earthquakes(
        self,
        hours: int = 24,
        min_magnitude: float = 4.0,
        limit: int = 50,
    ) -> list[DisasterAlert]:
        """Get recent earthquakes above minimum magnitude."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = (
            select(DisasterAlert)
            .where(
                DisasterAlert.alert_type == "earthquake",
                DisasterAlert.issued_at >= cutoff,
            )
        )

        if min_magnitude:
            query = query.where(DisasterAlert.magnitude >= min_magnitude)

        query = query.order_by(DisasterAlert.issued_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_for_map(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get alerts with coordinates for map display.

        Returns list of dicts with [longitude, latitude] format for Leaflet.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = (
            select(DisasterAlert)
            .where(
                DisasterAlert.created_at >= cutoff,
                DisasterAlert.longitude.isnot(None),
                DisasterAlert.latitude.isnot(None),
            )
            .order_by(DisasterAlert.issued_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        alerts = result.scalars().all()

        return [
            {
                "id": str(alert.id),
                "bipad_id": alert.bipad_id,
                "title": alert.title,
                "alert_type": alert.alert_type,
                "alert_level": alert.alert_level,
                "location_name": alert.location_name,
                "district": alert.district,
                "magnitude": alert.magnitude,
                "depth_km": alert.depth_km,
                "is_active": alert.is_active,
                "issued_at": alert.issued_at.isoformat() if alert.issued_at else None,
                "coordinates": [alert.longitude, alert.latitude],
            }
            for alert in alerts
        ]

    async def get_recent_by_event_time(
        self,
        hours: int = 72,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get alerts filtered by event time (issued_at), not ingestion time.

        This is important for showing truly recent events, not old data we just ingested.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = (
            select(DisasterAlert)
            .where(
                DisasterAlert.issued_at >= cutoff,
                DisasterAlert.longitude.isnot(None),
                DisasterAlert.latitude.isnot(None),
            )
            .order_by(DisasterAlert.issued_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        alerts = result.scalars().all()

        return [
            {
                "id": str(alert.id),
                "bipad_id": alert.bipad_id,
                "title": alert.title,
                "alert_type": alert.alert_type,
                "alert_level": alert.alert_level,
                "location_name": alert.location_name,
                "district": alert.district,
                "magnitude": alert.magnitude,
                "depth_km": alert.depth_km,
                "is_active": alert.is_active,
                "issued_at": alert.issued_at.isoformat() if alert.issued_at else None,
                "coordinates": [alert.longitude, alert.latitude],
            }
            for alert in alerts
        ]

    async def deactivate_expired(self) -> int:
        """Deactivate alerts that have expired."""
        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            update(DisasterAlert)
            .where(
                DisasterAlert.is_active == True,
                DisasterAlert.expires_at.isnot(None),
                DisasterAlert.expires_at < now,
            )
            .values(is_active=False, updated_at=now)
        )

        await self.db.commit()
        return result.rowcount

    async def count_total(self, hours: Optional[int] = None, active_only: bool = False) -> int:
        """Count total alerts, optionally within time window (by event time) or active only."""
        query = select(func.count(DisasterAlert.id))

        filters = []
        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            filters.append(DisasterAlert.issued_at >= cutoff)
        if active_only:
            filters.append(DisasterAlert.is_active == True)

        if filters:
            query = query.where(and_(*filters))

        return await self.db.scalar(query) or 0

    async def count_by_type(self, hours: int = 168) -> dict[str, int]:
        """Get alert count by type within time window (by event time)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(DisasterAlert.alert_type, func.count(DisasterAlert.id))
            .where(DisasterAlert.issued_at >= cutoff)
            .group_by(DisasterAlert.alert_type)
        )

        return {row[0]: row[1] for row in result.all()}
