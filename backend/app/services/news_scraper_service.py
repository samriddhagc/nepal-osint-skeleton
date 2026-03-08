"""Unified news scraper service for all provincial and national sources.

Orchestrates scraping from:
- Ratopati (all 7 provinces)
- Ekantipur (all 7 provinces + national)
- Himalayan Times (national)
- My Republica (national)
- Nepali Times (national)
- Kantipur TV (national)
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.services.ingestion_service import IngestionService
from app.ingestion.rss_fetcher import FetchedArticle

# Import all scrapers
from app.ingestion.ratopati_scraper import (
    fetch_ratopati_province,
    fetch_all_ratopati_provinces,
    RATOPATI_PROVINCES,
)
from app.ingestion.ekantipur_scraper import (
    fetch_ekantipur_province,
    fetch_all_ekantipur_provinces,
    fetch_ekantipur_national,
    EKANTIPUR_PROVINCES,
)
from app.ingestion.himalayan_scraper import (
    fetch_himalayan_news,
    fetch_all_himalayan_categories,
)
from app.ingestion.republica_scraper import (
    fetch_republica_news,
    fetch_all_republica_categories,
)
from app.ingestion.nepalitimes_scraper import (
    fetch_nepalitimes,
    fetch_nepalitimes_all_categories,
)
from app.ingestion.kantipurtv_scraper import (
    fetch_kantipurtv,
    fetch_kantipurtv_all_sections,
)

logger = logging.getLogger(__name__)


class NewsScraperService:
    """
    Unified service for scraping news from all sources.

    Handles:
    - Scraping from multiple news sites
    - Converting articles to stories
    - Deduplication via ingestion service
    - Province/district tagging
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ingestion = IngestionService(db)

    async def _safe_rollback(self) -> None:
        try:
            await self.db.rollback()
        except Exception:
            # Best-effort: rollback itself can fail if the connection is already broken.
            pass

    async def _process_articles(
        self,
        articles: List[Dict[str, Any]],
        source_type: str,
    ) -> Dict[str, int]:
        """Process scraped articles through the ingestion pipeline."""
        stats = {"scraped": len(articles), "new": 0, "duplicates": 0, "international": 0, "failed": 0}

        for article in articles:
            try:
                fetched = FetchedArticle(
                    source_id=article.get("source_id", source_type),
                    source_name=article.get("source_name", source_type),
                    url=article.get("url", ""),
                    title=article.get("title", ""),
                    summary=article.get("summary"),
                    published_at=article.get("published_at"),
                    language=article.get("language", "ne"),
                )
                outcome = await self.ingestion._process_article(fetched)
                stats[outcome] += 1
            except Exception as e:
                logger.warning(f"Failed to process article: {e}")
                # If the DB session is in an error state, later inserts/commits will fail
                # until we rollback. This can happen after disconnects or failed commits.
                if isinstance(e, SQLAlchemyError) or "rollback" in str(e).lower():
                    await self._safe_rollback()
                stats["failed"] += 1

        return stats

    async def scrape_ratopati_all(
        self,
        max_articles_per_province: int = 30,
    ) -> Dict[str, Any]:
        """Scrape all Ratopati provincial sites."""
        logger.info("Scraping all Ratopati provincial sites...")

        try:
            results = await fetch_all_ratopati_provinces(max_articles_per_province)

            total_stats = {"scraped": 0, "new": 0, "duplicates": 0, "international": 0, "failed": 0}
            province_stats = {}

            for province_key, articles in results.items():
                stats = await self._process_articles(articles, f"ratopati_{province_key}")
                province_stats[province_key] = stats
                for key in total_stats:
                    total_stats[key] += stats[key]

            await self.db.commit()
            logger.info(f"Ratopati scrape complete: {total_stats['new']} new stories")

            return {
                "source": "ratopati",
                "total": total_stats,
                "by_province": province_stats,
            }
        except Exception as e:
            await self._safe_rollback()
            logger.exception(f"Error scraping Ratopati: {e}")
            return {"source": "ratopati", "error": str(e)}

    async def scrape_ekantipur_all(
        self,
        max_articles_per_province: int = 30,
        include_national: bool = True,
    ) -> Dict[str, Any]:
        """Scrape all Ekantipur provincial sites and optionally national."""
        logger.info("Scraping all Ekantipur sites...")

        try:
            total_stats = {"scraped": 0, "new": 0, "duplicates": 0, "international": 0, "failed": 0}
            province_stats = {}

            # Scrape provincial pages
            results = await fetch_all_ekantipur_provinces(max_articles_per_province)
            for province_key, articles in results.items():
                stats = await self._process_articles(articles, f"ekantipur_{province_key}")
                province_stats[province_key] = stats
                for key in total_stats:
                    total_stats[key] += stats[key]

            # Scrape national if requested
            if include_national:
                national_articles = await fetch_ekantipur_national(max_articles_per_province)
                national_stats = await self._process_articles(national_articles, "ekantipur")
                province_stats["national"] = national_stats
                for key in total_stats:
                    total_stats[key] += national_stats[key]

            await self.db.commit()
            logger.info(f"Ekantipur scrape complete: {total_stats['new']} new stories")

            return {
                "source": "ekantipur",
                "total": total_stats,
                "by_province": province_stats,
            }
        except Exception as e:
            await self._safe_rollback()
            logger.exception(f"Error scraping Ekantipur: {e}")
            return {"source": "ekantipur", "error": str(e)}

    async def scrape_himalayan(
        self,
        max_articles: int = 50,
    ) -> Dict[str, Any]:
        """Scrape Himalayan Times."""
        logger.info("Scraping Himalayan Times...")

        try:
            results = await fetch_all_himalayan_categories(max_articles)

            total_stats = {"scraped": 0, "new": 0, "duplicates": 0, "international": 0, "failed": 0}

            for category, articles in results.items():
                stats = await self._process_articles(articles, "himalayan")
                for key in total_stats:
                    total_stats[key] += stats[key]

            await self.db.commit()
            logger.info(f"Himalayan Times scrape complete: {total_stats['new']} new stories")

            return {
                "source": "himalayan",
                "total": total_stats,
            }
        except Exception as e:
            await self._safe_rollback()
            logger.exception(f"Error scraping Himalayan Times: {e}")
            return {"source": "himalayan", "error": str(e)}

    async def scrape_republica(
        self,
        max_articles: int = 50,
    ) -> Dict[str, Any]:
        """Scrape My Republica."""
        logger.info("Scraping My Republica...")

        try:
            results = await fetch_all_republica_categories(max_articles)

            total_stats = {"scraped": 0, "new": 0, "duplicates": 0, "international": 0, "failed": 0}

            for category, articles in results.items():
                stats = await self._process_articles(articles, "republica")
                for key in total_stats:
                    total_stats[key] += stats[key]

            await self.db.commit()
            logger.info(f"My Republica scrape complete: {total_stats['new']} new stories")

            return {
                "source": "republica",
                "total": total_stats,
            }
        except Exception as e:
            await self._safe_rollback()
            logger.exception(f"Error scraping My Republica: {e}")
            return {"source": "republica", "error": str(e)}

    async def scrape_nepalitimes(
        self,
        max_articles: int = 50,
    ) -> Dict[str, Any]:
        """Scrape Nepali Times."""
        logger.info("Scraping Nepali Times...")

        try:
            results = await fetch_nepalitimes_all_categories(max_articles)

            total_stats = {"scraped": 0, "new": 0, "duplicates": 0, "international": 0, "failed": 0}

            for category, articles in results.items():
                stats = await self._process_articles(articles, "nepalitimes")
                for key in total_stats:
                    total_stats[key] += stats[key]

            await self.db.commit()
            logger.info(f"Nepali Times scrape complete: {total_stats['new']} new stories")

            return {
                "source": "nepalitimes",
                "total": total_stats,
            }
        except Exception as e:
            await self._safe_rollback()
            logger.exception(f"Error scraping Nepali Times: {e}")
            return {"source": "nepalitimes", "error": str(e)}

    async def scrape_kantipurtv(
        self,
        max_articles: int = 50,
    ) -> Dict[str, Any]:
        """Scrape Kantipur TV."""
        logger.info("Scraping Kantipur TV...")

        try:
            results = await fetch_kantipurtv_all_sections(max_articles)

            total_stats = {"scraped": 0, "new": 0, "duplicates": 0, "international": 0, "failed": 0}

            for section, articles in results.items():
                stats = await self._process_articles(articles, "kantipurtv")
                for key in total_stats:
                    total_stats[key] += stats[key]

            await self.db.commit()
            logger.info(f"Kantipur TV scrape complete: {total_stats['new']} new stories")

            return {
                "source": "kantipurtv",
                "total": total_stats,
            }
        except Exception as e:
            await self._safe_rollback()
            logger.exception(f"Error scraping Kantipur TV: {e}")
            return {"source": "kantipurtv", "error": str(e)}

    async def scrape_all_sources(
        self,
        max_articles_per_source: int = 30,
    ) -> Dict[str, Any]:
        """
        Scrape all news sources.

        This is the main entry point for comprehensive news scraping.
        """
        logger.info("Starting comprehensive news scraping...")
        start_time = datetime.now(timezone.utc)

        results = {
            "timestamp": start_time.isoformat(),
            "sources": {},
            "totals": {"scraped": 0, "new": 0, "duplicates": 0, "failed": 0},
        }

        # Scrape all sources
        scrapers = [
            ("ratopati", self.scrape_ratopati_all(max_articles_per_source)),
            ("ekantipur", self.scrape_ekantipur_all(max_articles_per_source)),
            ("himalayan", self.scrape_himalayan(max_articles_per_source)),
            ("republica", self.scrape_republica(max_articles_per_source)),
            ("nepalitimes", self.scrape_nepalitimes(max_articles_per_source)),
            ("kantipurtv", self.scrape_kantipurtv(max_articles_per_source)),
        ]

        for source_name, scraper_coro in scrapers:
            try:
                result = await scraper_coro
                results["sources"][source_name] = result

                if "total" in result:
                    for key in ["scraped", "new", "duplicates", "failed"]:
                        results["totals"][key] += result["total"].get(key, 0)
            except Exception as e:
                logger.exception(f"Error scraping {source_name}: {e}")
                results["sources"][source_name] = {"error": str(e)}

        # Broadcast new stories
        await self.ingestion._broadcast_new_stories()

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        results["elapsed_seconds"] = round(elapsed, 1)

        logger.info(
            f"Comprehensive scrape complete: {results['totals']['new']} new stories "
            f"from {len(scrapers)} sources in {elapsed:.1f}s"
        )

        return results

    async def scrape_provincial_sources(
        self,
        province: Optional[str] = None,
        max_articles: int = 30,
    ) -> Dict[str, Any]:
        """
        Scrape provincial sources only.

        Args:
            province: Optional province key (e.g., 'gandaki'). If None, scrapes all.
            max_articles: Max articles per source.
        """
        logger.info(f"Scraping provincial sources: {province or 'all'}...")

        results = {
            "province": province or "all",
            "sources": {},
            "totals": {"scraped": 0, "new": 0, "duplicates": 0, "failed": 0},
        }

        if province:
            # Scrape specific province from both Ratopati and Ekantipur
            ratopati_articles = await fetch_ratopati_province(province, max_articles)
            ratopati_stats = await self._process_articles(ratopati_articles, f"ratopati_{province}")
            results["sources"]["ratopati"] = ratopati_stats

            ekantipur_articles = await fetch_ekantipur_province(province, max_articles)
            ekantipur_stats = await self._process_articles(ekantipur_articles, f"ekantipur_{province}")
            results["sources"]["ekantipur"] = ekantipur_stats

            for key in results["totals"]:
                results["totals"][key] += ratopati_stats.get(key, 0) + ekantipur_stats.get(key, 0)
        else:
            # Scrape all provinces from both sources
            ratopati_result = await self.scrape_ratopati_all(max_articles)
            results["sources"]["ratopati"] = ratopati_result

            ekantipur_result = await self.scrape_ekantipur_all(max_articles, include_national=False)
            results["sources"]["ekantipur"] = ekantipur_result

            for source_result in [ratopati_result, ekantipur_result]:
                if "total" in source_result:
                    for key in results["totals"]:
                        results["totals"][key] += source_result["total"].get(key, 0)

        await self.db.commit()
        await self.ingestion._broadcast_new_stories()

        return results
