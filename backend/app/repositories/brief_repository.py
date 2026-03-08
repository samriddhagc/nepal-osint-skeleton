"""Repository for SituationBrief, ProvinceSitrep, and FakeNewsFlag CRUD."""
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.situation_brief import SituationBrief, ProvinceSitrep, FakeNewsFlag


class BriefRepository:
    """CRUD operations for situation briefs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_latest(self) -> Optional[SituationBrief]:
        """Get the most recent completed brief with all relationships."""
        result = await self.db.execute(
            select(SituationBrief)
            .where(SituationBrief.status == "completed")
            .options(
                selectinload(SituationBrief.province_sitreps),
                selectinload(SituationBrief.fake_news_flags),
            )
            .order_by(desc(SituationBrief.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, brief_id: UUID) -> Optional[SituationBrief]:
        """Get a specific brief by ID with all relationships."""
        result = await self.db.execute(
            select(SituationBrief)
            .where(SituationBrief.id == brief_id)
            .options(
                selectinload(SituationBrief.province_sitreps),
                selectinload(SituationBrief.fake_news_flags),
            )
        )
        return result.scalar_one_or_none()

    async def get_province_sitrep(
        self, province_id: int,
    ) -> Optional[ProvinceSitrep]:
        """Get the latest sitrep for a specific province."""
        result = await self.db.execute(
            select(ProvinceSitrep)
            .join(SituationBrief, ProvinceSitrep.brief_id == SituationBrief.id)
            .where(
                SituationBrief.status == "completed",
                ProvinceSitrep.province_id == province_id,
            )
            .order_by(desc(SituationBrief.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_recent_flags(self, limit: int = 20) -> list[FakeNewsFlag]:
        """Get recent fake news flags."""
        result = await self.db.execute(
            select(FakeNewsFlag)
            .order_by(desc(FakeNewsFlag.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_history(self, limit: int = 10) -> list[SituationBrief]:
        """Get brief history (without full relationships for efficiency)."""
        result = await self.db.execute(
            select(SituationBrief)
            .order_by(desc(SituationBrief.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
