#!/usr/bin/env python3
"""
Ekantipur News Scraper

Scrapes news from Ekantipur's provincial and national pages since RSS feeds
return 404. Supports all 7 provinces plus national news.
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
class EkantipurArticle:
    """Structured data for an Ekantipur news article."""
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
            # Try to extract article ID from URL
            # URLs like: https://ekantipur.com/news/2024/01/15/article-slug-12345
            id_match = re.search(r'-(\d+)(?:\.html)?$', self.url)
            if id_match:
                self.id = f"ekantipur_{id_match.group(1)}"
            else:
                # Fallback to hash
                self.id = f"ekantipur_{hashlib.md5(self.url.encode()).hexdigest()[:12]}"


# Ekantipur provincial pages
EKANTIPUR_PROVINCES = {
    'koshi': {
        'name': 'Ekantipur Koshi',
        'base_url': 'https://ekantipur.com',
        'pages': ['/pradesh-1'],
        'province_name': 'Koshi Province',
        'province_number': 1,
        'source_id': 'ekantipur_koshi',
    },
    'madhesh': {
        'name': 'Ekantipur Madhesh',
        'base_url': 'https://ekantipur.com',
        'pages': ['/pradesh-2'],
        'province_name': 'Madhesh Province',
        'province_number': 2,
        'source_id': 'ekantipur_madhesh',
    },
    'bagmati': {
        'name': 'Ekantipur Bagmati',
        'base_url': 'https://ekantipur.com',
        'pages': ['/pradesh-3'],
        'province_name': 'Bagmati Province',
        'province_number': 3,
        'source_id': 'ekantipur_bagmati',
    },
    'gandaki': {
        'name': 'Ekantipur Gandaki',
        'base_url': 'https://ekantipur.com',
        'pages': ['/pradesh-4'],
        'province_name': 'Gandaki Province',
        'province_number': 4,
        'source_id': 'ekantipur_gandaki',
    },
    'lumbini': {
        'name': 'Ekantipur Lumbini',
        'base_url': 'https://ekantipur.com',
        'pages': ['/pradesh-5'],
        'province_name': 'Lumbini Province',
        'province_number': 5,
        'source_id': 'ekantipur_lumbini',
    },
    'karnali': {
        'name': 'Ekantipur Karnali',
        'base_url': 'https://ekantipur.com',
        'pages': ['/pradesh-6'],
        'province_name': 'Karnali Province',
        'province_number': 6,
        'source_id': 'ekantipur_karnali',
    },
    'sudurpashchim': {
        'name': 'Ekantipur Sudurpashchim',
        'base_url': 'https://ekantipur.com',
        'pages': ['/pradesh-7'],
        'province_name': 'Sudurpashchim Province',
        'province_number': 7,
        'source_id': 'ekantipur_sudurpashchim',
    },
}

# National Ekantipur site
EKANTIPUR_NATIONAL = {
    'name': 'Ekantipur National',
    'base_url': 'https://ekantipur.com',
    'pages': ['/'],
    'province_name': 'National',
    'source_id': 'ekantipur_national',
}


class EkantipurScraper:
    """
    Async scraper for Ekantipur news pages.

    Scrapes provincial and national news from Ekantipur's HTML pages
    since their RSS feeds return 404.
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

    async def __aenter__(self) -> "EkantipurScraper":
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
        source_info: dict,
    ) -> List[EkantipurArticle]:
        """Parse articles from HTML content."""
        soup = BeautifulSoup(html, 'lxml')
        articles = []
        seen_urls = set()

        # Ekantipur article URL patterns
        # Common patterns:
        # /news/2024/01/15/article-slug-12345
        # /national/2024/01/15/article-12345
        # /pradesh-1/2024/01/15/article-12345
        article_pattern = re.compile(
            r'/(news|national|sports|entertainment|business|opinion|world|pradesh-\d+|'
            r'lifestyle|technology|health|education|feature|photo-feature|video)'
            r'/\d{4}/\d{2}/\d{2}/[^"\'#\s]+'
        )

        # Find all article links
        for link in soup.find_all('a', href=article_pattern):
            url = link.get('href', '')
            if not url:
                continue

            # Normalize URL
            if not url.startswith('http'):
                url = f"https://ekantipur.com{url}"

            # Skip duplicates
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Extract title
            title = self._extract_title(link)

            # Skip if no valid title
            if not title or len(title) < 10:
                continue

            # Clean title
            title = re.sub(r'\s+', ' ', title).strip()

            # Extract image if available
            image_url = self._extract_image(link)

            # Extract summary if available
            summary = self._extract_summary(link)

            # Try to extract published date from URL
            published_at = self._extract_date_from_url(url)

            # Create article
            article = EkantipurArticle(
                id="",  # Will be generated in __post_init__
                title=title,
                url=url,
                province=source_info['province_name'],
                source_id=source_info['source_id'],
                source_name=source_info['name'],
                published_at=published_at,
                image_url=image_url,
                summary=summary,
                language='ne' if self._has_nepali_chars(title) else 'en',
            )
            articles.append(article)

        logger.info(f"Parsed {len(articles)} articles from {source_info['name']}")
        return articles

    def _extract_title(self, link) -> Optional[str]:
        """Extract article title from link element."""
        # Try to find title in heading elements
        for tag in ['h1', 'h2', 'h3', 'h4', 'h5']:
            title_el = link.find(tag)
            if title_el:
                return title_el.get_text(strip=True)

        # Try span with title class
        title_span = link.find('span', class_=re.compile(r'title|headline', re.I))
        if title_span:
            return title_span.get_text(strip=True)

        # Try link text directly
        link_text = link.get_text(strip=True)
        if link_text and len(link_text) > 10:
            return link_text

        # Try title attribute
        return link.get('title')

    def _extract_image(self, link) -> Optional[str]:
        """Extract image URL from link element."""
        # Look for img tag
        img = link.find('img')
        if img:
            return img.get('src') or img.get('data-src') or img.get('data-lazy-src')

        # Look for background image in style
        parent = link.parent
        if parent:
            style = parent.get('style', '')
            bg_match = re.search(r'background-image:\s*url\(["\']?([^"\')\s]+)', style)
            if bg_match:
                return bg_match.group(1)

        return None

    def _extract_summary(self, link) -> Optional[str]:
        """Extract article summary/excerpt if available."""
        parent = link.parent
        if not parent:
            return None

        # Look for paragraph or description text near the link
        for tag in ['p', 'span', 'div']:
            desc_el = parent.find(tag, class_=re.compile(r'desc|excerpt|summary|teaser', re.I))
            if desc_el:
                text = desc_el.get_text(strip=True)
                if text and len(text) > 20:
                    return text[:500]  # Limit summary length

        return None

    def _extract_date_from_url(self, url: str) -> Optional[datetime]:
        """Extract publication date from URL pattern."""
        date_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
        if date_match:
            try:
                return datetime(
                    int(date_match.group(1)),
                    int(date_match.group(2)),
                    int(date_match.group(3))
                )
            except ValueError:
                pass
        return None

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
    ) -> List[EkantipurArticle]:
        """
        Scrape news from a specific province's Ekantipur page.

        Args:
            province_key: Province identifier (e.g., 'gandaki', 'koshi')
            max_articles: Maximum articles to return

        Returns:
            List of EkantipurArticle objects
        """
        if province_key not in EKANTIPUR_PROVINCES:
            raise ValueError(f"Unknown province: {province_key}. Valid: {list(EKANTIPUR_PROVINCES.keys())}")

        province_info = EKANTIPUR_PROVINCES[province_key]
        all_articles = []

        for page_path in province_info['pages']:
            url = f"{province_info['base_url']}{page_path}"
            logger.info(f"Scraping {url}")

            html = await self._fetch_page(url)
            if not html:
                continue

            articles = self._parse_articles(html, province_info)
            all_articles.extend(articles)

            if len(all_articles) >= max_articles:
                break

        # Deduplicate by URL
        unique_articles = self._deduplicate_articles(all_articles)

        logger.info(f"Total unique articles from {province_key}: {len(unique_articles)}")
        return unique_articles[:max_articles]

    async def scrape_national(
        self,
        max_articles: int = 50,
    ) -> List[EkantipurArticle]:
        """
        Scrape national news from Ekantipur main page.

        Args:
            max_articles: Maximum articles to return

        Returns:
            List of EkantipurArticle objects
        """
        all_articles = []

        for page_path in EKANTIPUR_NATIONAL['pages']:
            url = f"{EKANTIPUR_NATIONAL['base_url']}{page_path}"
            logger.info(f"Scraping national news from {url}")

            html = await self._fetch_page(url)
            if not html:
                continue

            articles = self._parse_articles(html, EKANTIPUR_NATIONAL)
            all_articles.extend(articles)

            if len(all_articles) >= max_articles:
                break

        # Deduplicate by URL
        unique_articles = self._deduplicate_articles(all_articles)

        logger.info(f"Total unique national articles: {len(unique_articles)}")
        return unique_articles[:max_articles]

    async def scrape_all_provinces(
        self,
        max_articles_per_province: int = 30,
    ) -> Dict[str, List[EkantipurArticle]]:
        """
        Scrape from all provincial Ekantipur pages.

        Args:
            max_articles_per_province: Max articles per province

        Returns:
            Dict mapping province key to list of articles
        """
        results = {}

        for province_key in EKANTIPUR_PROVINCES:
            try:
                articles = await self.scrape_province(province_key, max_articles_per_province)
                results[province_key] = articles
            except Exception as e:
                logger.error(f"Error scraping {province_key}: {e}")
                results[province_key] = []

        return results

    def _deduplicate_articles(
        self,
        articles: List[EkantipurArticle],
    ) -> List[EkantipurArticle]:
        """Remove duplicate articles by URL."""
        seen_urls = set()
        unique = []
        for article in articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique.append(article)
        return unique


# ============ Async functions for FastAPI integration ============

async def fetch_ekantipur_province(
    province_key: str = 'gandaki',
    max_articles: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch articles from a specific Ekantipur provincial page.

    For use in FastAPI endpoints and scheduled tasks.

    Args:
        province_key: Province identifier (koshi, madhesh, bagmati, gandaki, lumbini, karnali, sudurpashchim)
        max_articles: Maximum number of articles to return

    Returns:
        List of article dictionaries
    """
    async with EkantipurScraper() as scraper:
        articles = await scraper.scrape_province(province_key, max_articles)
        return [asdict(a) for a in articles]


async def fetch_all_ekantipur_provinces(
    max_articles_per_province: int = 30,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch articles from all Ekantipur provincial pages.

    Args:
        max_articles_per_province: Maximum articles per province

    Returns:
        Dict mapping province key to list of article dictionaries
    """
    async with EkantipurScraper() as scraper:
        results = await scraper.scrape_all_provinces(max_articles_per_province)
        return {
            prov: [asdict(a) for a in articles]
            for prov, articles in results.items()
        }


async def fetch_ekantipur_national(
    max_articles: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch national news from Ekantipur main page.

    Args:
        max_articles: Maximum number of articles to return

    Returns:
        List of article dictionaries
    """
    async with EkantipurScraper() as scraper:
        articles = await scraper.scrape_national(max_articles)
        return [asdict(a) for a in articles]


# ============ CLI for testing ============

async def main():
    print("=" * 60)
    print("Ekantipur News Scraper")
    print("=" * 60)
    print("\nAvailable provinces:")
    for key, info in EKANTIPUR_PROVINCES.items():
        print(f"  - {key}: {info['name']} ({info['province_name']})")
    print(f"  - national: {EKANTIPUR_NATIONAL['name']} (National)")
    print()

    # Test national news
    print("[1] Scraping national news...")
    national_articles = await fetch_ekantipur_national(max_articles=15)

    print(f"\nFound {len(national_articles)} national articles:")
    print("-" * 60)

    for i, article in enumerate(national_articles[:5], 1):
        title = article['title'][:60] + "..." if len(article['title']) > 60 else article['title']
        print(f"[{i}] {title}")
        print(f"    Source: {article['source_name']}")
        print(f"    URL: {article['url']}")
        if article.get('published_at'):
            print(f"    Date: {article['published_at']}")
        print()

    if len(national_articles) > 5:
        print(f"... and {len(national_articles) - 5} more national articles")

    print()
    print("=" * 60)

    # Test one province
    print("\n[2] Scraping Gandaki province news...")
    gandaki_articles = await fetch_ekantipur_province('gandaki', max_articles=15)

    print(f"\nFound {len(gandaki_articles)} Gandaki articles:")
    print("-" * 60)

    for i, article in enumerate(gandaki_articles[:5], 1):
        title = article['title'][:60] + "..." if len(article['title']) > 60 else article['title']
        print(f"[{i}] {title}")
        print(f"    Source: {article['source_name']}")
        print(f"    URL: {article['url']}")
        print()

    if len(gandaki_articles) > 5:
        print(f"... and {len(gandaki_articles) - 5} more Gandaki articles")

    print()
    print("=" * 60)

    # Summary of all provinces
    print("\n[3] Fetching summary from all provinces...")
    all_provinces = await fetch_all_ekantipur_provinces(max_articles_per_province=10)

    print("\nArticle count by province:")
    print("-" * 60)
    total = 0
    for prov_key, articles in all_provinces.items():
        prov_info = EKANTIPUR_PROVINCES[prov_key]
        print(f"  {prov_info['province_name']}: {len(articles)} articles")
        total += len(articles)

    print("-" * 60)
    print(f"  Total: {total} articles across all provinces")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())
