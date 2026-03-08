"""Ingestion service for processing RSS articles into stories."""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import yaml
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.ingestion.rss_fetcher import RSSFetcher, FetchedArticle, FetchResult
from app.ingestion.deduplicator import Deduplicator, normalize_url, generate_external_id
from app.ingestion.realtime_dedup import get_realtime_deduplicator, compute_similarity
from app.models.story import Story
from app.repositories.story import StoryRepository
from app.services.severity_service import SeverityService
from app.core.realtime_bus import publish_news

logger = logging.getLogger(__name__)
settings = get_settings()


class IngestionService:
    """
    Service for ingesting RSS feeds into the database.

    Handles:
    - Loading source configuration
    - Fetching RSS feeds
    - Deduplication
    - Category and severity classification
    - Database storage
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StoryRepository(db)
        self.severity = SeverityService()
        self.deduplicator = Deduplicator()
        self.realtime_dedup = get_realtime_deduplicator()
        self._sources: Optional[list[dict]] = None
        self._new_story_payloads: list[dict] = []

    def _load_sources(self) -> list[dict]:
        """Load RSS sources from config file."""
        if self._sources is not None:
            return self._sources

        try:
            with open(settings.sources_config_path) as f:
                config = yaml.safe_load(f)
                self._sources = config.get("sources", [])
        except FileNotFoundError:
            logger.error(f"Sources config not found: {settings.sources_config_path}")
            self._sources = []

        return self._sources

    def get_sources(self, priority_max: int = 10, active_only: bool = True) -> list[dict]:
        """Get filtered list of sources for RSS fetching."""
        sources = self._load_sources()

        filtered = []
        for s in sources:
            if active_only and not s.get("is_active", True):
                continue
            if s.get("priority", 5) > priority_max:
                continue
            if s.get("scrape_method"):
                continue
            filtered.append(s)

        return filtered

    def get_priority_sources(self) -> list[dict]:
        """Get high-priority sources (priority 1-2)."""
        return self.get_sources(priority_max=2)

    async def ingest_all(
        self,
        priority_only: bool = False,
        max_sources: Optional[int] = None,
    ) -> dict:
        """Fetch and ingest all RSS sources."""
        if priority_only:
            sources = self.get_priority_sources()
        else:
            sources = self.get_sources()

        if max_sources:
            sources = sources[:max_sources]

        if not sources:
            return {"sources": 0, "fetched": 0, "new": 0, "duplicates": 0}

        logger.info(f"Fetching {len(sources)} RSS sources...")

        async with RSSFetcher(
            max_concurrent=settings.rss_max_concurrent,
            timeout=settings.rss_timeout,
        ) as fetcher:
            results = await fetcher.fetch_many(sources)

        stats = {
            "sources": len(sources),
            "sources_success": 0,
            "sources_failed": 0,
            "fetched": 0,
            "new": 0,
            "duplicates": 0,
            "international": 0,
            "failed": 0,
            "errors": [],
        }

        for result in results:
            if result.success:
                stats["sources_success"] += 1
                stats["fetched"] += len(result.articles)
                for article in result.articles:
                    outcome = await self._process_article(article)
                    stats[outcome] += 1
            else:
                stats["sources_failed"] += 1
                stats["errors"].append({
                    "source": result.source_id,
                    "error": result.error,
                })
                logger.warning(f"Failed to fetch {result.source_id}: {result.error}")

        try:
            await self.db.commit()
        except Exception:
            try:
                await self.db.rollback()
            except Exception:
                pass
            raise
        await self._broadcast_new_stories()

        logger.info(
            f"Ingestion complete: {stats['new']} new, "
            f"{stats['duplicates']} duplicates, "
            f"{stats['international']} filtered"
        )

        return stats

    async def _broadcast_new_stories(self):
        """Broadcast all new stories to WebSocket clients."""
        if not self._new_story_payloads:
            return

        for payload in self._new_story_payloads:
            try:
                await publish_news(
                    {
                        "type": "new_story",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": payload,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast story: {e}")

        self._new_story_payloads = []

    async def _process_article(self, article: FetchedArticle) -> str:
        """Process a single article. Returns outcome string."""
        # Check in-memory dedup first
        if not self.deduplicator.check_and_mark(article.external_id):
            return "duplicates"

        # Check database dedup
        if await self.repo.exists_by_external_id(article.external_id):
            return "duplicates"

        if await self.repo.exists_by_url(article.url):
            return "duplicates"

        # Real-time title similarity check
        similar_match = self.realtime_dedup.find_match(
            title=article.title,
            timestamp=article.published_at,
        )
        matched_cluster_id = None
        matched_title = None
        if similar_match:
            matched_title, matched_cluster_id, similarity_score = similar_match
            logger.debug(
                f"Real-time match ({similarity_score:.0%}): '{article.title[:40]}' "
                f"-> '{matched_title[:40]}'"
            )

        # Classify severity (rule-based)
        severity_result = self.severity.grade(
            title=article.title,
            content=article.summary,
            nepal_relevance="RELEVANT",
            relevance_score=0.5,
        )

        final_category = None
        final_severity = severity_result.level.value

        story = Story(
            external_id=article.external_id,
            source_id=article.source_id,
            source_name=article.source_name,
            title=article.title,
            url=article.url,
            summary=article.summary,
            language=article.language,
            author=article.author,
            categories=article.categories,
            published_at=article.published_at,
            scraped_at=datetime.now(timezone.utc),
            nepal_relevance="RELEVANT",
            relevance_score=0.5,
            relevance_triggers=[],
            category=final_category,
            severity=final_severity,
            cluster_id=matched_cluster_id,
        )

        try:
            async with self.db.begin_nested():
                self.db.add(story)
                await self.db.flush()

            self._new_story_payloads.append(
                {
                    "id": str(story.id),
                    "title": story.title,
                    "url": story.url,
                    "summary": story.summary,
                    "source_id": story.source_id,
                    "source_name": story.source_name,
                    "category": story.category,
                    "severity": story.severity,
                    "nepal_relevance": story.nepal_relevance,
                    "published_at": story.published_at.isoformat() if story.published_at else None,
                    "created_at": story.created_at.isoformat() if story.created_at else None,
                    "cluster_id": str(story.cluster_id) if story.cluster_id else None,
                }
            )

            final_cluster_id = matched_cluster_id or (str(story.cluster_id) if story.cluster_id else None)
            self.realtime_dedup.add_to_cache(
                title=story.title,
                cluster_id=final_cluster_id,
                timestamp=story.published_at or datetime.now(timezone.utc),
            )

            return "new"
        except IntegrityError:
            logger.debug(f"Duplicate story skipped: {article.url[:50]}")
            return "duplicates"
        except Exception as e:
            logger.exception(f"Failed to insert story: {e}")
            return "failed"

    async def ingest_single_source(self, source_id: str) -> dict:
        """Fetch and ingest a single source by ID."""
        sources = self._load_sources()
        source = next((s for s in sources if s["id"] == source_id), None)

        if not source:
            return {"error": f"Source not found: {source_id}"}

        async with RSSFetcher() as fetcher:
            result = await fetcher.fetch_source(
                source_id=source["id"],
                source_name=source["name"],
                url=source["url"],
                language=source.get("language", "en"),
            )

        if not result.success:
            return {"error": result.error, "source": source_id}

        stats = {"fetched": len(result.articles), "new": 0, "duplicates": 0, "international": 0, "failed": 0}

        for article in result.articles:
            outcome = await self._process_article(article)
            stats[outcome] += 1

        try:
            await self.db.commit()
        except Exception:
            try:
                await self.db.rollback()
            except Exception:
                pass
            raise
        await self._broadcast_new_stories()

        return stats
