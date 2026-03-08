#!/usr/bin/env python3
"""
OPMCM (Office of the Prime Minister and Council of Ministers) Nepal Scraper

Scrapes press releases, cabinet decisions, and notices from opmcm.gov.np
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

# Nepali month names to numbers
NEPALI_MONTHS = {
    'बैशाख': '01', 'जेठ': '02', 'असार': '03', 'श्रावण': '04', 'साउन': '04',
    'भदौ': '05', 'भाद्र': '05', 'असोज': '06', 'आश्विन': '06',
    'कार्तिक': '07', 'मंसिर': '08', 'मङ्सिर': '08',
    'पुष': '09', 'पौष': '09', 'माघ': '10',
    'फागुन': '11', 'फाल्गुन': '11', 'चैत्र': '12', 'चैत': '12',
}

# Nepali digits to Arabic
NEPALI_DIGITS = {
    '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
    '५': '5', '६': '6', '७': '7', '८': '8', '९': '9',
}


def nepali_to_arabic(text: str) -> str:
    """Convert Nepali digits to Arabic digits."""
    for nep, ara in NEPALI_DIGITS.items():
        text = text.replace(nep, ara)
    return text


def parse_nepali_date(date_str: str) -> Optional[str]:
    """
    Parse Nepali date string to BS format (YYYY-MM-DD).

    Handles formats like:
    - "पुष २३, २०८२, बुधबार १५:४१"
    - "२०८२-०९-२३"
    - "मंसिर १५, २०८२"
    """
    if not date_str:
        return None

    # Convert Nepali digits
    date_str = nepali_to_arabic(date_str.strip())

    # Try standard format: YYYY-MM-DD
    match = re.search(r'(20\d{2})-(\d{2})-(\d{2})', date_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    # Try Nepali month name format: "पुष २३, २०८२"
    for month_ne, month_num in NEPALI_MONTHS.items():
        if month_ne in date_str:
            # Extract day and year
            numbers = re.findall(r'\d+', date_str)
            if len(numbers) >= 2:
                day = numbers[0].zfill(2)
                year = numbers[1] if len(numbers[1]) == 4 else numbers[-1]
                if len(year) == 4 and year.startswith('20'):
                    return f"{year}-{month_num}-{day}"

    return None


@dataclass
class OPMCMPost:
    """Structured data for an OPMCM post/notice"""
    id: str
    title: str
    url: str
    date_bs: Optional[str] = None
    date: Optional[str] = None
    category: str = "press-release"
    has_attachment: bool = False
    source: str = "opmcm.gov.np"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class OPMCMScraper:
    """
    Scraper for Office of the Prime Minister and Council of Ministers website.

    Supported categories:
    - press-release: Press releases
    - cabinet-decision: Cabinet decisions
    - cabinet-committee-decision: Cabinet committee decisions
    - highlights: Important highlights
    """

    BASE_URL = "https://opmcm.gov.np"

    # Category URL patterns
    PAGES = {
        'press-release': '/category/press-release/',
        'cabinet-decision': '/category/cabinet-decision/',
        'cabinet-committee-decision': '/category/cabinet-comitte-decision/',
        'highlights': '/category/highlights-content/',
    }

    def __init__(self, delay: float = 0.5, verify_ssl: bool = False):
        """
        Initialize the scraper.

        Args:
            delay: Delay between requests in seconds
            verify_ssl: Whether to verify SSL certificates
        """
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ne,en-US,en;q=0.9',
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

    def _parse_card_posts(self, soup: BeautifulSoup, category: str) -> List[OPMCMPost]:
        """Parse posts from card/grid layout (press releases, highlights)."""
        posts = []

        # Look for grid cards
        cards = soup.find_all('div', class_=re.compile(r'grid__card|card', re.I))

        for card in cards:
            # Find the title/link
            link = card.find('a', href=True)
            if not link:
                continue

            # Get title - try multiple possible elements
            title_el = card.find(class_=re.compile(r'card__title|title', re.I))
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

            if not title or len(title) < 5:
                continue

            # Build URL - clean whitespace/newlines from href
            url = ' '.join(link['href'].split()).strip()
            if not url.startswith('http'):
                url = f"{self.BASE_URL}{url}"

            # Extract date
            date_bs = None
            date_el = card.find(class_=re.compile(r'date|post[-_]?meta', re.I))
            if date_el:
                date_bs = parse_nepali_date(date_el.get_text())

            # Check for attachments
            has_attachment = bool(card.find('a', href=re.compile(r'\.(pdf|doc|docx)$', re.I)))

            # Generate unique ID
            post_id = hashlib.md5(url.encode()).hexdigest()[:12]

            posts.append(OPMCMPost(
                id=post_id,
                title=title,
                url=url,
                date_bs=date_bs,
                category=category,
                has_attachment=has_attachment,
            ))

        return posts

    def _parse_table_posts(self, soup: BeautifulSoup, category: str) -> List[OPMCMPost]:
        """Parse posts from table layout (cabinet decisions)."""
        posts = []

        # Find org-table or standard table
        table = soup.find('table', class_=re.compile(r'org-table', re.I)) or soup.find('table')
        if not table:
            return posts

        tbody = table.find('tbody') or table

        for row in tbody.find_all('tr'):
            cells = row.find_all('td')
            if not cells or len(cells) < 2:
                continue

            # Find the main link
            link = row.find('a', href=True)
            if not link:
                continue

            # Extract title
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Build URL - clean whitespace/newlines from href
            url = ' '.join(link['href'].split()).strip()
            if not url.startswith('http'):
                url = f"{self.BASE_URL}{url}"

            # Extract date (usually in date column)
            date_bs = None
            for cell in cells:
                text = cell.get_text(strip=True)
                parsed_date = parse_nepali_date(text)
                if parsed_date:
                    date_bs = parsed_date
                    break

            # Check for file attachments
            has_attachment = bool(row.find('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)))

            # Also check for download links
            if not has_attachment:
                download_cell = row.find('td', class_=re.compile(r'file|download', re.I))
                has_attachment = bool(download_cell and download_cell.find('a'))

            # Generate unique ID
            post_id = hashlib.md5(url.encode()).hexdigest()[:12]

            posts.append(OPMCMPost(
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
        }

        # Look for pagination
        pagination = soup.find('div', class_=re.compile(r'pagination', re.I)) or \
                     soup.find('nav', class_=re.compile(r'pagination', re.I))

        if not pagination:
            return info

        # Find all page buttons
        buttons = pagination.find_all(['a', 'button'], class_=re.compile(r'pagination__btn|page', re.I))

        for btn in buttons:
            text = btn.get_text(strip=True)
            if text.isdigit():
                page_num = int(text)
                info['total_pages'] = max(info['total_pages'], page_num)

            # Check for active page
            if 'active' in btn.get('class', []) or btn.name == 'span':
                if text.isdigit():
                    info['current_page'] = int(text)

        # Find next link
        next_btn = pagination.find(['a', 'button'], string=re.compile(r'next|›|»', re.I))
        if next_btn and next_btn.get('href'):
            info['next_url'] = next_btn['href']
            if not info['next_url'].startswith('http'):
                info['next_url'] = f"{self.BASE_URL}{info['next_url']}"

        return info

    def scrape_category(
        self,
        category: str = 'press-release',
        max_pages: int = 10,
    ) -> List[OPMCMPost]:
        """
        Scrape all posts from a category.

        Args:
            category: Category key (see PAGES dict)
            max_pages: Maximum pages to scrape

        Returns:
            List of OPMCMPost objects
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

            # Try table layout first (cabinet decisions), then card layout
            posts = self._parse_table_posts(soup, category)
            if not posts:
                posts = self._parse_card_posts(soup, category)

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
                # Try constructing page URL
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
    ) -> Dict[str, List[OPMCMPost]]:
        """
        Scrape multiple categories.

        Args:
            categories: List of category keys (defaults to main categories)
            max_pages_per_category: Max pages per category

        Returns:
            Dict mapping category to list of posts
        """
        if categories is None:
            categories = ['press-release', 'cabinet-decision']

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
        content_el = soup.find('div', class_=re.compile(r'content|body|article|detail', re.I)) or \
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


# ============ Async wrapper for FastAPI ============

async def fetch_opmcm_posts_async(
    category: str = 'press-release',
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """
    Async wrapper for OPMCM scraping.

    For use in FastAPI endpoints - runs sync code in executor.
    """
    import asyncio

    def _scrape():
        scraper = OPMCMScraper(delay=0.5, verify_ssl=False)
        posts = scraper.scrape_category(category, max_pages=max_pages)
        return [asdict(p) for p in posts]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


async def fetch_all_opmcm_categories_async(
    categories: List[str] = None,
    max_pages: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Async wrapper to fetch all categories.
    """
    import asyncio

    if categories is None:
        categories = ['press-release', 'cabinet-decision']

    def _scrape():
        scraper = OPMCMScraper(delay=0.5, verify_ssl=False)
        results = scraper.scrape_all_categories(categories, max_pages_per_category=max_pages)
        return {cat: [asdict(p) for p in posts] for cat, posts in results.items()}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


# ============ CLI ============

def main():
    print("=" * 60)
    print("OPMCM (Prime Minister's Office) Nepal Scraper")
    print("=" * 60)
    print("\nSupported categories:")
    for key in OPMCMScraper.PAGES:
        print(f"  - {key}")
    print()

    scraper = OPMCMScraper(delay=0.5, verify_ssl=False)

    print("[1] Scraping press-release (page 1)...")
    posts = scraper.scrape_category('press-release', max_pages=1)

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


if __name__ == "__main__":
    main()
