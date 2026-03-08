#!/usr/bin/env python3
"""
Kantipur TV News Scraper

Scrapes Nepali-language news articles from Kantipur TV website.
Extracts news from homepage sections and category pages.
"""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class KantipurTVArticle:
    """Structured data for a Kantipur TV news article."""
    id: str
    title: str
    url: str
    category: str
    source_id: str = "kantipurtv"
    source_name: str = "Kantipur TV"
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    summary: Optional[str] = None
    language: str = "ne"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        """Generate ID if not set."""
        if not self.id:
            # Try to extract article/news ID from URL
            id_match = re.search(r'/(\d+)/?$', self.url)
            if id_match:
                self.id = f"kantipurtv_{id_match.group(1)}"
            else:
                slug_match = re.search(r'/([^/]+)/?$', self.url.rstrip('/'))
                if slug_match:
                    slug = slug_match.group(1)[:30]
                    self.id = f"kantipurtv_{slug}"
                else:
                    self.id = f"kantipurtv_{hashlib.md5(self.url.encode()).hexdigest()[:12]}"


# Kantipur TV sections/categories to scrape
KANTIPURTV_SECTIONS = {
    'homepage': {
        'name': 'Homepage',
        'path': '/',
        'description': 'Main homepage news',
    },
    'news': {
        'name': 'News',
        'path': '/news',
        'description': 'General news section',
    },
    'politics': {
        'name': 'Politics',
        'path': '/politics',
        'description': 'Political news',
    },
    'entertainment': {
        'name': 'Entertainment',
        'path': '/entertainment',
        'description': 'Entertainment news',
    },
    'sports': {
        'name': 'Sports',
        'path': '/sports',
        'description': 'Sports news',
    },
}

BASE_URL = "https://www.kantipurtv.com"


class KantipurTVScraper:
    """
    Async scraper for Kantipur TV news website.

    Scrapes Nepali-language news articles from one of Nepal's
    major television news portals.
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

    async def __aenter__(self) -> "KantipurTVScraper":
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
                "Accept-Language": "ne,en-US;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
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

    def _has_nepali_chars(self, text: str) -> bool:
        """Check if text contains Nepali (Devanagari) characters."""
        for char in text:
            if '\u0900' <= char <= '\u097F':
                return True
        return False

    def _parse_articles(
        self,
        html: str,
        section_key: str,
        section_info: dict,
    ) -> List[KantipurTVArticle]:
        """Parse articles from HTML content."""
        soup = BeautifulSoup(html, 'lxml')
        articles = []
        seen_urls = set()

        # Find article containers - common patterns for news sites
        article_containers = soup.find_all(
            ['article', 'div', 'li'],
            class_=re.compile(r'news|article|post|story|item|card', re.I)
        )

        for container in article_containers:
            article = self._extract_article_from_container(container, section_info, seen_urls)
            if article:
                articles.append(article)
                seen_urls.add(article.url)

        # Also search for news links directly
        for link in soup.find_all('a', href=True):
            url = link.get('href', '')

            # Skip if already processed or not a news link
            if not url or url in seen_urls:
                continue

            # Normalize URL
            if not url.startswith('http'):
                if url.startswith('/'):
                    url = f"{BASE_URL}{url}"
                else:
                    continue

            # Skip non-news URLs
            if any(skip in url for skip in ['/tag/', '/page/', '/author/', '#', 'javascript:', '.jpg', '.png', '.mp4']):
                continue

            # Must be from kantipurtv.com
            if 'kantipurtv.com' not in url:
                continue

            seen_urls.add(url)

            # Try to get title
            title = link.get_text(strip=True)

            # Skip if title is too short or doesn't look like news
            if not title or len(title) < 10:
                continue

            # Prefer Nepali content
            if not self._has_nepali_chars(title):
                # Check if it has enough words to be a headline
                if len(title.split()) < 4:
                    continue

            title = re.sub(r'\s+', ' ', title).strip()

            # Extract image from nearby elements
            image_url = None
            parent = link.parent
            if parent:
                img = parent.find('img')
                if img:
                    image_url = img.get('src') or img.get('data-src')

            article = KantipurTVArticle(
                id="",
                title=title,
                url=url,
                category=section_info['name'],
                image_url=image_url,
            )
            articles.append(article)

        logger.info(f"Parsed {len(articles)} articles from {section_key}")
        return articles

    def _extract_article_from_container(
        self,
        container,
        section_info: dict,
        seen_urls: set,
    ) -> Optional[KantipurTVArticle]:
        """Extract article data from a container element."""
        # Find the main link
        link = container.find('a', href=True)
        if not link:
            return None

        url = link.get('href', '')
        if not url:
            return None

        # Normalize URL
        if not url.startswith('http'):
            if url.startswith('/'):
                url = f"{BASE_URL}{url}"
            else:
                return None

        # Skip if already seen
        if url in seen_urls:
            return None

        # Skip non-article URLs
        if any(skip in url for skip in ['/tag/', '/page/', '/author/', '#', 'javascript:']):
            return None

        # Extract title
        title = None
        title_el = container.find(['h1', 'h2', 'h3', 'h4', 'h5'], class_=re.compile(r'title|heading|name', re.I))
        if title_el:
            title = title_el.get_text(strip=True)

        if not title:
            title_el = container.find(['h1', 'h2', 'h3', 'h4', 'h5'])
            if title_el:
                title = title_el.get_text(strip=True)

        if not title:
            title = link.get_text(strip=True)

        # Skip if no valid title
        if not title or len(title) < 10:
            return None

        # Clean title
        title = re.sub(r'\s+', ' ', title).strip()

        # Extract summary
        summary = None
        summary_el = container.find(['p', 'div'], class_=re.compile(r'excerpt|summary|desc|intro', re.I))
        if summary_el:
            summary = summary_el.get_text(strip=True)

        # Extract image
        image_url = None
        img = container.find('img')
        if img:
            image_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')

        # Extract video URL if present
        video_url = None
        video = container.find('video')
        if video:
            video_url = video.get('src')
            if not video_url:
                source = video.find('source')
                if source:
                    video_url = source.get('src')

        # Also check for YouTube embeds
        if not video_url:
            iframe = container.find('iframe', src=re.compile(r'youtube|youtu\.be'))
            if iframe:
                video_url = iframe.get('src')

        # Extract date if available
        published_at = None
        date_el = container.find(['time', 'span', 'div'], class_=re.compile(r'date|time|published', re.I))
        if date_el:
            date_str = date_el.get('datetime') or date_el.get_text(strip=True)
            published_at = self._parse_date(date_str)

        return KantipurTVArticle(
            id="",
            title=title,
            url=url,
            category=section_info['name'],
            published_at=published_at,
            image_url=image_url,
            video_url=video_url,
            summary=summary,
        )

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Try to parse various date formats including Nepali."""
        if not date_str:
            return None

        # Common date formats
        date_formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%B %d, %Y",
            "%d %B %Y",
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    async def scrape_section(
        self,
        section_key: str,
        max_articles: int = 50,
    ) -> List[KantipurTVArticle]:
        """
        Scrape news from a specific section.

        Args:
            section_key: Section identifier (e.g., 'news', 'politics')
            max_articles: Maximum articles to return

        Returns:
            List of KantipurTVArticle objects
        """
        if section_key not in KANTIPURTV_SECTIONS:
            raise ValueError(f"Unknown section: {section_key}. Valid: {list(KANTIPURTV_SECTIONS.keys())}")

        section_info = KANTIPURTV_SECTIONS[section_key]
        all_articles = []

        # Scrape main section page and pagination
        for page_num in range(1, 4):  # Pages 1-3
            if page_num == 1:
                url = f"{BASE_URL}{section_info['path']}"
            else:
                # Try common pagination patterns
                url = f"{BASE_URL}{section_info['path']}?page={page_num}"

            logger.info(f"Scraping {url}")

            html = await self._fetch_page(url)
            if not html:
                break

            articles = self._parse_articles(html, section_key, section_info)
            if not articles:
                break

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

        logger.info(f"Total unique articles from {section_key}: {len(unique_articles)}")
        return unique_articles[:max_articles]

    async def scrape_homepage(
        self,
        max_articles: int = 50,
    ) -> List[KantipurTVArticle]:
        """
        Scrape news from the homepage.

        Args:
            max_articles: Maximum articles to return

        Returns:
            List of KantipurTVArticle objects
        """
        return await self.scrape_section('homepage', max_articles)

    async def scrape_all_sections(
        self,
        max_articles_per_section: int = 30,
    ) -> Dict[str, List[KantipurTVArticle]]:
        """
        Scrape from all sections.

        Args:
            max_articles_per_section: Max articles per section

        Returns:
            Dict mapping section key to list of articles
        """
        results = {}

        for section_key in KANTIPURTV_SECTIONS:
            try:
                articles = await self.scrape_section(section_key, max_articles_per_section)
                results[section_key] = articles
            except Exception as e:
                logger.error(f"Error scraping {section_key}: {e}")
                results[section_key] = []

        return results


# ============ Async functions for FastAPI integration ============

async def fetch_kantipurtv(
    section: Optional[str] = None,
    max_articles: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch articles from Kantipur TV.

    Args:
        section: Optional section to scrape. If None, scrapes homepage.
        max_articles: Maximum articles to return

    Returns:
        List of article dictionaries

    For use in FastAPI endpoints and scheduled tasks.
    """
    async with KantipurTVScraper() as scraper:
        if section:
            articles = await scraper.scrape_section(section, max_articles)
        else:
            articles = await scraper.scrape_homepage(max_articles)
        return [asdict(a) for a in articles]


async def fetch_kantipurtv_all_sections(
    max_articles_per_section: int = 30,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch articles from all Kantipur TV sections.
    """
    async with KantipurTVScraper() as scraper:
        results = await scraper.scrape_all_sections(max_articles_per_section)
        return {
            sec: [asdict(a) for a in articles]
            for sec, articles in results.items()
        }


async def fetch_kantipurtv_news(max_articles: int = 50) -> List[Dict[str, Any]]:
    """Convenience function to fetch news section."""
    return await fetch_kantipurtv('news', max_articles)


async def fetch_kantipurtv_politics(max_articles: int = 50) -> List[Dict[str, Any]]:
    """Convenience function to fetch politics section."""
    return await fetch_kantipurtv('politics', max_articles)


# ============ CLI for testing ============

async def main():
    print("=" * 60)
    print("Kantipur TV News Scraper")
    print("=" * 60)
    print(f"\nBase URL: {BASE_URL}")
    print("\nAvailable sections:")
    for key, info in KANTIPURTV_SECTIONS.items():
        print(f"  - {key}: {info['name']} ({info['description']})")
    print()

    print("[1] Scraping homepage...")
    articles = await fetch_kantipurtv(max_articles=20)

    print(f"\nFound {len(articles)} articles from homepage:")
    print("-" * 60)

    for i, article in enumerate(articles[:10], 1):
        title = article['title'][:50] + "..." if len(article['title']) > 50 else article['title']
        print(f"[{i}] {title}")
        print(f"    Category: {article['category']}")
        print(f"    URL: {article['url']}")
        if article.get('video_url'):
            print(f"    Video: {article['video_url']}")
        print()

    if len(articles) > 10:
        print(f"... and {len(articles) - 10} more")

    print("\n" + "=" * 60)
    print("[2] Scraping 'news' section...")
    news_articles = await fetch_kantipurtv_news(max_articles=10)
    print(f"Found {len(news_articles)} articles in news section")

    for i, article in enumerate(news_articles[:5], 1):
        title = article['title'][:50] + "..." if len(article['title']) > 50 else article['title']
        print(f"  [{i}] {title}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    asyncio.run(main())
