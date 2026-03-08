"""Government announcement service for ingestion and management."""
import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.announcement import GovtAnnouncement, GOVT_SOURCES
from app.repositories.announcement import AnnouncementRepository
from app.ingestion.moha_scraper import MoHAScraper, MoHAPost
from app.ingestion.opmcm_scraper import OPMCMScraper, OPMCMPost
from app.ingestion.mofa_scraper import MoFAScraper, MoFAPost
from app.ingestion.ecn_scraper import ECNScraper, ECNPost
from app.ingestion.provincial_scraper import ProvincialScraper
from app.ingestion.dao_scraper import DAOScraper
from app.ingestion.ministry_scraper_generic import GenericMinistryScraper, MINISTRY_CONFIGS
from app.ingestion.constitutional_scraper import ConstitutionalScraper
from app.ingestion.municipality_scraper import MunicipalityScraper
from app.ingestion.security_scraper import scrape_security_async, SecurityScraper
# Connected analyst models excluded from skeleton
# KBObject, KBLink, KBEvidenceRef, etc. are analyst-only
from app.schemas.announcement import (
    AnnouncementResponse,
    AnnouncementSummary,
    IngestionStats,
)

logger = logging.getLogger(__name__)

# WebSocket manager - imported lazily to avoid circular imports
_news_manager = None


def get_news_manager():
    """Get the news WebSocket manager (lazy import)."""
    global _news_manager
    if _news_manager is None:
        try:
            from app.api.v1.websocket import news_manager
            _news_manager = news_manager
        except ImportError:
            logger.warning("WebSocket manager not available")
    return _news_manager


class AnnouncementService:
    """Service for government announcement operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AnnouncementRepository(db)

    async def ingest_moha(
        self,
        categories: List[str] = None,
        max_pages: int = 3,
        fetch_content: bool = False,
    ) -> IngestionStats:
        """
        Ingest announcements from Ministry of Home Affairs.

        Args:
            categories: List of categories to scrape (defaults to English categories)
            max_pages: Maximum pages per category
            fetch_content: Whether to fetch full content for each post

        Returns:
            IngestionStats with counts
        """
        if categories is None:
            categories = ["press-release-en", "notice-en"]

        stats = IngestionStats(
            source="moha.gov.np",
            fetched=0,
            new=0,
            updated=0,
            errors=[],
        )

        source_info = GOVT_SOURCES.get("moha.gov.np", {})
        source_name = source_info.get("name", "Ministry of Home Affairs")

        # Run scraper in executor (it's synchronous)
        import asyncio

        def _scrape():
            scraper = MoHAScraper(delay=0.5, verify_ssl=False)
            return scraper.scrape_all_categories(categories, max_pages_per_category=max_pages)

        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(None, _scrape)
        except Exception as e:
            logger.error(f"MoHA scraping failed: {e}")
            stats.errors.append(str(e))
            return stats

        new_announcements = []

        for category, posts in results.items():
            for post in posts:
                try:
                    # Generate external ID from URL
                    external_id = hashlib.md5(post.url.encode()).hexdigest()[:16]

                    # Fetch attachments if needed
                    attachments = []
                    if fetch_content:
                        # Could fetch detail page here for attachments
                        pass

                    # Upsert announcement
                    announcement, created = await self.repo.upsert(
                        external_id=external_id,
                        source="moha.gov.np",
                        source_name=source_name,
                        title=post.title,
                        url=post.url,
                        category=category,
                        date_bs=post.date_bs,
                        attachments=attachments if attachments else None,
                    )

                    stats.fetched += 1
                    if created:
                        stats.new += 1
                        new_announcements.append(announcement)
                    else:
                        stats.updated += 1

                except Exception as e:
                    logger.error(f"Error storing announcement {post.url}: {e}")
                    stats.errors.append(f"{post.url}: {e}")

        # Broadcast new announcements via WebSocket
        if new_announcements:
            await self._broadcast_new_announcements(new_announcements)

        logger.info(
            f"MoHA ingestion complete: {stats.fetched} fetched, "
            f"{stats.new} new, {stats.updated} updated"
        )

        return stats

    async def ingest_opmcm(
        self,
        categories: List[str] = None,
        max_pages: int = 3,
        fetch_content: bool = False,
    ) -> IngestionStats:
        """
        Ingest announcements from Prime Minister's Office (OPMCM).

        Args:
            categories: List of categories to scrape
            max_pages: Maximum pages per category
            fetch_content: Whether to fetch full content for each post

        Returns:
            IngestionStats with counts
        """
        if categories is None:
            categories = ["press-release", "cabinet-decision"]

        stats = IngestionStats(
            source="opmcm.gov.np",
            fetched=0,
            new=0,
            updated=0,
            errors=[],
        )

        source_info = GOVT_SOURCES.get("opmcm.gov.np", {})
        source_name = source_info.get("name", "Prime Minister's Office")

        # Run scraper in executor (it's synchronous)
        import asyncio

        def _scrape():
            scraper = OPMCMScraper(delay=0.5, verify_ssl=False)
            return scraper.scrape_all_categories(categories, max_pages_per_category=max_pages)

        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(None, _scrape)
        except Exception as e:
            logger.error(f"OPMCM scraping failed: {e}")
            stats.errors.append(str(e))
            return stats

        new_announcements = []

        for category, posts in results.items():
            for post in posts:
                try:
                    # Generate external ID from URL
                    external_id = hashlib.md5(post.url.encode()).hexdigest()[:16]

                    # Upsert announcement
                    announcement, created = await self.repo.upsert(
                        external_id=external_id,
                        source="opmcm.gov.np",
                        source_name=source_name,
                        title=post.title,
                        url=post.url,
                        category=category,
                        date_bs=post.date_bs,
                        attachments=None,
                    )

                    stats.fetched += 1
                    if created:
                        stats.new += 1
                        new_announcements.append(announcement)
                    else:
                        stats.updated += 1

                except Exception as e:
                    logger.error(f"Error storing announcement {post.url}: {e}")
                    stats.errors.append(f"{post.url}: {e}")

        # Broadcast new announcements via WebSocket
        if new_announcements:
            await self._broadcast_new_announcements(new_announcements)

        logger.info(
            f"OPMCM ingestion complete: {stats.fetched} fetched, "
            f"{stats.new} new, {stats.updated} updated"
        )

        return stats

    async def ingest_mofa(
        self,
        categories: List[str] = None,
        max_pages: int = 3,
        fetch_content: bool = False,
    ) -> IngestionStats:
        """
        Ingest announcements from Ministry of Foreign Affairs (MoFA).

        Args:
            categories: List of categories to scrape
            max_pages: Maximum pages per category
            fetch_content: Whether to fetch full content for each post

        Returns:
            IngestionStats with counts
        """
        if categories is None:
            categories = ["press-release"]

        stats = IngestionStats(
            source="mofa.gov.np",
            fetched=0,
            new=0,
            updated=0,
            errors=[],
        )

        source_info = GOVT_SOURCES.get("mofa.gov.np", {})
        source_name = source_info.get("name", "Ministry of Foreign Affairs")

        # Run scraper in executor (it's synchronous)
        import asyncio

        def _scrape():
            scraper = MoFAScraper(delay=0.5, verify_ssl=False)
            return scraper.scrape_all_categories(categories, max_pages_per_category=max_pages)

        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(None, _scrape)
        except Exception as e:
            logger.error(f"MoFA scraping failed: {e}")
            stats.errors.append(str(e))
            return stats

        new_announcements = []

        for category, posts in results.items():
            for post in posts:
                try:
                    # Generate external ID from URL
                    external_id = hashlib.md5(post.url.encode()).hexdigest()[:16]

                    # Upsert announcement
                    announcement, created = await self.repo.upsert(
                        external_id=external_id,
                        source="mofa.gov.np",
                        source_name=source_name,
                        title=post.title,
                        url=post.url,
                        category=category,
                        date_bs=post.date_bs,
                        date_ad=post.date_ad,
                        attachments=None,
                    )

                    stats.fetched += 1
                    if created:
                        stats.new += 1
                        new_announcements.append(announcement)
                    else:
                        stats.updated += 1

                except Exception as e:
                    logger.error(f"Error storing announcement {post.url}: {e}")
                    stats.errors.append(f"{post.url}: {e}")

        # Broadcast new announcements via WebSocket
        if new_announcements:
            await self._broadcast_new_announcements(new_announcements)

        logger.info(
            f"MoFA ingestion complete: {stats.fetched} fetched, "
            f"{stats.new} new, {stats.updated} updated"
        )

        return stats

    async def ingest_ecn(
        self,
        categories: List[str] = None,
        max_pages: int = 3,
        fetch_content: bool = False,
    ) -> IngestionStats:
        """
        Ingest announcements from Election Commission Nepal (ECN).
        Uses Playwright for JavaScript-rendered content.

        Args:
            categories: List of categories to scrape
            max_pages: Maximum pages per category
            fetch_content: Whether to fetch full content for each post

        Returns:
            IngestionStats with counts
        """
        if categories is None:
            categories = ["press-release"]

        stats = IngestionStats(
            source="election.gov.np",
            fetched=0,
            new=0,
            updated=0,
            errors=[],
        )

        source_info = GOVT_SOURCES.get("election.gov.np", {})
        source_name = source_info.get("name", "Election Commission Nepal")

        try:
            # ECN scraper is async and uses Playwright
            async with ECNScraper(headless=True) as scraper:
                results = await scraper.scrape_all_categories(
                    categories, max_pages_per_category=max_pages
                )
        except Exception as e:
            logger.error(f"ECN scraping failed: {e}")
            stats.errors.append(str(e))
            return stats

        new_announcements = []

        for category, posts in results.items():
            for post in posts:
                try:
                    # Generate external ID from URL
                    external_id = hashlib.md5(post.url.encode()).hexdigest()[:16]

                    # Upsert announcement
                    announcement, created = await self.repo.upsert(
                        external_id=external_id,
                        source="election.gov.np",
                        source_name=source_name,
                        title=post.title,
                        url=post.url,
                        category=category,
                        date_bs=post.date_bs,
                        date_ad=post.date_ad,
                        attachments=None,
                    )

                    stats.fetched += 1
                    if created:
                        stats.new += 1
                        new_announcements.append(announcement)
                    else:
                        stats.updated += 1

                except Exception as e:
                    logger.error(f"Error storing announcement {post.url}: {e}")
                    stats.errors.append(f"{post.url}: {e}")

        # Broadcast new announcements via WebSocket
        if new_announcements:
            await self._broadcast_new_announcements(new_announcements)

        logger.info(
            f"ECN ingestion complete: {stats.fetched} fetched, "
            f"{stats.new} new, {stats.updated} updated"
        )

        return stats

    async def ingest_provincial(
        self,
        province: str,
        categories: List[str] = None,
        max_pages: int = 3,
        check_curfews: bool = True,
    ) -> IngestionStats:
        """
        Ingest announcements from a provincial government website.

        Args:
            province: Province key (e.g., 'koshi', 'bagmati')
            categories: List of categories to scrape
            max_pages: Maximum pages per category
            check_curfews: Whether to check for curfew keywords

        Returns:
            IngestionStats with counts
        """
        if categories is None:
            categories = ["press-release", "news"]

        stats = IngestionStats(
            source=f"{province}.gov.np",
            fetched=0,
            new=0,
            updated=0,
            errors=[],
        )

        # Run scraper in executor
        import asyncio

        def _scrape():
            scraper = ProvincialScraper(delay=0.5, verify_ssl=False)
            all_posts = []
            for category in categories:
                try:
                    posts = scraper.scrape_province(province, category, max_pages=max_pages)
                    all_posts.extend(posts)
                except Exception as e:
                    logger.error(f"Error scraping {province} {category}: {e}")
            return all_posts

        loop = asyncio.get_event_loop()
        try:
            posts = await loop.run_in_executor(None, _scrape)
        except Exception as e:
            logger.error(f"Provincial scraping failed for {province}: {e}")
            stats.errors.append(str(e))
            return stats

        new_announcements = []

        for post in posts:
            try:
                external_id = hashlib.md5(post.url.encode()).hexdigest()[:16]

                announcement, created = await self.repo.upsert(
                    external_id=external_id,
                    source=post.source,
                    source_name=post.source_name,
                    title=post.title,
                    url=post.url,
                    category=post.category,
                    date_bs=post.date_bs,
                    attachments=None,
                )

                stats.fetched += 1
                if created:
                    stats.new += 1
                    new_announcements.append(announcement)
                else:
                    stats.updated += 1

            except Exception as e:
                logger.error(f"Error storing announcement {post.url}: {e}")
                stats.errors.append(f"{post.url}: {e}")

        # Check for curfews in new announcements
        if check_curfews and new_announcements:
            await self._check_curfews(new_announcements)

        # Broadcast new announcements
        if new_announcements:
            await self._broadcast_new_announcements(new_announcements)

        logger.info(
            f"Provincial {province} ingestion complete: {stats.fetched} fetched, "
            f"{stats.new} new, {stats.updated} updated"
        )

        return stats

    async def ingest_dao(
        self,
        district: str,
        categories: List[str] = None,
        max_pages: int = 2,
        check_curfews: bool = True,
    ) -> IngestionStats:
        """
        Ingest announcements from a DAO (District Administration Office).

        Args:
            district: District key (e.g., 'kathmandu', 'lalitpur')
            categories: List of categories to scrape
            max_pages: Maximum pages per category
            check_curfews: Whether to check for curfew keywords

        Returns:
            IngestionStats with counts
        """
        if categories is None:
            categories = ["notice-en", "circular-en"]

        stats = IngestionStats(
            source=f"dao{district}.moha.gov.np",
            fetched=0,
            new=0,
            updated=0,
            errors=[],
        )

        # Run scraper in executor
        import asyncio

        def _scrape():
            scraper = DAOScraper(delay=0.5, verify_ssl=False)
            all_posts = []
            for category in categories:
                try:
                    posts = scraper.scrape_district(district, category, max_pages=max_pages)
                    all_posts.extend(posts)
                except Exception as e:
                    logger.error(f"Error scraping DAO {district} {category}: {e}")
            return all_posts

        loop = asyncio.get_event_loop()
        try:
            posts = await loop.run_in_executor(None, _scrape)
        except Exception as e:
            logger.error(f"DAO scraping failed for {district}: {e}")
            stats.errors.append(str(e))
            return stats

        new_announcements = []

        for post in posts:
            try:
                external_id = hashlib.md5(post.url.encode()).hexdigest()[:16]

                announcement, created = await self.repo.upsert(
                    external_id=external_id,
                    source=post.source,
                    source_name=post.source_name,
                    title=post.title,
                    url=post.url,
                    category=post.category,
                    date_bs=post.date_bs,
                    attachments=None,
                )

                stats.fetched += 1
                if created:
                    stats.new += 1
                    new_announcements.append(announcement)
                else:
                    stats.updated += 1

            except Exception as e:
                logger.error(f"Error storing announcement {post.url}: {e}")
                stats.errors.append(f"{post.url}: {e}")

        # Check for curfews in new announcements (important for DAO!)
        if check_curfews and new_announcements:
            await self._check_curfews(new_announcements)

        # Broadcast new announcements
        if new_announcements:
            await self._broadcast_new_announcements(new_announcements)

        logger.info(
            f"DAO {district} ingestion complete: {stats.fetched} fetched, "
            f"{stats.new} new, {stats.updated} updated"
        )

        return stats

    async def ingest_all_provincial(self, max_pages: int = 2) -> List[IngestionStats]:
        """Ingest from all 7 provincial government websites."""
        all_stats = []

        for province in ProvincialScraper.PROVINCES.keys():
            try:
                stats = await self.ingest_provincial(province, max_pages=max_pages)
                all_stats.append(stats)
            except Exception as e:
                logger.error(f"Failed to ingest provincial {province}: {e}")

        return all_stats

    async def ingest_priority_daos(self, max_pages: int = 2) -> List[IngestionStats]:
        """Ingest from priority DAO offices (major metros)."""
        all_stats = []

        for district in DAOScraper.PRIORITY_DISTRICTS:
            try:
                stats = await self.ingest_dao(district, max_pages=max_pages)
                all_stats.append(stats)
            except Exception as e:
                logger.error(f"Failed to ingest DAO {district}: {e}")

        return all_stats

    async def _check_curfews(self, announcements: List[GovtAnnouncement]) -> None:
        """Check announcements for curfew keywords and create alerts."""
        try:
            from app.services.curfew_detection_service import CurfewDetectionService

            service = CurfewDetectionService(self.db)
            alerts = await service.process_announcements(announcements)

            if alerts:
                logger.info(f"Created {len(alerts)} curfew alerts from {len(announcements)} announcements")
        except ImportError:
            logger.warning("Curfew detection service not available")
        except Exception as e:
            logger.error(f"Error checking for curfews: {e}")

    async def ingest_ministry(
        self,
        ministry_id: str,
        max_pages: int = 2,
    ) -> IngestionStats:
        """
        Ingest announcements from a generic ministry.

        Args:
            ministry_id: Ministry key from MINISTRY_CONFIGS
            max_pages: Maximum pages per endpoint

        Returns:
            IngestionStats with counts
        """
        if ministry_id not in MINISTRY_CONFIGS:
            return IngestionStats(
                source=f"{ministry_id}.gov.np",
                fetched=0,
                new=0,
                updated=0,
                errors=[f"Unknown ministry: {ministry_id}"],
            )

        config = MINISTRY_CONFIGS[ministry_id]
        stats = IngestionStats(
            source=config.base_url.replace("https://", ""),
            fetched=0,
            new=0,
            updated=0,
            errors=[],
        )

        # Run scraper in executor
        import asyncio

        def _scrape():
            scraper = GenericMinistryScraper(config, delay=0.5)
            return scraper.scrape_all(max_pages_per_endpoint=max_pages)

        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(None, _scrape)
        except Exception as e:
            logger.error(f"Ministry scraping failed for {ministry_id}: {e}")
            stats.errors.append(str(e))
            return stats

        new_announcements = []

        for endpoint, posts in results.items():
            for post in posts:
                try:
                    external_id = hashlib.md5(post.url.encode()).hexdigest()[:16]

                    announcement, created = await self.repo.upsert(
                        external_id=external_id,
                        source=config.base_url.replace("https://", ""),
                        source_name=config.name,
                        title=post.title,
                        url=post.url,
                        category=endpoint.replace("_", "-"),
                        date_bs=post.date_bs,
                        attachments=None,
                    )

                    stats.fetched += 1
                    if created:
                        stats.new += 1
                        new_announcements.append(announcement)
                    else:
                        stats.updated += 1

                except Exception as e:
                    logger.error(f"Error storing announcement {post.url}: {e}")
                    stats.errors.append(f"{post.url}: {e}")

        if new_announcements:
            await self._broadcast_new_announcements(new_announcements)

        logger.info(
            f"Ministry {ministry_id} ingestion complete: {stats.fetched} fetched, "
            f"{stats.new} new, {stats.updated} updated"
        )

        return stats

    async def ingest_all_ministries(self, max_pages: int = 2) -> List[IngestionStats]:
        """Ingest from all generic ministries in MINISTRY_CONFIGS."""
        all_stats = []

        for ministry_id in MINISTRY_CONFIGS.keys():
            try:
                stats = await self.ingest_ministry(ministry_id, max_pages=max_pages)
                all_stats.append(stats)
            except Exception as e:
                logger.error(f"Failed to ingest ministry {ministry_id}: {e}")

        return all_stats

    async def ingest_constitutional_body(
        self,
        body_id: str,
        max_pages: int = 2,
    ) -> IngestionStats:
        """
        Ingest announcements from a constitutional body.

        Args:
            body_id: Body key from ConstitutionalScraper.BODIES
            max_pages: Maximum pages per endpoint

        Returns:
            IngestionStats with counts
        """
        scraper_instance = ConstitutionalScraper(delay=0.5, verify_ssl=False)

        if body_id not in scraper_instance.BODIES:
            return IngestionStats(
                source=f"{body_id}.gov.np",
                fetched=0,
                new=0,
                updated=0,
                errors=[f"Unknown constitutional body: {body_id}"],
            )

        config = scraper_instance.BODIES[body_id]
        stats = IngestionStats(
            source=config.base_url.replace("https://", ""),
            fetched=0,
            new=0,
            updated=0,
            errors=[],
        )

        # Run scraper in executor
        import asyncio

        def _scrape():
            scraper = ConstitutionalScraper(delay=0.5, verify_ssl=False)
            return scraper.scrape_body(body_id, max_pages=max_pages)

        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(None, _scrape)
        except Exception as e:
            logger.error(f"Constitutional body scraping failed for {body_id}: {e}")
            stats.errors.append(str(e))
            return stats

        new_announcements = []

        for post in results:
            try:
                external_id = hashlib.md5(post.url.encode()).hexdigest()[:16]

                announcement, created = await self.repo.upsert(
                    external_id=external_id,
                    source=post.source_domain,
                    source_name=post.body_name,
                    title=post.title,
                    url=post.url,
                    category=post.category,
                    date_bs=post.date_bs,
                    attachments=None,
                )

                stats.fetched += 1
                if created:
                    stats.new += 1
                    new_announcements.append(announcement)
                else:
                    stats.updated += 1

            except Exception as e:
                logger.error(f"Error storing announcement {post.url}: {e}")
                stats.errors.append(f"{post.url}: {e}")

        if new_announcements:
            await self._broadcast_new_announcements(new_announcements)

        logger.info(
            f"Constitutional {body_id} ingestion complete: {stats.fetched} fetched, "
            f"{stats.new} new, {stats.updated} updated"
        )

        return stats

    async def ingest_all_constitutional_bodies(self, max_pages: int = 2) -> List[IngestionStats]:
        """Ingest from all constitutional bodies."""
        all_stats = []

        scraper_instance = ConstitutionalScraper(delay=0.5, verify_ssl=False)
        for body_id in scraper_instance.BODIES.keys():
            try:
                stats = await self.ingest_constitutional_body(body_id, max_pages=max_pages)
                all_stats.append(stats)
            except Exception as e:
                logger.error(f"Failed to ingest constitutional body {body_id}: {e}")

        return all_stats

    async def ingest_municipality(
        self,
        mun_id: str,
        max_pages: int = 2,
    ) -> IngestionStats:
        """
        Ingest announcements from a municipality.

        Args:
            mun_id: Municipality key from MunicipalityScraper.MUNICIPALITIES
            max_pages: Maximum pages per endpoint

        Returns:
            IngestionStats with counts
        """
        scraper_instance = MunicipalityScraper(delay=0.5, verify_ssl=False)

        if mun_id not in scraper_instance.MUNICIPALITIES:
            return IngestionStats(
                source=f"{mun_id}mun.gov.np",
                fetched=0,
                new=0,
                updated=0,
                errors=[f"Unknown municipality: {mun_id}"],
            )

        config = scraper_instance.MUNICIPALITIES[mun_id]
        stats = IngestionStats(
            source=config.base_url.replace("https://", ""),
            fetched=0,
            new=0,
            updated=0,
            errors=[],
        )

        # Run scraper in executor
        import asyncio

        def _scrape():
            scraper = MunicipalityScraper(delay=0.5, verify_ssl=False)
            return scraper.scrape_municipality(mun_id, max_pages=max_pages)

        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(None, _scrape)
        except Exception as e:
            logger.error(f"Municipality scraping failed for {mun_id}: {e}")
            stats.errors.append(str(e))
            return stats

        new_announcements = []

        for post in results:
            try:
                external_id = hashlib.md5(post.url.encode()).hexdigest()[:16]

                announcement, created = await self.repo.upsert(
                    external_id=external_id,
                    source=post.source_domain,
                    source_name=post.municipality_name,
                    title=post.title,
                    url=post.url,
                    category=post.category,
                    date_bs=post.date_bs,
                    attachments=None,
                )

                stats.fetched += 1
                if created:
                    stats.new += 1
                    new_announcements.append(announcement)
                else:
                    stats.updated += 1

            except Exception as e:
                logger.error(f"Error storing announcement {post.url}: {e}")
                stats.errors.append(f"{post.url}: {e}")

        if new_announcements:
            await self._broadcast_new_announcements(new_announcements)

        logger.info(
            f"Municipality {mun_id} ingestion complete: {stats.fetched} fetched, "
            f"{stats.new} new, {stats.updated} updated"
        )

        return stats

    async def ingest_all_municipalities(self, max_pages: int = 2) -> List[IngestionStats]:
        """Ingest from all municipalities."""
        all_stats = []

        scraper_instance = MunicipalityScraper(delay=0.5, verify_ssl=False)
        for mun_id in scraper_instance.MUNICIPALITIES.keys():
            try:
                stats = await self.ingest_municipality(mun_id, max_pages=max_pages)
                all_stats.append(stats)
            except Exception as e:
                logger.error(f"Failed to ingest municipality {mun_id}: {e}")

        return all_stats

    async def ingest_all_sources(self, max_pages: int = 3) -> List[IngestionStats]:
        """Ingest from all registered government sources."""
        all_stats = []

        # Key sources (MOHA, OPMCM, MOFA, ECN)
        moha_stats = await self.ingest_moha(max_pages=max_pages)
        all_stats.append(moha_stats)

        opmcm_stats = await self.ingest_opmcm(max_pages=max_pages)
        all_stats.append(opmcm_stats)

        mofa_stats = await self.ingest_mofa(max_pages=max_pages)
        all_stats.append(mofa_stats)

        ecn_stats = await self.ingest_ecn(max_pages=max_pages)
        all_stats.append(ecn_stats)

        # All generic ministries
        ministry_stats = await self.ingest_all_ministries(max_pages=max_pages)
        all_stats.extend(ministry_stats)

        # All provincial governments
        provincial_stats = await self.ingest_all_provincial(max_pages=max_pages)
        all_stats.extend(provincial_stats)

        # All constitutional bodies
        constitutional_stats = await self.ingest_all_constitutional_bodies(max_pages=max_pages)
        all_stats.extend(constitutional_stats)

        # All municipalities (metro and sub-metro)
        municipality_stats = await self.ingest_all_municipalities(max_pages=max_pages)
        all_stats.extend(municipality_stats)

        # Priority DAO offices
        dao_stats = await self.ingest_priority_daos(max_pages=max_pages)
        all_stats.extend(dao_stats)

        # Security services
        security_stats = await self.ingest_security_sources(max_pages=max_pages)
        all_stats.extend(security_stats)

        return all_stats

    async def ingest_security_sources(
        self,
        source_ids: Optional[List[str]] = None,
        max_pages: int = 2,
    ) -> List[IngestionStats]:
        """Ingest Nepal security-service websites and emit provenance-backed graph objects."""
        source_map = SecurityScraper.SECURITY_SOURCES
        selected_ids = source_ids or list(source_map.keys())
        valid_ids = [item for item in selected_ids if item in source_map]
        if not valid_ids:
            return []

        results = await scrape_security_async(source_ids=valid_ids, max_pages=max_pages)
        all_stats: List[IngestionStats] = []
        new_announcements: list[GovtAnnouncement] = []

        for source_id in valid_ids:
            config = source_map[source_id]
            source_domain = config.base_url.replace("https://", "").replace("http://", "")
            stats = IngestionStats(
                source=source_domain,
                fetched=0,
                new=0,
                updated=0,
                errors=[],
            )

            endpoint_posts = results.get(source_id) or {}
            for _, posts in endpoint_posts.items():
                for post in posts:
                    try:
                        external_id = hashlib.md5(post.url.encode()).hexdigest()[:16]
                        category = f"security:{post.category or 'notice'}"
                        announcement, created = await self.repo.upsert(
                            external_id=external_id,
                            source=source_domain,
                            source_name=post.source_name,
                            title=post.title,
                            url=post.url,
                            category=category,
                            date_bs=post.date_bs,
                            attachments=None,
                        )

                        stats.fetched += 1
                        if created:
                            stats.new += 1
                            new_announcements.append(announcement)
                            await self._emit_security_graph_evidence(
                                source_id=source_id,
                                source_name=post.source_name,
                                source_domain=source_domain,
                                announcement_id=str(announcement.id),
                                title=post.title,
                                url=post.url,
                                category=post.category or "notice",
                                alert_type=post.alert_type,
                                location_hint=self._extract_location_hint(post.title),
                            )
                        else:
                            stats.updated += 1

                    except Exception as exc:
                        logger.error("Security ingestion failed for %s: %s", source_id, exc)
                        stats.errors.append(str(exc))

            all_stats.append(stats)

        if new_announcements:
            await self._broadcast_new_announcements(new_announcements)

        await self.db.commit()
        return all_stats

    async def get_security_source_status(self) -> list[dict[str, Any]]:
        """Return configured security source metadata with existing announcement counts."""
        configured = SecurityScraper.SECURITY_SOURCES
        stats_payload = await self.repo.get_stats()
        source_counts = stats_payload.get("by_source", {}) if isinstance(stats_payload, dict) else {}
        payload: list[dict[str, Any]] = []
        for source_id, config in configured.items():
            source_domain = config.base_url.replace("https://", "").replace("http://", "")
            payload.append(
                {
                    "source_id": source_id,
                    "name": config.name,
                    "base_url": config.base_url,
                    "priority": config.priority,
                    "poll_interval_mins": config.poll_interval_mins,
                    "configured_endpoints": list(config.endpoints.keys()),
                    "stored_announcement_count": source_counts.get(source_domain, 0),
                }
            )
        return payload

    async def _emit_security_graph_evidence(
        self,
        *,
        source_id: str,
        source_name: str,
        source_domain: str,
        announcement_id: str,
        title: str,
        url: str,
        category: str,
        alert_type: str | None,
        location_hint: str | None,
    ) -> None:
        """Emit security graph evidence (stub - connected analyst excluded from skeleton)."""
        pass

    @staticmethod
    def _extract_location_hint(title: str) -> str | None:
        lowered = title.lower()
        if " in " in lowered:
            fragment = title.split(" in ", 1)[1]
            return fragment.split(",")[0].strip()[:80]
        if "मा" in title:
            parts = title.split("मा")
            if len(parts) >= 2:
                return parts[0].strip()[-80:]
        return None

    async def _broadcast_new_announcements(self, announcements: List[GovtAnnouncement]):
        """Broadcast new announcements via WebSocket."""
        manager = get_news_manager()
        if not manager:
            return

        for announcement in announcements:
            try:
                await manager.broadcast({
                    "type": "govt_announcement",
                    "data": {
                        "id": str(announcement.id),
                        "source": announcement.source,
                        "source_name": announcement.source_name,
                        "title": announcement.title,
                        "url": announcement.url,
                        "category": announcement.category,
                        "date_bs": announcement.date_bs,
                        "has_attachments": announcement.has_attachments,
                        "fetched_at": announcement.fetched_at.isoformat(),
                    },
                })
            except Exception as e:
                logger.warning(f"Failed to broadcast announcement: {e}")

    async def get_summary(self, limit: int = 5, hours: Optional[int] = None) -> AnnouncementSummary:
        """Get summary for dashboard widget."""
        stats = await self.repo.get_stats(hours=hours)
        latest = await self.repo.get_latest(limit=limit, hours=hours)

        return AnnouncementSummary(
            total=stats["total"],
            unread=stats["unread"],
            by_source=stats["by_source"],
            by_category=stats["by_category"],
            latest=[
                AnnouncementResponse(
                    id=str(a.id),
                    external_id=a.external_id,
                    source=a.source,
                    source_name=a.source_name,
                    title=a.title,
                    url=a.url,
                    category=a.category,
                    date_bs=a.date_bs,
                    date_ad=a.date_ad,
                    attachments=a.attachments or [],
                    has_attachments=a.has_attachments,
                    content=a.content,
                    is_read=a.is_read,
                    is_important=a.is_important,
                    published_at=a.published_at,
                    fetched_at=a.fetched_at,
                    created_at=a.created_at,
                )
                for a in latest
            ],
        )

    async def list_announcements(
        self,
        source: Optional[str] = None,
        province: Optional[str] = None,
        category: Optional[str] = None,
        has_attachments: Optional[bool] = None,
        unread_only: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """List announcements with pagination.

        Args:
            source: Filter by specific source domain (takes precedence over province)
            province: Filter by province name (e.g., "Koshi", "Bagmati")
            category: Filter by category
            has_attachments: Filter by attachment presence
            unread_only: Only show unread announcements
            page: Page number (1-indexed)
            per_page: Items per page
        """
        offset = (page - 1) * per_page

        # Resolve province to source domains if provided (and source not specified)
        sources = None
        if province and not source:
            from app.utils.province_mapping import get_sources_for_province
            sources = get_sources_for_province(province)
            # If province is invalid, sources will be None and we'll get no results
            # This is intentional - invalid province should return empty results

        announcements = await self.repo.list_all(
            source=source,
            sources=sources,
            category=category,
            has_attachments=has_attachments,
            unread_only=unread_only,
            limit=per_page + 1,  # Fetch one extra to check if there's more
            offset=offset,
        )

        has_more = len(announcements) > per_page
        if has_more:
            announcements = announcements[:per_page]

        total = await self.repo.count(
            source=source,
            sources=sources,
            category=category,
            unread_only=unread_only,
        )

        return {
            "announcements": [a.to_dict() for a in announcements],
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_more": has_more,
        }

    async def get_announcement(self, announcement_id: str) -> Optional[Dict[str, Any]]:
        """Get a single announcement by ID."""
        from uuid import UUID
        try:
            announcement = await self.repo.get_by_id(UUID(announcement_id))
            if announcement:
                return announcement.to_dict()
            return None
        except ValueError:
            return None

    async def mark_as_read(self, announcement_id: str) -> bool:
        """Mark announcement as read."""
        from uuid import UUID
        try:
            return await self.repo.mark_as_read(UUID(announcement_id))
        except ValueError:
            return False

    async def mark_all_as_read(self, source: Optional[str] = None) -> int:
        """Mark all announcements as read."""
        return await self.repo.mark_all_as_read(source=source)

    async def get_sources(self) -> List[Dict[str, Any]]:
        """Get list of available government sources."""
        sources = []
        for source_id, info in GOVT_SOURCES.items():
            count = await self.repo.count(source=source_id)
            sources.append({
                "source": source_id,
                "name": info["name"],
                "name_ne": info.get("name_ne"),
                "categories": info["categories"],
                "total_announcements": count,
            })
        return sources

    async def fetch_announcement_content(self, announcement_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full content and attachments for an announcement."""
        from uuid import UUID
        import asyncio

        try:
            announcement = await self.repo.get_by_id(UUID(announcement_id))
        except ValueError:
            return None

        if not announcement:
            return None

        # Skip if already fetched
        if announcement.content_fetched:
            return announcement.to_dict()

        # Fetch content based on source
        detail = None
        loop = asyncio.get_event_loop()

        if announcement.source == "moha.gov.np":
            def _fetch_moha():
                scraper = MoHAScraper(delay=0.3, verify_ssl=False)
                return scraper.get_post_detail(announcement.url)
            detail = await loop.run_in_executor(None, _fetch_moha)

        elif announcement.source == "opmcm.gov.np":
            def _fetch_opmcm():
                scraper = OPMCMScraper(delay=0.3, verify_ssl=False)
                return scraper.get_post_detail(announcement.url)
            detail = await loop.run_in_executor(None, _fetch_opmcm)

        elif announcement.source == "mofa.gov.np":
            def _fetch_mofa():
                scraper = MoFAScraper(delay=0.3, verify_ssl=False)
                return scraper.get_post_detail(announcement.url)
            detail = await loop.run_in_executor(None, _fetch_mofa)

        elif announcement.source == "election.gov.np":
            # ECN uses async Playwright scraper
            async with ECNScraper(headless=True) as scraper:
                detail = await scraper.get_post_detail(announcement.url)

        if detail:
            announcement.content = detail.get("content")
            announcement.attachments = detail.get("attachments", [])
            announcement.has_attachments = len(announcement.attachments) > 0
            announcement.content_fetched = True
            await self.db.commit()

        return announcement.to_dict()
