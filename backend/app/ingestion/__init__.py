"""
Nepal OSINT Ingestion Modules

Includes RSS fetchers, government scrapers, and data processing utilities.
"""
from app.ingestion.rss_fetcher import RSSFetcher, FetchedArticle, FetchResult
from app.ingestion.deduplicator import Deduplicator

# Government Scrapers
from app.ingestion.ministry_scraper_generic import (
    GenericMinistryScraper,
    GenericMinistryScraperConfig,
    GovtPost,
    MINISTRY_CONFIGS,
    get_ministry_scraper,
    scrape_ministry_async,
)
from app.ingestion.dao_scraper import DAOScraper, DAOPost, fetch_priority_dao_posts_async
from app.ingestion.provincial_scraper import (
    ProvincialScraper,
    ProvincialPost,
    fetch_all_provincial_posts_async,
)
from app.ingestion.constitutional_scraper import ConstitutionalScraper
from app.ingestion.municipality_scraper import MunicipalityScraper
from app.ingestion.security_scraper import SecurityScraper, SecurityPost, scrape_security_async
from app.ingestion.govt_batch_scraper import GovtBatchScraper, ScrapeResult

__all__ = [
    # RSS
    "RSSFetcher",
    "FetchedArticle",
    "FetchResult",
    "Deduplicator",
    # Ministry Scrapers
    "GenericMinistryScraper",
    "GenericMinistryScraperConfig",
    "GovtPost",
    "MINISTRY_CONFIGS",
    "get_ministry_scraper",
    "scrape_ministry_async",
    # DAO Scraper
    "DAOScraper",
    "DAOPost",
    "fetch_priority_dao_posts_async",
    # Provincial Scraper
    "ProvincialScraper",
    "ProvincialPost",
    "fetch_all_provincial_posts_async",
    # Constitutional Scraper
    "ConstitutionalScraper",
    # Municipality Scraper
    "MunicipalityScraper",
    # Security Scraper
    "SecurityScraper",
    "SecurityPost",
    "scrape_security_async",
    # Batch Scraper
    "GovtBatchScraper",
    "ScrapeResult",
]
