#!/usr/bin/env python3
"""
My Republica News Scraper

Scrapes news from My Republica (myrepublica.nagariknetwork.com) since their
RSS feed returns 404. Extracts articles from HTML pages directly.
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
class RepublicaArticle:
    """Structured data for a My Republica news article."""
    id: str
    title: str
    url: str
    category: str
    source_id: str
    source_name: str
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    summary: Optional[str] = None
    language: str = "en"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        """Generate ID if not set."""
        if not self.id:
            # Try to extract article ID from URL
            # URLs like: /news/xyz-123456 or /category/xyz-123456
            id_match = re.search(r'-(\d+)(?:\.html)?$', self.url)
            if id_match:
                self.id = f"republica_{id_match.group(1)}"
            else:
                self.id = f"republica_{hashlib.md5(self.url.encode()).hexdigest()[:12]}"


# My Republica category configuration
REPUBLICA_BASE_URL = "https://myrepublica.nagariknetwork.com"

REPUBLICA_CATEGORIES = {
    'home': {
        'name': 'My Republica - Home',
        'path': '/',
        'category_name': 'General',
    },
    'news': {
        'name': 'My Republica - News',
        'path': '/category/news',
        'category_name': 'News',
    },
    'economy': {
        'name': 'My Republica - Economy',
        'path': '/category/economy',
        'category_name': 'Economy',
    },
    'politics': {
        'name': 'My Republica - Politics',
        'path': '/category/politics',
        'category_name': 'Politics',
    },
    'sports': {
        'name': 'My Republica - Sports',
        'path': '/category/sports',
        'category_name': 'Sports',
    },
}


class RepublicaScraper:
    """
    Async scraper for My Republica news pages.

    Since My Republica's RSS feeds return 404, this scrapes
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

    async def __aenter__(self) -> "RepublicaScraper":
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
            await asyncio.sleep(self.delay)  # Rate limiting
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
    ) -> List[RepublicaArticle]:
        """Parse articles from HTML content."""
        soup = BeautifulSoup(html, 'lxml')
        articles = []
        seen_urls = set()

        # Find all article links - My Republica uses various patterns
        # Look for links that contain article-like paths
        article_patterns = [
            # Common patterns in My Republica URLs
            re.compile(r'/news/[^/]+-\d+'),
            re.compile(r'/category/[^/]+/[^/]+-\d+'),
            re.compile(r'/[^/]+-\d+\.html'),
        ]

        # Find all anchor tags
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if not href:
                continue

            # Check if URL matches article patterns
            is_article = any(pattern.search(href) for pattern in article_patterns)
            if not is_article:
                continue

            # Normalize URL
            if href.startswith('/'):
                url = f"{REPUBLICA_BASE_URL}{href}"
            elif href.startswith('http'):
                url = href
            else:
                continue

            # Skip if not from My Republica domain
            if 'myrepublica.nagariknetwork.com' not in url:
                continue

            # Skip duplicates
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Extract title
            title = self._extract_title(link)
            if not title or len(title) < 10:
                continue

            # Clean title
            title = re.sub(r'\s+', ' ', title).strip()

            # Extract image if available
            image_url = self._extract_image(link)

            # Extract summary if available
            summary = self._extract_summary(link)

            # Determine category from URL or use provided category
            detected_category = self._detect_category(url, category_info['category_name'])

            # Create article
            article = RepublicaArticle(
                id="",  # Will be generated in __post_init__
                title=title,
                url=url,
                category=detected_category,
                source_id="myrepublica",
                source_name="My Republica",
                image_url=image_url,
                summary=summary,
                language='en',
            )
            articles.append(article)

        logger.info(f"Parsed {len(articles)} articles from {category_key}")
        return articles

    def _extract_title(self, link_element) -> Optional[str]:
        """Extract title from link element."""
        # Try to find title in heading elements
        for tag in ['h1', 'h2', 'h3', 'h4', 'h5']:
            title_el = link_element.find(tag)
            if title_el:
                return title_el.get_text(strip=True)

        # Try specific class names common in news sites
        for class_name in ['title', 'headline', 'news-title', 'article-title']:
            title_el = link_element.find(class_=re.compile(class_name, re.I))
            if title_el:
                return title_el.get_text(strip=True)

        # Fall back to link text
        text = link_element.get_text(strip=True)
        if text:
            return text

        # Try title attribute
        return link_element.get('title')

    def _extract_image(self, link_element) -> Optional[str]:
        """Extract image URL from link element or parent."""
        # Look within the link
        img = link_element.find('img')
        if img:
            return img.get('src') or img.get('data-src') or img.get('data-lazy-src')

        # Look in parent container
        parent = link_element.parent
        if parent:
            img = parent.find('img')
            if img:
                return img.get('src') or img.get('data-src') or img.get('data-lazy-src')

        return None

    def _extract_summary(self, link_element) -> Optional[str]:
        """Extract summary/description from link element or parent."""
        # Look for paragraph in parent
        parent = link_element.parent
        if parent:
            # Try to find a description/summary element
            for class_name in ['summary', 'description', 'excerpt', 'intro']:
                desc_el = parent.find(class_=re.compile(class_name, re.I))
                if desc_el:
                    text = desc_el.get_text(strip=True)
                    if text and len(text) > 20:
                        return text[:500]  # Limit summary length

            # Try paragraph
            p = parent.find('p')
            if p:
                text = p.get_text(strip=True)
                if text and len(text) > 20:
                    return text[:500]

        return None

    def _detect_category(self, url: str, default_category: str) -> str:
        """Detect category from URL pattern."""
        url_lower = url.lower()

        if '/politics/' in url_lower or '/category/politics' in url_lower:
            return 'Politics'
        elif '/economy/' in url_lower or '/category/economy' in url_lower:
            return 'Economy'
        elif '/sports/' in url_lower or '/category/sports' in url_lower:
            return 'Sports'
        elif '/news/' in url_lower or '/category/news' in url_lower:
            return 'News'
        elif '/entertainment/' in url_lower:
            return 'Entertainment'
        elif '/world/' in url_lower:
            return 'World'
        elif '/opinion/' in url_lower:
            return 'Opinion'

        return default_category

    async def scrape_category(
        self,
        category_key: str,
        max_articles: int = 50,
    ) -> List[RepublicaArticle]:
        """
        Scrape news from a specific category page.

        Args:
            category_key: Category identifier (e.g., 'news', 'politics')
            max_articles: Maximum articles to return

        Returns:
            List of RepublicaArticle objects
        """
        if category_key not in REPUBLICA_CATEGORIES:
            raise ValueError(f"Unknown category: {category_key}. Valid: {list(REPUBLICA_CATEGORIES.keys())}")

        category_info = REPUBLICA_CATEGORIES[category_key]
        url = f"{REPUBLICA_BASE_URL}{category_info['path']}"

        logger.info(f"Scraping {url}")
        html = await self._fetch_page(url)

        if not html:
            return []

        articles = self._parse_articles(html, category_key, category_info)

        # Deduplicate by URL (in case of duplicates)
        seen_urls = set()
        unique_articles = []
        for article in articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)

        logger.info(f"Total unique articles from {category_key}: {len(unique_articles)}")
        return unique_articles[:max_articles]

    async def scrape_all_categories(
        self,
        max_articles_per_category: int = 30,
    ) -> Dict[str, List[RepublicaArticle]]:
        """
        Scrape from all category pages.

        Args:
            max_articles_per_category: Max articles per category

        Returns:
            Dict mapping category key to list of articles
        """
        results = {}

        for category_key in REPUBLICA_CATEGORIES:
            try:
                articles = await self.scrape_category(category_key, max_articles_per_category)
                results[category_key] = articles
            except Exception as e:
                logger.error(f"Error scraping {category_key}: {e}")
                results[category_key] = []

        return results

    async def scrape_home(self, max_articles: int = 50) -> List[RepublicaArticle]:
        """
        Scrape articles from the homepage.

        Args:
            max_articles: Maximum articles to return

        Returns:
            List of RepublicaArticle objects
        """
        return await self.scrape_category('home', max_articles)


# ============ Async functions for FastAPI integration ============

async def fetch_republica_news(
    max_articles: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch articles from My Republica homepage.

    For use in FastAPI endpoints and scheduled tasks.

    Args:
        max_articles: Maximum number of articles to fetch

    Returns:
        List of article dictionaries
    """
    async with RepublicaScraper() as scraper:
        articles = await scraper.scrape_home(max_articles)
        return [asdict(a) for a in articles]


async def fetch_republica_category(
    category: str = 'news',
    max_articles: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch articles from a specific My Republica category.

    Args:
        category: Category key ('news', 'economy', 'politics', 'sports', 'home')
        max_articles: Maximum number of articles to fetch

    Returns:
        List of article dictionaries
    """
    async with RepublicaScraper() as scraper:
        articles = await scraper.scrape_category(category, max_articles)
        return [asdict(a) for a in articles]


async def fetch_all_republica_categories(
    max_articles_per_category: int = 30,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch articles from all My Republica categories.

    Args:
        max_articles_per_category: Max articles per category

    Returns:
        Dict mapping category key to list of article dictionaries
    """
    async with RepublicaScraper() as scraper:
        results = await scraper.scrape_all_categories(max_articles_per_category)
        return {
            cat: [asdict(a) for a in articles]
            for cat, articles in results.items()
        }


# ============ CLI for testing ============

async def main():
    print("=" * 60)
    print("My Republica News Scraper")
    print("=" * 60)
    print(f"\nBase URL: {REPUBLICA_BASE_URL}")
    print("\nAvailable categories:")
    for key, info in REPUBLICA_CATEGORIES.items():
        print(f"  - {key}: {info['name']} ({info['path']})")
    print()

    print("[1] Scraping homepage news...")
    articles = await fetch_republica_news(max_articles=20)

    print(f"\nFound {len(articles)} articles from homepage:")
    print("-" * 60)

    for i, article in enumerate(articles[:10], 1):
        title = article['title'][:55] + "..." if len(article['title']) > 55 else article['title']
        print(f"[{i}] {title}")
        print(f"    Category: {article['category']}")
        print(f"    URL: {article['url']}")
        if article.get('summary'):
            summary = article['summary'][:80] + "..." if len(article['summary']) > 80 else article['summary']
            print(f"    Summary: {summary}")
        print()

    if len(articles) > 10:
        print(f"... and {len(articles) - 10} more")

    print("\n" + "=" * 60)
    print("[2] Scraping Politics category...")
    politics_articles = await fetch_republica_category('politics', max_articles=10)

    print(f"\nFound {len(politics_articles)} articles from politics:")
    print("-" * 60)

    for i, article in enumerate(politics_articles[:5], 1):
        title = article['title'][:55] + "..." if len(article['title']) > 55 else article['title']
        print(f"[{i}] {title}")
        print(f"    URL: {article['url']}")
        print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    asyncio.run(main())
