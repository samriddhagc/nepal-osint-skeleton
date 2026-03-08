#!/usr/bin/env python3
"""
MoHA (Ministry of Home Affairs) Nepal Scraper

Scrapes press releases, notices, and circulars from moha.gov.np
Uses direct HTML scraping with pagination support.
"""

import requests
from bs4 import BeautifulSoup
import re
import hashlib
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
import urllib3

# Suppress SSL warnings for Nepal govt sites
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class MoHAPost:
    """Structured data for a MoHA post/notice"""
    id: str
    title: str
    url: str
    date_bs: Optional[str] = None  # Bikram Sambat date
    date: Optional[str] = None  # Gregorian date if available
    category: str = "press-release"
    has_attachment: bool = False
    source: str = "moha.gov.np"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class MoHAScraper:
    """
    Scraper for Ministry of Home Affairs Nepal website.

    Supported categories:
    - press-release-en: English press releases
    - press-release-ne: Nepali press releases
    - notice-en: English notices
    - notice-ne: Nepali notices
    - circular-en: English circulars
    - circular-ne: Nepali circulars
    """

    BASE_URL = "https://moha.gov.np"

    # Page URL patterns
    PAGES = {
        'press-release-en': '/en/page/press-release',
        'press-release-ne': '/page/press-release',
        'notice-en': '/en/page/notice',
        'notice-ne': '/page/notice',
        'circular-en': '/en/page/circular',
        'circular-ne': '/page/circular',
    }

    def __init__(self, delay: float = 0.5, verify_ssl: bool = False):
        """
        Initialize the scraper.

        Args:
            delay: Delay between requests in seconds
            verify_ssl: Whether to verify SSL certificates (Nepal govt sites often have issues)
        """
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ne;q=0.8',
        })
        self.delay = delay
        self.verify_ssl = verify_ssl

    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch a page and return parsed BeautifulSoup object."""
        try:
            import time
            time.sleep(self.delay)

            response = self.session.get(url, verify=self.verify_ssl, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def _parse_table_posts(self, soup: BeautifulSoup, category: str) -> List[MoHAPost]:
        """Parse posts from table-based layout."""
        posts = []

        table = soup.find('table')
        if not table:
            return posts

        tbody = table.find('tbody') or table

        for row in tbody.find_all('tr'):
            cells = row.find_all('td')
            if not cells:
                continue

            # Find the main link
            link = row.find('a', href=True)
            if not link:
                continue

            # Extract title - clean up extra whitespace and "X ago" suffixes
            title = link.get_text(strip=True)
            # Remove relative time suffixes like "4 months ago"
            title = re.sub(r'\d+\s*(month|day|week|year|hour|minute)s?\s*ago\s*$', '', title, flags=re.I).strip()

            if not title:
                continue

            # Build URL
            url = link['href']
            if not url.startswith('http'):
                url = f"{self.BASE_URL}{url}"

            # Extract date (usually in first column, BS format like 2082-09-25)
            date_bs = None
            for cell in cells:
                text = cell.get_text(strip=True)
                # Match BS date format: YYYY-MM-DD where year is 2000+
                bs_match = re.search(r'(20\d{2}-\d{2}-\d{2})', text)
                if bs_match:
                    date_bs = bs_match.group(1)
                    break

            # Check for attachments (look for file icons or download links)
            has_attachment = bool(row.find('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)))
            if not has_attachment:
                # Check for file cell
                file_cell = row.find('td', class_=lambda x: x and 'file' in x.lower() if x else False)
                has_attachment = bool(file_cell and file_cell.find('a'))

            # Generate unique ID
            post_id = hashlib.md5(url.encode()).hexdigest()[:12]

            posts.append(MoHAPost(
                id=post_id,
                title=title,
                url=url,
                date_bs=date_bs,
                category=category,
                has_attachment=has_attachment,
            ))

        return posts

    def _get_pagination_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract pagination information from the page."""
        info = {
            'current_page': 1,
            'total_pages': 1,
            'next_url': None,
            'page_urls': [],
        }

        # Look for Livewire pagination or standard pagination
        pagination = soup.find('nav', {'aria-label': 'Pagination Navigation'}) or \
                     soup.find('ul', class_=re.compile(r'pagination', re.I)) or \
                     soup.find('div', class_=re.compile(r'pagination', re.I))

        if not pagination:
            return info

        # Find all page links
        page_links = pagination.find_all('a', href=True)

        # Extract page numbers
        for link in page_links:
            text = link.get_text(strip=True)
            if text.isdigit():
                page_num = int(text)
                info['total_pages'] = max(info['total_pages'], page_num)

        # Find current page
        active = pagination.find('span', class_=re.compile(r'current|active', re.I)) or \
                 pagination.find('li', class_=re.compile(r'active', re.I))
        if active:
            text = active.get_text(strip=True)
            if text.isdigit():
                info['current_page'] = int(text)

        # Find next page link
        next_link = pagination.find('a', {'rel': 'next'}) or \
                    pagination.find('a', string=re.compile(r'next|»|>', re.I))
        if next_link:
            next_url = next_link.get('href', '')
            if next_url and not next_url.startswith('http'):
                next_url = f"{self.BASE_URL}{next_url}"
            info['next_url'] = next_url if next_url else None

        return info

    def scrape_category(
        self,
        category: str = 'press-release-en',
        max_pages: int = 10,
    ) -> List[MoHAPost]:
        """
        Scrape all posts from a category.

        Args:
            category: Category key (see PAGES dict)
            max_pages: Maximum pages to scrape

        Returns:
            List of MoHAPost objects
        """
        if category not in self.PAGES:
            raise ValueError(f"Unknown category: {category}. Valid: {list(self.PAGES.keys())}")

        base_url = f"{self.BASE_URL}{self.PAGES[category]}"
        all_posts = []
        current_url = base_url

        for page_num in range(1, max_pages + 1):
            logger.info(f"Scraping {category} page {page_num}: {current_url}")

            soup = self._fetch_page(current_url)
            if not soup:
                logger.error(f"Failed to fetch page {page_num}")
                break

            # Parse posts from this page
            posts = self._parse_table_posts(soup, category)
            if not posts:
                logger.info(f"No posts found on page {page_num}, stopping")
                break

            all_posts.extend(posts)
            logger.info(f"Found {len(posts)} posts on page {page_num}")

            # Get pagination info
            pagination = self._get_pagination_info(soup)

            # Check if there's a next page
            if pagination['next_url']:
                current_url = pagination['next_url']
            elif page_num < pagination['total_pages']:
                # Try constructing page URL (common pattern)
                current_url = f"{base_url}?page={page_num + 1}"
            else:
                logger.info("Reached last page")
                break

        # Deduplicate by URL
        seen_urls = set()
        unique_posts = []
        for post in all_posts:
            if post.url not in seen_urls:
                seen_urls.add(post.url)
                unique_posts.append(post)

        logger.info(f"Total unique posts from {category}: {len(unique_posts)}")
        return unique_posts

    def scrape_all_categories(
        self,
        categories: List[str] = None,
        max_pages_per_category: int = 5,
    ) -> Dict[str, List[MoHAPost]]:
        """
        Scrape multiple categories.

        Args:
            categories: List of category keys (defaults to all English categories)
            max_pages_per_category: Max pages per category

        Returns:
            Dict mapping category to list of posts
        """
        if categories is None:
            categories = ['press-release-en', 'notice-en', 'circular-en']

        results = {}
        for category in categories:
            try:
                posts = self.scrape_category(category, max_pages=max_pages_per_category)
                results[category] = posts
            except Exception as e:
                logger.error(f"Error scraping {category}: {e}")
                results[category] = []

        return results

    def get_post_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full details for a single post.

        Args:
            url: URL of the post

        Returns:
            Dict with post details including full content
        """
        soup = self._fetch_page(url)
        if not soup:
            return None

        detail = {
            'url': url,
            'title': None,
            'content': None,
            'date': None,
            'attachments': [],
        }

        # Extract title
        title_el = soup.find('h1') or soup.find('h2', class_=re.compile(r'title', re.I))
        if title_el:
            detail['title'] = title_el.get_text(strip=True)

        # Extract content
        content_el = soup.find('div', class_=re.compile(r'content|body|article', re.I)) or \
                     soup.find('article')
        if content_el:
            detail['content'] = content_el.get_text(strip=True)

        # Extract attachments
        for link in soup.find_all('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)):
            href = link['href']
            if not href.startswith('http'):
                href = f"{self.BASE_URL}{href}"
            detail['attachments'].append({
                'name': link.get_text(strip=True) or href.split('/')[-1],
                'url': href,
            })

        return detail

    def export_json(self, posts: List[MoHAPost], filepath: str):
        """Export posts to JSON file."""
        import json

        data = {
            'source': 'moha.gov.np',
            'scraped_at': datetime.utcnow().isoformat(),
            'count': len(posts),
            'posts': [asdict(p) for p in posts]
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported {len(posts)} posts to {filepath}")


# ============ Async wrapper for FastAPI ============

async def fetch_moha_posts_async(
    category: str = 'press-release-en',
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """
    Async wrapper for MoHA scraping.

    For use in FastAPI endpoints - runs sync code in executor.
    """
    import asyncio

    def _scrape():
        scraper = MoHAScraper(delay=0.5, verify_ssl=False)
        posts = scraper.scrape_category(category, max_pages=max_pages)
        return [asdict(p) for p in posts]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


async def fetch_all_moha_categories_async(
    categories: List[str] = None,
    max_pages: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Async wrapper to fetch all categories.
    """
    import asyncio

    if categories is None:
        categories = ['press-release-en', 'notice-en', 'circular-en']

    def _scrape():
        scraper = MoHAScraper(delay=0.5, verify_ssl=False)
        results = scraper.scrape_all_categories(categories, max_pages_per_category=max_pages)
        return {cat: [asdict(p) for p in posts] for cat, posts in results.items()}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


# ============ CLI ============

def main():
    print("=" * 60)
    print("MoHA (Ministry of Home Affairs) Nepal Scraper")
    print("=" * 60)
    print("\nSupported categories:")
    for key in MoHAScraper.PAGES:
        print(f"  - {key}")
    print()

    scraper = MoHAScraper(delay=0.5, verify_ssl=False)

    print("[1] Scraping press-release-en (page 1)...")
    posts = scraper.scrape_category('press-release-en', max_pages=1)

    print(f"\nFound {len(posts)} posts:")
    print("-" * 60)

    for i, post in enumerate(posts[:10], 1):
        print(f"[{i}] {post.title[:60]}")
        print(f"    Date (BS): {post.date_bs}")
        print(f"    URL: {post.url}")
        print(f"    Attachment: {'Yes' if post.has_attachment else 'No'}")
        print()

    if len(posts) > 10:
        print(f"... and {len(posts) - 10} more")

    print("=" * 60)
    print("\nUsage example:")
    print("""
from app.ingestion.moha_scraper import MoHAScraper, fetch_moha_posts_async

# Sync usage
scraper = MoHAScraper()
posts = scraper.scrape_category('press-release-en', max_pages=5)

# Get all categories
results = scraper.scrape_all_categories()

# Get post details
detail = scraper.get_post_detail(posts[0].url)

# Export to JSON
scraper.export_json(posts, 'moha_data.json')

# Async usage (for FastAPI)
posts = await fetch_moha_posts_async('press-release-en', max_pages=3)
""")


if __name__ == "__main__":
    main()
