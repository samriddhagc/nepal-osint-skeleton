#!/usr/bin/env python3
"""
Nepali Times News Scraper

Scrapes English-language news articles from Nepali Times website.
Focuses on categories: Here Now, Opinion, and From the Nepali Press.
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
class NepaliTimesArticle:
    """Structured data for a Nepali Times news article."""
    id: str
    title: str
    url: str
    category: str
    source_id: str = "nepalitimes"
    source_name: str = "Nepali Times"
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    image_url: Optional[str] = None
    summary: Optional[str] = None
    language: str = "en"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        """Generate ID if not set."""
        if not self.id:
            # Try to extract article slug from URL
            slug_match = re.search(r'/([^/]+)/?$', self.url.rstrip('/'))
            if slug_match:
                slug = slug_match.group(1)[:30]
                self.id = f"nepalitimes_{slug}"
            else:
                self.id = f"nepalitimes_{hashlib.md5(self.url.encode()).hexdigest()[:12]}"


# Nepali Times categories to scrape
NEPALITIMES_CATEGORIES = {
    'here-now': {
        'name': 'Here Now',
        'path': '/category/here-now/',
        'description': 'Current news and events',
    },
    'opinion': {
        'name': 'Opinion',
        'path': '/category/opinion/',
        'description': 'Opinion pieces and editorials',
    },
    'from-the-nepali-press': {
        'name': 'From the Nepali Press',
        'path': '/category/from-the-nepali-press/',
        'description': 'Translated articles from Nepali media',
    },
}

BASE_URL = "https://www.nepalitimes.com"


class NepaliTimesScraper:
    """
    Async scraper for Nepali Times news website.

    Scrapes articles from the main English-language Nepali news site.
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

    async def __aenter__(self) -> "NepaliTimesScraper":
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
                "Accept-Language": "en-US,en;q=0.9",
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

    def _parse_articles(
        self,
        html: str,
        category_key: str,
        category_info: dict,
    ) -> List[NepaliTimesArticle]:
        """Parse articles from HTML content."""
        soup = BeautifulSoup(html, 'lxml')
        articles = []
        seen_urls = set()

        # Find article containers - Nepali Times uses article tags and div.post structures
        article_containers = soup.find_all(['article', 'div'], class_=re.compile(r'post|article|entry'))

        for container in article_containers:
            # Find the article link
            link = container.find('a', href=True)
            if not link:
                continue

            url = link.get('href', '')
            if not url:
                continue

            # Normalize URL
            if not url.startswith('http'):
                url = f"{BASE_URL}{url}" if url.startswith('/') else f"{BASE_URL}/{url}"

            # Skip non-article URLs
            if '/category/' in url or '/tag/' in url or '/page/' in url:
                continue

            # Skip duplicates
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Extract title
            title = None
            title_el = container.find(['h1', 'h2', 'h3', 'h4'], class_=re.compile(r'title|heading'))
            if title_el:
                title = title_el.get_text(strip=True)

            if not title:
                title_el = container.find(['h1', 'h2', 'h3', 'h4'])
                if title_el:
                    title = title_el.get_text(strip=True)

            if not title:
                title = link.get_text(strip=True)

            # Skip if no valid title
            if not title or len(title) < 10:
                continue

            # Clean title
            title = re.sub(r'\s+', ' ', title).strip()

            # Extract summary/excerpt
            summary = None
            excerpt_el = container.find(['p', 'div'], class_=re.compile(r'excerpt|summary|desc'))
            if excerpt_el:
                summary = excerpt_el.get_text(strip=True)

            # Extract author
            author = None
            author_el = container.find(['span', 'a', 'div'], class_=re.compile(r'author|byline|writer'))
            if author_el:
                author = author_el.get_text(strip=True)

            # Extract image
            image_url = None
            img = container.find('img')
            if img:
                image_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')

            # Extract date if available
            published_at = None
            date_el = container.find(['time', 'span', 'div'], class_=re.compile(r'date|time|published'))
            if date_el:
                date_str = date_el.get('datetime') or date_el.get_text(strip=True)
                published_at = self._parse_date(date_str)

            # Create article
            article = NepaliTimesArticle(
                id="",  # Will be generated in __post_init__
                title=title,
                url=url,
                category=category_info['name'],
                published_at=published_at,
                author=author,
                image_url=image_url,
                summary=summary,
            )
            articles.append(article)

        # Also check for standalone article links
        for link in soup.find_all('a', href=True):
            url = link.get('href', '')

            # Only process links that look like articles
            if not url or '/category/' in url or '/tag/' in url or '/page/' in url:
                continue
            if not re.search(r'/\d{4}/\d{2}/', url) and not re.search(r'/[a-z0-9-]{10,}/?$', url):
                continue

            # Normalize URL
            if not url.startswith('http'):
                url = f"{BASE_URL}{url}" if url.startswith('/') else f"{BASE_URL}/{url}"

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Try to get title from link
            title = link.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            title = re.sub(r'\s+', ' ', title).strip()

            article = NepaliTimesArticle(
                id="",
                title=title,
                url=url,
                category=category_info['name'],
            )
            articles.append(article)

        logger.info(f"Parsed {len(articles)} articles from {category_key}")
        return articles

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Try to parse various date formats."""
        if not date_str:
            return None

        date_formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%d %B %Y",
            "%b %d, %Y",
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    async def scrape_category(
        self,
        category_key: str,
        max_articles: int = 50,
    ) -> List[NepaliTimesArticle]:
        """
        Scrape news from a specific category.

        Args:
            category_key: Category identifier (e.g., 'here-now', 'opinion')
            max_articles: Maximum articles to return

        Returns:
            List of NepaliTimesArticle objects
        """
        if category_key not in NEPALITIMES_CATEGORIES:
            raise ValueError(f"Unknown category: {category_key}. Valid: {list(NEPALITIMES_CATEGORIES.keys())}")

        category_info = NEPALITIMES_CATEGORIES[category_key]
        all_articles = []

        # Scrape main category page and first few pagination pages
        for page_num in range(1, 4):  # Pages 1-3
            if page_num == 1:
                url = f"{BASE_URL}{category_info['path']}"
            else:
                url = f"{BASE_URL}{category_info['path']}page/{page_num}/"

            logger.info(f"Scraping {url}")

            html = await self._fetch_page(url)
            if not html:
                break

            articles = self._parse_articles(html, category_key, category_info)
            if not articles:
                break  # No more articles found

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

        logger.info(f"Total unique articles from {category_key}: {len(unique_articles)}")
        return unique_articles[:max_articles]

    async def scrape_homepage(
        self,
        max_articles: int = 50,
    ) -> List[NepaliTimesArticle]:
        """
        Scrape news from the homepage.

        Args:
            max_articles: Maximum articles to return

        Returns:
            List of NepaliTimesArticle objects
        """
        url = BASE_URL
        logger.info(f"Scraping homepage: {url}")

        html = await self._fetch_page(url)
        if not html:
            return []

        category_info = {'name': 'Homepage', 'path': '/'}
        articles = self._parse_articles(html, 'homepage', category_info)

        # Deduplicate
        seen_urls = set()
        unique_articles = []
        for article in articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)

        return unique_articles[:max_articles]

    async def scrape_all_categories(
        self,
        max_articles_per_category: int = 30,
    ) -> Dict[str, List[NepaliTimesArticle]]:
        """
        Scrape from all categories.

        Args:
            max_articles_per_category: Max articles per category

        Returns:
            Dict mapping category key to list of articles
        """
        results = {}

        for category_key in NEPALITIMES_CATEGORIES:
            try:
                articles = await self.scrape_category(category_key, max_articles_per_category)
                results[category_key] = articles
            except Exception as e:
                logger.error(f"Error scraping {category_key}: {e}")
                results[category_key] = []

        return results


# ============ Async functions for FastAPI integration ============

async def fetch_nepalitimes(
    category: Optional[str] = None,
    max_articles: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch articles from Nepali Times.

    Args:
        category: Optional category to scrape. If None, scrapes homepage.
        max_articles: Maximum articles to return

    Returns:
        List of article dictionaries

    For use in FastAPI endpoints and scheduled tasks.
    """
    async with NepaliTimesScraper() as scraper:
        if category:
            articles = await scraper.scrape_category(category, max_articles)
        else:
            articles = await scraper.scrape_homepage(max_articles)
        return [asdict(a) for a in articles]


async def fetch_nepalitimes_all_categories(
    max_articles_per_category: int = 30,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch articles from all Nepali Times categories.
    """
    async with NepaliTimesScraper() as scraper:
        results = await scraper.scrape_all_categories(max_articles_per_category)
        return {
            cat: [asdict(a) for a in articles]
            for cat, articles in results.items()
        }


async def fetch_nepalitimes_here_now(max_articles: int = 50) -> List[Dict[str, Any]]:
    """Convenience function to fetch Here Now category."""
    return await fetch_nepalitimes('here-now', max_articles)


async def fetch_nepalitimes_opinion(max_articles: int = 50) -> List[Dict[str, Any]]:
    """Convenience function to fetch Opinion category."""
    return await fetch_nepalitimes('opinion', max_articles)


# ============ CLI for testing ============

async def main():
    print("=" * 60)
    print("Nepali Times News Scraper")
    print("=" * 60)
    print(f"\nBase URL: {BASE_URL}")
    print("\nAvailable categories:")
    for key, info in NEPALITIMES_CATEGORIES.items():
        print(f"  - {key}: {info['name']} ({info['description']})")
    print()

    print("[1] Scraping homepage...")
    articles = await fetch_nepalitimes(max_articles=20)

    print(f"\nFound {len(articles)} articles from homepage:")
    print("-" * 60)

    for i, article in enumerate(articles[:10], 1):
        title = article['title'][:55] + "..." if len(article['title']) > 55 else article['title']
        print(f"[{i}] {title}")
        print(f"    Category: {article['category']}")
        print(f"    URL: {article['url']}")
        if article.get('author'):
            print(f"    Author: {article['author']}")
        print()

    if len(articles) > 10:
        print(f"... and {len(articles) - 10} more")

    print("\n" + "=" * 60)
    print("[2] Scraping 'Here Now' category...")
    here_now = await fetch_nepalitimes_here_now(max_articles=10)
    print(f"Found {len(here_now)} articles in Here Now category")

    for i, article in enumerate(here_now[:5], 1):
        title = article['title'][:55] + "..." if len(article['title']) > 55 else article['title']
        print(f"  [{i}] {title}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    asyncio.run(main())
