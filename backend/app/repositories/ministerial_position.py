"""Repository for ministerial positions."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ministerial_position import MinisterialPosition


class MinisterialPositionRepository:
    """Repository for ministerial positions CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, position_id: UUID) -> Optional[MinisterialPosition]:
        """Get a ministerial position by ID."""
        stmt = select(MinisterialPosition).where(MinisterialPosition.id == position_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_candidate_id(self, candidate_id: UUID) -> List[MinisterialPosition]:
        """Get all ministerial positions for a linked candidate."""
        stmt = (
            select(MinisterialPosition)
            .where(MinisterialPosition.linked_candidate_id == candidate_id)
            .order_by(MinisterialPosition.start_date.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_mp_id(self, mp_id: UUID) -> List[MinisterialPosition]:
        """Get all ministerial positions for a linked MP."""
        stmt = (
            select(MinisterialPosition)
            .where(MinisterialPosition.linked_mp_id == mp_id)
            .order_by(MinisterialPosition.start_date.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def search_by_name(
        self,
        name_en: str,
        name_ne: Optional[str] = None,
        limit: int = 20,
    ) -> List[MinisterialPosition]:
        """
        Search ministerial positions by person name.

        Uses case-insensitive partial matching on both English and Nepali names.
        Returns positions ordered by start date (most recent first).
        """
        # Build name search conditions
        conditions = []

        # English name (case-insensitive contains)
        if name_en:
            # Try different matching strategies
            name_lower = name_en.lower().strip()
            conditions.append(func.lower(MinisterialPosition.person_name_en).contains(name_lower))

            # Also try individual name parts (for names like "KP Sharma Oli" vs "KP Oli")
            name_parts = name_lower.split()
            if len(name_parts) >= 2:
                # Try first and last name
                conditions.append(
                    func.lower(MinisterialPosition.person_name_en).contains(name_parts[0])
                    & func.lower(MinisterialPosition.person_name_en).contains(name_parts[-1])
                )

        # Nepali name (exact or contains)
        if name_ne:
            conditions.append(MinisterialPosition.person_name_ne == name_ne)
            conditions.append(MinisterialPosition.person_name_ne.contains(name_ne))

        if not conditions:
            return []

        stmt = (
            select(MinisterialPosition)
            .where(or_(*conditions))
            .order_by(MinisterialPosition.start_date.desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_current_ministers(self) -> List[MinisterialPosition]:
        """Get all current ministerial positions."""
        stmt = (
            select(MinisterialPosition)
            .where(MinisterialPosition.is_current == True)
            .order_by(MinisterialPosition.position_type, MinisterialPosition.ministry)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_position_type(
        self,
        position_type: str,
        limit: int = 50,
    ) -> List[MinisterialPosition]:
        """Get all positions of a specific type (e.g., prime_minister)."""
        stmt = (
            select(MinisterialPosition)
            .where(MinisterialPosition.position_type == position_type)
            .order_by(MinisterialPosition.start_date.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ministry(
        self,
        ministry: str,
        limit: int = 50,
    ) -> List[MinisterialPosition]:
        """Get all positions for a specific ministry."""
        stmt = (
            select(MinisterialPosition)
            .where(func.lower(MinisterialPosition.ministry).contains(ministry.lower()))
            .order_by(MinisterialPosition.start_date.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, position: MinisterialPosition) -> MinisterialPosition:
        """Create a new ministerial position record."""
        self.db.add(position)
        await self.db.commit()
        await self.db.refresh(position)
        return position

    async def update(self, position: MinisterialPosition) -> MinisterialPosition:
        """Update an existing ministerial position."""
        await self.db.commit()
        await self.db.refresh(position)
        return position

    async def link_to_candidate(
        self,
        position_id: UUID,
        candidate_id: UUID,
    ) -> Optional[MinisterialPosition]:
        """Link a ministerial position to a candidate."""
        position = await self.get_by_id(position_id)
        if position:
            position.linked_candidate_id = candidate_id
            await self.db.commit()
            await self.db.refresh(position)
        return position

    async def link_to_mp(
        self,
        position_id: UUID,
        mp_id: UUID,
    ) -> Optional[MinisterialPosition]:
        """Link a ministerial position to an MP."""
        position = await self.get_by_id(position_id)
        if position:
            position.linked_mp_id = mp_id
            await self.db.commit()
            await self.db.refresh(position)
        return position
