"""Story repository for database operations."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story import Story
from app.models.story_cluster import StoryCluster


class StoryRepository:
    """Repository for Story database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, story_id: UUID) -> Optional[Story]:
        """Get story by ID."""
        result = await self.db.execute(
            select(Story).where(Story.id == story_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[Story]:
        """Get story by external ID (dedup hash)."""
        result = await self.db.execute(
            select(Story).where(Story.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def exists_by_external_id(self, external_id: str) -> bool:
        """Check if story exists by external ID."""
        result = await self.db.execute(
            select(func.count(Story.id)).where(Story.external_id == external_id)
        )
        return (result.scalar() or 0) > 0

    async def exists_by_url(self, url: str) -> bool:
        """Check if story exists by URL."""
        result = await self.db.execute(
            select(func.count(Story.id)).where(Story.url == url)
        )
        return (result.scalar() or 0) > 0

    async def create(self, story: Story) -> Story:
        """Create a new story."""
        self.db.add(story)
        await self.db.commit()
        await self.db.refresh(story)
        return story

    async def create_many(self, stories: list[Story]) -> int:
        """Bulk create stories, returning count of created."""
        self.db.add_all(stories)
        await self.db.commit()
        return len(stories)

    async def list_stories(
        self,
        page: int = 1,
        page_size: int = 20,
        source_id: Optional[str] = None,
        source_ids: Optional[list[str]] = None,
        category: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        nepal_only: bool = True,
        multi_source_only: bool = False,
    ) -> tuple[list[Story], int]:
        """List stories with pagination and filters."""
        query = select(Story)
        count_query = select(func.count(Story.id)).select_from(Story)

        if multi_source_only:
            query = query.join(StoryCluster, Story.cluster_id == StoryCluster.id)
            count_query = count_query.join(StoryCluster, Story.cluster_id == StoryCluster.id)

        # Build filters
        filters = []
        if source_id:
            filters.append(Story.source_id.ilike(f"{source_id}%"))
        if source_ids:
            normalized_source_ids = [source.strip() for source in source_ids if source and source.strip()]
            if normalized_source_ids:
                filters.append(Story.source_id.in_(normalized_source_ids))
        if category:
            filters.append(Story.category == category)
        if from_date:
            filters.append(Story.published_at >= from_date)
        if to_date:
            filters.append(Story.published_at <= to_date)
        if nepal_only:
            filters.append(Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"]))
        if multi_source_only:
            filters.append(StoryCluster.source_count > 1)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Get total count
        total = await self.db.scalar(count_query) or 0

        # Get paginated results
        query = query.order_by(Story.published_at.desc().nullslast())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        stories = list(result.scalars().all())

        return stories, total

    async def list_sources(
        self,
        category: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        nepal_only: bool = True,
        multi_source_only: bool = False,
        limit: int = 200,
    ) -> list[dict[str, str | int]]:
        """List distinct story sources with counts for filter UIs."""
        source_name_expr = func.coalesce(
            func.max(Story.source_name),
            Story.source_id,
        ).label("source_name")
        story_count_expr = func.count(Story.id).label("story_count")

        query = select(
            Story.source_id.label("source_id"),
            source_name_expr,
            story_count_expr,
        )

        if multi_source_only:
            query = query.join(StoryCluster, Story.cluster_id == StoryCluster.id)

        filters = []
        if category:
            filters.append(Story.category == category)
        if from_date:
            filters.append(Story.published_at >= from_date)
        if to_date:
            filters.append(Story.published_at <= to_date)
        if nepal_only:
            filters.append(Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"]))
        if multi_source_only:
            filters.append(StoryCluster.source_count > 1)

        if filters:
            query = query.where(and_(*filters))

        query = (
            query.group_by(Story.source_id)
            .order_by(desc(story_count_expr), Story.source_id.asc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return [
            {
                "source_id": str(row.source_id),
                "source_name": str(row.source_name or row.source_id),
                "story_count": int(row.story_count or 0),
            }
            for row in result.all()
        ]

    async def get_recent(
        self,
        hours: int = 24,
        limit: int = 100,
        nepal_only: bool = True,
        category: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> list[Story]:
        """Get recent stories within time window."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = select(Story).where(Story.created_at >= cutoff)

        if nepal_only:
            query = query.where(
                Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"])
            )

        if category:
            query = query.where(Story.category == category)

        if severity:
            query = query.where(Story.severity == severity)

        # Order by the best available timestamp so feeds stay "live" even when
        # a source does not provide published_at.
        query = query.order_by(
            func.coalesce(Story.published_at, Story.created_at).desc()
        ).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_by_source(
        self,
        hours: int = 72,
    ) -> dict[str, int]:
        """Get story count by source within time window."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(Story.source_id, func.count(Story.id))
            .where(Story.created_at >= cutoff)
            .group_by(Story.source_id)
            .order_by(func.count(Story.id).desc())
            .limit(20)
        )

        return {row[0]: row[1] for row in result.all()}

    async def count_total(self, hours: Optional[int] = None, nepal_only: bool = True) -> int:
        """Count total stories, optionally within time window."""
        query = select(func.count(Story.id))

        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            query = query.where(Story.created_at >= cutoff)

        if nepal_only:
            query = query.where(
                Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"])
            )

        return await self.db.scalar(query) or 0

    async def get_hourly_trend(self, hours: int = 72) -> list[tuple[datetime, int]]:
        """Get hourly story counts for trend chart."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Use subquery to avoid GROUP BY issues
        hour_col = func.date_trunc("hour", Story.published_at).label("hour")

        result = await self.db.execute(
            select(hour_col, func.count(Story.id).label("count"))
            .where(
                Story.created_at >= cutoff,
                Story.published_at.isnot(None),
            )
            .group_by(hour_col)
            .order_by(hour_col)
        )

        return [(row.hour, row.count) for row in result.all()]

    async def get_stories_today_nepal(self, nepal_only: bool = True) -> list[Story]:
        """
        Get all stories from today in Nepal time (UTC+5:45).

        Nepal time starts at 00:00 NPT which is 18:15 UTC the previous day.
        Stories reset at midnight Nepal time.
        """
        from sqlalchemy import func, or_

        # Nepal is UTC+5:45
        nepal_offset = timedelta(hours=5, minutes=45)

        # Get current time in Nepal
        now_utc = datetime.now(timezone.utc)
        now_nepal = now_utc + nepal_offset

        # Calculate start of today in Nepal time, then convert to UTC
        nepal_midnight = now_nepal.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_day_utc = nepal_midnight - nepal_offset

        # Make it timezone-aware UTC
        start_of_day_utc = start_of_day_utc.replace(tzinfo=timezone.utc)

        # Use published_at if available, otherwise fall back to created_at
        # Many RSS feeds don't include publication dates, so created_at is the fallback
        query = select(Story).where(
            or_(
                Story.published_at >= start_of_day_utc,
                # If published_at is NULL, use created_at instead
                (Story.published_at.is_(None)) & (Story.created_at >= start_of_day_utc)
            )
        )

        if nepal_only:
            query = query.where(
                Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"])
            )

        # Order by published_at first, then created_at as fallback
        query = query.order_by(
            func.coalesce(Story.published_at, Story.created_at).desc()
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_recent_stories_limited(
        self, hours: int = 6, limit: int = 50, nepal_only: bool = True
    ) -> list[Story]:
        """Get recent stories within `hours`, capped at `limit`. For WebSocket initial load."""
        from sqlalchemy import func, or_

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = select(Story).where(
            or_(
                Story.published_at >= cutoff,
                (Story.published_at.is_(None)) & (Story.created_at >= cutoff),
            )
        )

        if nepal_only:
            query = query.where(
                Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"])
            )

        query = query.order_by(
            func.coalesce(Story.published_at, Story.created_at).desc()
        ).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search_by_name(
        self,
        name: str,
        name_ne: Optional[str] = None,
        hours: int = 720,
        limit: int = 50,
        category: Optional[str] = None,
    ) -> list[Story]:
        """
        Search stories mentioning a person's name in title or content.

        Uses ILIKE for case-insensitive matching.
        Searches both English and Nepali names if provided.
        Also extracts last name (surname) for partial matching.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Extract search terms - include full name and last name (surname)
        search_terms = [name]

        # Extract last word as surname (common pattern for Nepali names)
        name_parts = name.strip().split()
        if len(name_parts) > 1:
            surname = name_parts[-1]
            if len(surname) > 2:  # Only add if surname is meaningful
                search_terms.append(surname)

        # Build name search conditions for all terms
        name_conditions = []
        for term in search_terms:
            name_conditions.extend([
                Story.title.ilike(f"%{term}%"),
                Story.content.ilike(f"%{term}%"),
            ])

        # Also search Nepali name if provided
        if name_ne:
            # Add full Nepali name
            name_conditions.extend([
                Story.title.ilike(f"%{name_ne}%"),
                Story.content.ilike(f"%{name_ne}%"),
            ])
            # Extract Nepali surname
            ne_parts = name_ne.strip().split()
            if len(ne_parts) > 1:
                ne_surname = ne_parts[-1]
                if len(ne_surname) > 1:
                    name_conditions.extend([
                        Story.title.ilike(f"%{ne_surname}%"),
                        Story.content.ilike(f"%{ne_surname}%"),
                    ])

        from sqlalchemy import or_

        query = select(Story).where(
            Story.created_at >= cutoff,
            or_(*name_conditions),
            Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"]),
        )

        if category and category != "all":
            query = query.where(Story.category == category)

        query = query.order_by(Story.published_at.desc().nullslast()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())
