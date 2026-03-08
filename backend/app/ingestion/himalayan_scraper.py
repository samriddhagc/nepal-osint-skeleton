#!/usr/bin/env python3
"""
The Himalayan Times News Scraper

Scrapes news from The Himalayan Times (thehimalayantimes.com) since their
RSS feed returns malformed XML. Extracts articles from HTML pages directly.
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
class HimalayanArticle:
    """Structured data for a Himalayan Times news article."""
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
            # URLs like: /nepal/article-title-slug or /business/article-title
            # Use the URL path as a unique identifier
            url_path = self.url.replace('https://www.thehimalayantimes.com', '')
            url_hash = hashlib.md5(url_path.encode()).hexdigest()[:12]
            self.id = f"himalayan_{url_hash}"


# The Himalayan Times configuration
HIMALAYAN_BASE_URL = "https://www.thehimalayantimes.com"

HIMALAYAN_CATEGORIES = {
    'home': {
        'name': 'The Himalayan Times - Home',
        'path': '/',
        'category_name': 'General',
    },
    'nepal': {
        'name': 'The Himalayan Times - Nepal',
        'path': '/nepal',
        'category_name': 'Nepal',
    },
    'kathmandu': {
        'name': 'The Himalayan Times - Kathmandu',
        'path': '/kathmandu',
        'category_name': 'Kathmandu',
    },
    'business': {
        'name': 'The Himalayan Times - Business',
        'path': '/business',
        'category_name': 'Business',
    },
    'world': {
        'name': 'The Himalayan Times - World',
        'path': '/world',
        'category_name': 'World',
    },
}


class HimalayanScraper:
    """
    Async scraper for The Himalayan Times news pages.

    Since The Himalayan Times RSS feed returns malformed XML, this scrapes
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

    async def __aenter__(self) -> "HimalayanScraper":
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
                    # Handle encoding issues - site may have mixed encodings
                    try:
                        return await response.text()
                    except UnicodeDecodeError:
                        # Fallback to reading bytes and decoding with error handling
                        content = await response.read()
                        return content.decode('utf-8', errors='replace')
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
    ) -> List[HimalayanArticle]:
        """Parse articles from HTML content."""
        soup = BeautifulSoup(html, 'lxml')
        articles = []
        seen_urls = set()

        # The Himalayan Times uses various patterns for article links
        # URLs can be absolute (https://thehimalayantimes.com/nepal/article-slug)
        # or relative (/nepal/article-slug)
        article_categories = ['nepal', 'kathmandu', 'business', 'world', 'entertainment', 'sports', 'opinion', 'lifestyle', 'blog']

        # Find all anchor tags
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if not href:
                continue

            # Normalize URL first - convert absolute to path for checking
            url = href
            path = href

            if href.startswith('https://thehimalayantimes.com'):
                path = href.replace('https://thehimalayantimes.com', '')
                url = href
            elif href.startswith('https://www.thehimalayantimes.com'):
                path = href.replace('https://www.thehimalayantimes.com', '')
                url = href.replace('www.', '')  # Normalize to non-www
            elif href.startswith('/'):
                path = href
                url = f"{HIMALAYAN_BASE_URL}{href}"
            else:
                # Skip external URLs
                continue

            # Skip non-article links
            if any(skip in path.lower() for skip in [
                '/author/', '/tag/', '/page/', 'javascript:', '#',
                '/wp-content/', '/feed/', '.xml', '/category/',
                '/morearticles/', '/archives', '/about-us', '/contact-us',
                '/advertise', '/covid', '/video', '/epaper'
            ]):
                continue

            # Check if it's an article URL
            # Article URLs have format: /category/article-slug
            path_parts = [p for p in path.split('/') if p]

            if len(path_parts) < 2:
                continue

            category = path_parts[0].lower()
            slug = path_parts[1] if len(path_parts) > 1 else ''

            # Must be a known category and have a slug with hyphens (indicating article title)
            is_article = (
                category in article_categories and
                len(slug) > 10 and
                '-' in slug
            )

            if not is_article:
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

            # Skip if title looks like navigation text
            if title.lower() in ['read more', 'more', 'view all', 'see all', 'click here']:
                continue

            # Extract image if available
            image_url = self._extract_image(link)

            # Extract summary if available
            summary = self._extract_summary(link)

            # Determine category from URL or use provided category
            detected_category = self._detect_category(url, category_info['category_name'])

            # Create article
            article = HimalayanArticle(
                id="",  # Will be generated in __post_init__
                title=title,
                url=url,
                category=detected_category,
                source_id="himalayan_times",
                source_name="The Himalayan Times",
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
        for class_name in ['title', 'headline', 'news-title', 'article-title', 'entry-title']:
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
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                return self._normalize_image_url(src)

        # Look in parent container
        parent = link_element.parent
        if parent:
            img = parent.find('img')
            if img:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    return self._normalize_image_url(src)

        return None

    def _normalize_image_url(self, url: str) -> str:
        """Normalize image URL to absolute URL."""
        if url.startswith('//'):
            return f"https:{url}"
        elif url.startswith('/'):
            return f"{HIMALAYAN_BASE_URL}{url}"
        return url

    def _extract_summary(self, link_element) -> Optional[str]:
        """Extract summary/description from link element or parent."""
        # Look for paragraph in parent
        parent = link_element.parent
        if parent:
            # Try to find a description/summary element
            for class_name in ['summary', 'description', 'excerpt', 'intro', 'lead']:
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

        if '/nepal/' in url_lower or url_lower.endswith('/nepal'):
            return 'Nepal'
        elif '/kathmandu/' in url_lower or url_lower.endswith('/kathmandu'):
            return 'Kathmandu'
        elif '/business/' in url_lower or url_lower.endswith('/business'):
            return 'Business'
        elif '/world/' in url_lower or url_lower.endswith('/world'):
            return 'World'
        elif '/entertainment/' in url_lower:
            return 'Entertainment'
        elif '/sports/' in url_lower:
            return 'Sports'
        elif '/opinion/' in url_lower:
            return 'Opinion'
        elif '/lifestyle/' in url_lower:
            return 'Lifestyle'

        return default_category

    async def scrape_category(
        self,
        category_key: str,
        max_articles: int = 50,
    ) -> List[HimalayanArticle]:
        """
        Scrape news from a specific category page.

        Args:
            category_key: Category identifier (e.g., 'nepal', 'business')
            max_articles: Maximum articles to return

        Returns:
            List of HimalayanArticle objects
        """
        if category_key not in HIMALAYAN_CATEGORIES:
            raise ValueError(f"Unknown category: {category_key}. Valid: {list(HIMALAYAN_CATEGORIES.keys())}")

        category_info = HIMALAYAN_CATEGORIES[category_key]
        url = f"{HIMALAYAN_BASE_URL}{category_info['path']}"

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
    ) -> Dict[str, List[HimalayanArticle]]:
        """
        Scrape from all category pages.

        Args:
            max_articles_per_category: Max articles per category

        Returns:
            Dict mapping category key to list of articles
        """
        results = {}

        for category_key in HIMALAYAN_CATEGORIES:
            try:
                articles = await self.scrape_category(category_key, max_articles_per_category)
                results[category_key] = articles
            except Exception as e:
                logger.error(f"Error scraping {category_key}: {e}")
                results[category_key] = []

        return results

    async def scrape_home(self, max_articles: int = 50) -> List[HimalayanArticle]:
        """
        Scrape articles from the homepage.

        Args:
            max_articles: Maximum articles to return

        Returns:
            List of HimalayanArticle objects
        """
        return await self.scrape_category('home', max_articles)


# ============ Async functions for FastAPI integration ============

async def fetch_himalayan_news(
    max_articles: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch articles from The Himalayan Times homepage.

    For use in FastAPI endpoints and scheduled tasks.

    Args:
        max_articles: Maximum number of articles to fetch

    Returns:
        List of article dictionaries
    """
    async with HimalayanScraper() as scraper:
        articles = await scraper.scrape_home(max_articles)
        return [asdict(a) for a in articles]


async def fetch_himalayan_category(
    category: str = 'nepal',
    max_articles: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch articles from a specific Himalayan Times category.

    Args:
        category: Category key ('nepal', 'kathmandu', 'business', 'world', 'home')
        max_articles: Maximum number of articles to fetch

    Returns:
        List of article dictionaries
    """
    async with HimalayanScraper() as scraper:
        articles = await scraper.scrape_category(category, max_articles)
        return [asdict(a) for a in articles]


async def fetch_all_himalayan_categories(
    max_articles_per_category: int = 30,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch articles from all Himalayan Times categories.

    Args:
        max_articles_per_category: Max articles per category

    Returns:
        Dict mapping category key to list of article dictionaries
    """
    async with HimalayanScraper() as scraper:
        results = await scraper.scrape_all_categories(max_articles_per_category)
        return {
            cat: [asdict(a) for a in articles]
            for cat, articles in results.items()
        }


# ============ CLI for testing ============

async def main():
    print("=" * 60)
    print("The Himalayan Times News Scraper")
    print("=" * 60)
    print(f"\nBase URL: {HIMALAYAN_BASE_URL}")
    print("\nAvailable categories:")
    for key, info in HIMALAYAN_CATEGORIES.items():
        print(f"  - {key}: {info['name']} ({info['path']})")
    print()

    print("[1] Scraping homepage news...")
    articles = await fetch_himalayan_news(max_articles=20)

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
    print("[2] Scraping Nepal category...")
    nepal_articles = await fetch_himalayan_category('nepal', max_articles=10)

    print(f"\nFound {len(nepal_articles)} articles from Nepal category:")
    print("-" * 60)

    for i, article in enumerate(nepal_articles[:5], 1):
        title = article['title'][:55] + "..." if len(article['title']) > 55 else article['title']
        print(f"[{i}] {title}")
        print(f"    URL: {article['url']}")
        print()

    print("\n" + "=" * 60)
    print("[3] Scraping Business category...")
    business_articles = await fetch_himalayan_category('business', max_articles=10)

    print(f"\nFound {len(business_articles)} articles from Business category:")
    print("-" * 60)

    for i, article in enumerate(business_articles[:5], 1):
        title = article['title'][:55] + "..." if len(article['title']) > 55 else article['title']
        print(f"[{i}] {title}")
        print(f"    URL: {article['url']}")
        print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    asyncio.run(main())
