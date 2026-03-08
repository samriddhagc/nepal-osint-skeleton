"""Curfew alert repository for database operations."""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curfew_alert import CurfewAlert


class CurfewRepository:
    """Repository for CurfewAlert database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, alert_id: UUID) -> Optional[CurfewAlert]:
        """Get curfew alert by ID."""
        result = await self.db.execute(
            select(CurfewAlert).where(CurfewAlert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def create(self, alert: CurfewAlert) -> CurfewAlert:
        """Create a new curfew alert."""
        self.db.add(alert)
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def update(self, alert: CurfewAlert) -> CurfewAlert:
        """Update an existing curfew alert."""
        alert.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def get_active_alerts(self) -> List[CurfewAlert]:
        """Get all currently active curfew alerts."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(CurfewAlert)
            .where(
                and_(
                    CurfewAlert.is_active == True,
                    CurfewAlert.expires_at > now,
                )
            )
            .order_by(CurfewAlert.detected_at.desc())
        )
        return list(result.scalars().all())

    async def get_active_by_district(self, district: str) -> Optional[CurfewAlert]:
        """Get active curfew alert for a specific district."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(CurfewAlert)
            .where(
                and_(
                    CurfewAlert.district.ilike(district),
                    CurfewAlert.is_active == True,
                    CurfewAlert.expires_at > now,
                )
            )
            .order_by(CurfewAlert.detected_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_province(self, province: str) -> List[CurfewAlert]:
        """Get all active curfew alerts for a province."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(CurfewAlert)
            .where(
                and_(
                    CurfewAlert.province == province,
                    CurfewAlert.is_active == True,
                    CurfewAlert.expires_at > now,
                )
            )
            .order_by(CurfewAlert.detected_at.desc())
        )
        return list(result.scalars().all())

    async def expire_alerts(self) -> int:
        """Mark expired alerts as inactive. Returns count of expired alerts."""
        now = datetime.now(timezone.utc)

        # Find expired but still active alerts
        result = await self.db.execute(
            select(CurfewAlert)
            .where(
                and_(
                    CurfewAlert.is_active == True,
                    CurfewAlert.expires_at <= now,
                )
            )
        )
        expired_alerts = result.scalars().all()

        count = 0
        for alert in expired_alerts:
            alert.is_active = False
            alert.updated_at = now
            count += 1

        if count > 0:
            await self.db.commit()

        return count

    async def deactivate(self, alert_id: UUID) -> bool:
        """Manually deactivate a curfew alert."""
        alert = await self.get_by_id(alert_id)
        if not alert:
            return False

        alert.is_active = False
        alert.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True

    async def extend_alert(self, alert_id: UUID, hours: int = 24) -> Optional[CurfewAlert]:
        """Extend an alert's expiration time."""
        alert = await self.get_by_id(alert_id)
        if not alert:
            return None

        from datetime import timedelta
        alert.expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
        alert.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def confirm_alert(self, alert_id: UUID) -> Optional[CurfewAlert]:
        """Mark an alert as manually confirmed."""
        alert = await self.get_by_id(alert_id)
        if not alert:
            return None

        alert.is_confirmed = True
        alert.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def get_stats(self) -> dict:
        """Get curfew alert statistics."""
        now = datetime.now(timezone.utc)

        # Active alerts count
        active_query = select(func.count(CurfewAlert.id)).where(
            and_(
                CurfewAlert.is_active == True,
                CurfewAlert.expires_at > now,
            )
        )
        active_result = await self.db.execute(active_query)
        active_count = active_result.scalar() or 0

        # Total alerts
        total_query = select(func.count(CurfewAlert.id))
        total_result = await self.db.execute(total_query)
        total_count = total_result.scalar() or 0

        # Alerts by province
        province_query = select(
            CurfewAlert.province, func.count(CurfewAlert.id)
        ).where(
            and_(
                CurfewAlert.is_active == True,
                CurfewAlert.expires_at > now,
            )
        ).group_by(CurfewAlert.province)
        province_result = await self.db.execute(province_query)
        by_province = {row[0]: row[1] for row in province_result.all() if row[0]}

        # Alerts by severity
        severity_query = select(
            CurfewAlert.severity, func.count(CurfewAlert.id)
        ).where(
            and_(
                CurfewAlert.is_active == True,
                CurfewAlert.expires_at > now,
            )
        ).group_by(CurfewAlert.severity)
        severity_result = await self.db.execute(severity_query)
        by_severity = {row[0]: row[1] for row in severity_result.all()}

        return {
            "active": active_count,
            "total": total_count,
            "by_province": by_province,
            "by_severity": by_severity,
        }

    async def get_recent_alerts(self, limit: int = 10) -> List[CurfewAlert]:
        """Get most recent curfew alerts (active or not)."""
        result = await self.db.execute(
            select(CurfewAlert)
            .order_by(CurfewAlert.detected_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_history_for_district(
        self,
        district: str,
        limit: int = 10,
    ) -> List[CurfewAlert]:
        """Get curfew history for a specific district."""
        result = await self.db.execute(
            select(CurfewAlert)
            .where(CurfewAlert.district.ilike(district))
            .order_by(CurfewAlert.detected_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
