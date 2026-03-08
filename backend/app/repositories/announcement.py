"""Government announcement repository for database operations."""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.announcement import GovtAnnouncement
from app.utils.nepali_date import bs_to_ad


class AnnouncementRepository:
    """Repository for GovtAnnouncement database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, announcement_id: UUID) -> Optional[GovtAnnouncement]:
        """Get announcement by ID."""
        result = await self.db.execute(
            select(GovtAnnouncement).where(GovtAnnouncement.id == announcement_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[GovtAnnouncement]:
        """Get announcement by external ID (URL hash)."""
        result = await self.db.execute(
            select(GovtAnnouncement).where(GovtAnnouncement.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def exists(self, external_id: str) -> bool:
        """Check if announcement exists by external ID."""
        result = await self.db.execute(
            select(func.count(GovtAnnouncement.id)).where(
                GovtAnnouncement.external_id == external_id
            )
        )
        return (result.scalar() or 0) > 0

    async def create(self, announcement: GovtAnnouncement) -> GovtAnnouncement:
        """Create a new announcement."""
        self.db.add(announcement)
        await self.db.commit()
        await self.db.refresh(announcement)
        return announcement

    async def update(self, announcement: GovtAnnouncement) -> GovtAnnouncement:
        """Update an existing announcement."""
        announcement.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(announcement)
        return announcement

    async def upsert(
        self,
        external_id: str,
        source: str,
        source_name: str,
        title: str,
        url: str,
        category: str,
        date_bs: Optional[str] = None,
        date_ad: Optional[datetime] = None,
        attachments: Optional[List[dict]] = None,
        content: Optional[str] = None,
    ) -> tuple[GovtAnnouncement, bool]:
        """
        Create or update announcement.
        Returns (announcement, created) tuple.
        """
        existing = await self.get_by_external_id(external_id)

        has_attachments = bool(attachments and len(attachments) > 0)

        # Calculate published_at from date_ad or date_bs
        published_at = None
        if date_ad is not None:
            published_at = date_ad if date_ad.tzinfo else date_ad.replace(tzinfo=timezone.utc)
        elif date_bs is not None:
            converted = bs_to_ad(date_bs)
            if converted:
                published_at = converted.replace(tzinfo=timezone.utc)

        if existing:
            # Update existing
            existing.title = title
            # For dates: if date_ad is provided, use it and clear date_bs (AD date sources)
            # If date_bs is provided, use it (BS date sources)
            if date_ad is not None:
                existing.date_ad = date_ad
                existing.date_bs = date_bs  # Allow clearing date_bs for AD-only sources
            elif date_bs is not None:
                existing.date_bs = date_bs
            # Always update published_at if we have a valid date
            if published_at:
                existing.published_at = published_at
            existing.attachments = attachments or existing.attachments
            existing.has_attachments = has_attachments
            if content:
                existing.content = content
                existing.content_fetched = True
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing)
            return existing, False

        # Create new
        announcement = GovtAnnouncement(
            external_id=external_id,
            source=source,
            source_name=source_name,
            title=title,
            url=url,
            category=category,
            date_bs=date_bs,
            date_ad=date_ad,
            published_at=published_at,
            attachments=attachments or [],
            has_attachments=has_attachments,
            content=content,
            content_fetched=bool(content),
            fetched_at=datetime.now(timezone.utc),
        )
        self.db.add(announcement)
        await self.db.commit()
        await self.db.refresh(announcement)
        return announcement, True

    async def list_all(
        self,
        source: Optional[str] = None,
        sources: Optional[List[str]] = None,
        category: Optional[str] = None,
        has_attachments: Optional[bool] = None,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[GovtAnnouncement]:
        """List announcements with filters.

        Args:
            source: Filter by single source domain
            sources: Filter by multiple source domains (OR condition)
            category: Filter by category
            has_attachments: Filter by attachment presence
            unread_only: Only show unread announcements
            limit: Maximum number of results
            offset: Number of results to skip
        """
        query = select(GovtAnnouncement)

        conditions = []
        if source:
            conditions.append(GovtAnnouncement.source == source)
        elif sources:
            # Filter by multiple sources (OR condition)
            conditions.append(GovtAnnouncement.source.in_(sources))
        if category:
            conditions.append(GovtAnnouncement.category == category)
        if has_attachments is not None:
            conditions.append(GovtAnnouncement.has_attachments == has_attachments)
        if unread_only:
            conditions.append(GovtAnnouncement.is_read == False)

        if conditions:
            query = query.where(and_(*conditions))

        # Order by published_at (most recent first), nulls go to bottom
        query = query.order_by(
            desc(func.coalesce(
                GovtAnnouncement.published_at,
                datetime(1970, 1, 1, tzinfo=timezone.utc)  # Sort nulls to bottom
            ))
        ).offset(offset).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        source: Optional[str] = None,
        sources: Optional[List[str]] = None,
        category: Optional[str] = None,
        unread_only: bool = False,
    ) -> int:
        """Count announcements with filters.

        Args:
            source: Filter by single source domain
            sources: Filter by multiple source domains (OR condition)
            category: Filter by category
            unread_only: Only count unread announcements
        """
        query = select(func.count(GovtAnnouncement.id))

        conditions = []
        if source:
            conditions.append(GovtAnnouncement.source == source)
        elif sources:
            # Filter by multiple sources (OR condition)
            conditions.append(GovtAnnouncement.source.in_(sources))
        if category:
            conditions.append(GovtAnnouncement.category == category)
        if unread_only:
            conditions.append(GovtAnnouncement.is_read == False)

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_latest(self, limit: int = 10, hours: Optional[int] = None) -> List[GovtAnnouncement]:
        """Get latest announcements, optionally filtered by publication date."""
        # Use published_at with fetched_at fallback for filtering and sorting
        effective_date = func.coalesce(
            GovtAnnouncement.published_at,
            GovtAnnouncement.fetched_at,
        )

        query = select(GovtAnnouncement)

        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            query = query.where(effective_date >= cutoff)

        query = query.order_by(desc(effective_date)).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_unread_count(self) -> int:
        """Get count of unread announcements."""
        result = await self.db.execute(
            select(func.count(GovtAnnouncement.id)).where(
                GovtAnnouncement.is_read == False
            )
        )
        return result.scalar() or 0

    async def get_stats(self, hours: Optional[int] = None) -> dict:
        """Get announcement statistics, optionally filtered by publication date."""
        # Use published_at with fetched_at fallback
        effective_date = func.coalesce(
            GovtAnnouncement.published_at,
            GovtAnnouncement.fetched_at,
        )
        conditions = []
        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            conditions.append(effective_date >= cutoff)

        # Total count
        total_query = select(func.count(GovtAnnouncement.id))
        if conditions:
            total_query = total_query.where(and_(*conditions))
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        # Unread count
        unread_conditions = conditions + [GovtAnnouncement.is_read == False]
        unread_query = select(func.count(GovtAnnouncement.id)).where(and_(*unread_conditions))
        unread_result = await self.db.execute(unread_query)
        unread = unread_result.scalar() or 0

        # Count by source
        source_query = select(GovtAnnouncement.source, func.count(GovtAnnouncement.id))
        if conditions:
            source_query = source_query.where(and_(*conditions))
        source_query = source_query.group_by(GovtAnnouncement.source)
        source_result = await self.db.execute(source_query)
        by_source = {row[0]: row[1] for row in source_result.all()}

        # Count by category
        cat_query = select(GovtAnnouncement.category, func.count(GovtAnnouncement.id))
        if conditions:
            cat_query = cat_query.where(and_(*conditions))
        cat_query = cat_query.group_by(GovtAnnouncement.category)
        cat_result = await self.db.execute(cat_query)
        by_category = {row[0]: row[1] for row in cat_result.all()}

        return {
            "total": total,
            "unread": unread,
            "by_source": by_source,
            "by_category": by_category,
        }

    async def mark_as_read(self, announcement_id: UUID) -> bool:
        """Mark an announcement as read."""
        announcement = await self.get_by_id(announcement_id)
        if not announcement:
            return False
        announcement.is_read = True
        await self.db.commit()
        return True

    async def mark_all_as_read(self, source: Optional[str] = None) -> int:
        """Mark all announcements as read. Returns count updated."""
        query = select(GovtAnnouncement).where(GovtAnnouncement.is_read == False)
        if source:
            query = query.where(GovtAnnouncement.source == source)

        result = await self.db.execute(query)
        announcements = result.scalars().all()

        count = 0
        for a in announcements:
            a.is_read = True
            count += 1

        await self.db.commit()
        return count

    async def cleanup_old(self, days: int = 90) -> int:
        """Delete announcements older than specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            select(GovtAnnouncement).where(GovtAnnouncement.fetched_at < cutoff)
        )
        announcements = result.scalars().all()

        count = len(announcements)
        for a in announcements:
            await self.db.delete(a)

        await self.db.commit()
        return count
