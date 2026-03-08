#!/usr/bin/env python3
"""
Ratopati Regional News Scraper

Scrapes news from Ratopati's regional/provincial pages since RSS feeds
require special access. Focuses on Gandaki province but supports all provinces.
"""

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class RatopatiArticle:
    """Structured data for a Ratopati news article."""
    id: str
    title: str
    url: str
    province: str
    source_id: str
    source_name: str
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    summary: Optional[str] = None
    language: str = "ne"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        """Generate ID if not set."""
        if not self.id:
            # Use story number from URL if available
            story_match = re.search(r'/story/(\d+)', self.url)
            if story_match:
                self.id = f"ratopati_{story_match.group(1)}"
            else:
                self.id = f"ratopati_{hashlib.md5(self.url.encode()).hexdigest()[:12]}"


# Regional Ratopati sites
RATOPATI_PROVINCES = {
    'gandaki': {
        'name': 'Ratopati Gandaki',
        'base_url': 'https://gandaki.ratopati.com',
        'pages': ['/province/4', '/'],
        'province_name': 'Gandaki Province',
        'source_id': 'gandaki_ratopati',
    },
    'koshi': {
        'name': 'Ratopati Koshi',
        'base_url': 'https://koshi.ratopati.com',
        'pages': ['/province/1', '/'],
        'province_name': 'Koshi Province',
        'source_id': 'koshi_ratopati',
    },
    'madhesh': {
        'name': 'Ratopati Madhesh',
        'base_url': 'https://madhesh.ratopati.com',
        'pages': ['/province/2', '/'],
        'province_name': 'Madhesh Province',
        'source_id': 'madhesh_ratopati',
    },
    'bagmati': {
        'name': 'Ratopati Bagmati',
        'base_url': 'https://bagmati.ratopati.com',
        'pages': ['/province/3', '/'],
        'province_name': 'Bagmati Province',
        'source_id': 'bagmati_ratopati',
    },
    'lumbini': {
        'name': 'Ratopati Lumbini',
        'base_url': 'https://lumbini.ratopati.com',
        'pages': ['/province/5', '/'],
        'province_name': 'Lumbini Province',
        'source_id': 'lumbini_ratopati',
    },
    'karnali': {
        'name': 'Ratopati Karnali',
        'base_url': 'https://karnali.ratopati.com',
        'pages': ['/province/6', '/'],
        'province_name': 'Karnali Province',
        'source_id': 'karnali_ratopati',
    },
    'sudurpashchim': {
        'name': 'Ratopati Sudurpashchim',
        'base_url': 'https://sudurpashchim.ratopati.com',
        'pages': ['/province/7', '/'],
        'province_name': 'Sudurpashchim Province',
        'source_id': 'sudurpashchim_ratopati',
    },
}


class RatopatiScraper:
    """
    Async scraper for Ratopati regional news pages.

    Since Ratopati's RSS feeds require special access, this scrapes
    the HTML pages directly.
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        timeout: int = 30,
        delay: float = 0.5,
    ):
        self.max_concurrent = max_concurrent
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.delay = delay
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def __aenter__(self) -> "RatopatiScraper":
        """Create session on context entry."""
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent * 2,
            limit_per_host=3,
            ttl_dns_cache=300,
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,ne;q=0.8",
                "Accept-Encoding": "gzip, deflate",  # Avoid brotli (br) which requires Brotli library
                "Connection": "keep-alive",
            },
        )
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self

    async def __aexit__(self, *args) -> None:
        """Close session on context exit."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page and return HTML content."""
        async with self._semaphore:
            await asyncio.sleep(self.delay)
            try:
                async with self._session.get(url) as response:
                    if response.status != 200:
                        logger.warning(f"HTTP {response.status} for {url}")
                        return None
                    return await response.text()
            except asyncio.TimeoutError:
                logger.error(f"Timeout fetching {url}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                return None

    def _parse_articles(
        self,
        html: str,
        province_key: str,
        province_info: dict,
    ) -> List[RatopatiArticle]:
        """Parse articles from HTML content."""
        soup = BeautifulSoup(html, 'lxml')
        articles = []
        seen_urls = set()

        # Find all story links
        for link in soup.find_all('a', href=re.compile(r'/story/\d+')):
            url = link.get('href', '')
            if not url:
                continue

            # Normalize URL
            if not url.startswith('http'):
                url = f"https://www.ratopati.com{url}"

            # Skip duplicates
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Extract title
            title = None

            # Try to find title in h3.news-title
            title_el = link.find('h3', class_='news-title')
            if title_el:
                title = title_el.get_text(strip=True)

            # Or try any heading
            if not title:
                title_el = link.find(['h1', 'h2', 'h3', 'h4', 'h5'])
                if title_el:
                    title = title_el.get_text(strip=True)

            # Or use link text directly
            if not title:
                title = link.get_text(strip=True)

            # Skip if no valid title
            if not title or len(title) < 10:
                continue

            # Clean title
            title = re.sub(r'\s+', ' ', title).strip()

            # Extract image if available
            image_url = None
            img = link.find('img')
            if img:
                image_url = img.get('src') or img.get('data-src')

            # Create article
            article = RatopatiArticle(
                id="",  # Will be generated in __post_init__
                title=title,
                url=url,
                province=province_info['province_name'],
                source_id=province_info['source_id'],
                source_name=province_info['name'],
                image_url=image_url,
                language='ne' if self._has_nepali_chars(title) else 'en',
            )
            articles.append(article)

        logger.info(f"Parsed {len(articles)} articles from {province_key}")
        return articles

    def _has_nepali_chars(self, text: str) -> bool:
        """Check if text contains Nepali (Devanagari) characters."""
        for char in text:
            if '\u0900' <= char <= '\u097F':
                return True
        return False

    async def scrape_province(
        self,
        province_key: str,
        max_articles: int = 50,
    ) -> List[RatopatiArticle]:
        """
        Scrape news from a specific province's Ratopati site.

        Args:
            province_key: Province identifier (e.g., 'gandaki', 'koshi')
            max_articles: Maximum articles to return

        Returns:
            List of RatopatiArticle objects
        """
        if province_key not in RATOPATI_PROVINCES:
            raise ValueError(f"Unknown province: {province_key}. Valid: {list(RATOPATI_PROVINCES.keys())}")

        province_info = RATOPATI_PROVINCES[province_key]
        all_articles = []

        for page_path in province_info['pages']:
            url = f"{province_info['base_url']}{page_path}"
            logger.info(f"Scraping {url}")

            html = await self._fetch_page(url)
            if not html:
                continue

            articles = self._parse_articles(html, province_key, province_info)
            all_articles.extend(articles)

            if len(all_articles) >= max_articles:
                break

        # Deduplicate by URL
        seen_urls = set()
        unique_articles = []
        for article in all_articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)

        logger.info(f"Total unique articles from {province_key}: {len(unique_articles)}")
        return unique_articles[:max_articles]

    async def scrape_all_provinces(
        self,
        max_articles_per_province: int = 30,
    ) -> Dict[str, List[RatopatiArticle]]:
        """
        Scrape from all provincial Ratopati sites.

        Args:
            max_articles_per_province: Max articles per province

        Returns:
            Dict mapping province key to list of articles
        """
        results = {}

        for province_key in RATOPATI_PROVINCES:
            try:
                articles = await self.scrape_province(province_key, max_articles_per_province)
                results[province_key] = articles
            except Exception as e:
                logger.error(f"Error scraping {province_key}: {e}")
                results[province_key] = []

        return results


# ============ Async functions for FastAPI integration ============

async def fetch_ratopati_province(
    province_key: str = 'gandaki',
    max_articles: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch articles from a specific Ratopati provincial site.

    For use in FastAPI endpoints and scheduled tasks.
    """
    async with RatopatiScraper() as scraper:
        articles = await scraper.scrape_province(province_key, max_articles)
        return [asdict(a) for a in articles]


async def fetch_all_ratopati_provinces(
    max_articles_per_province: int = 30,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch articles from all Ratopati provincial sites.
    """
    async with RatopatiScraper() as scraper:
        results = await scraper.scrape_all_provinces(max_articles_per_province)
        return {
            prov: [asdict(a) for a in articles]
            for prov, articles in results.items()
        }


async def fetch_gandaki_news(max_articles: int = 50) -> List[Dict[str, Any]]:
    """
    Convenience function to fetch Gandaki province news.
    """
    return await fetch_ratopati_province('gandaki', max_articles)


# ============ CLI for testing ============

async def main():
    print("=" * 60)
    print("Ratopati Regional News Scraper")
    print("=" * 60)
    print("\nAvailable provinces:")
    for key, info in RATOPATI_PROVINCES.items():
        print(f"  - {key}: {info['name']} ({info['province_name']})")
    print()

    print("[1] Scraping Gandaki province news...")
    articles = await fetch_gandaki_news(max_articles=20)

    print(f"\nFound {len(articles)} articles:")
    print("-" * 60)

    for i, article in enumerate(articles[:10], 1):
        title = article['title'][:60] + "..." if len(article['title']) > 60 else article['title']
        print(f"[{i}] {title}")
        print(f"    Source: {article['source_name']}")
        print(f"    URL: {article['url']}")
        print()

    if len(articles) > 10:
        print(f"... and {len(articles) - 10} more")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    asyncio.run(main())
