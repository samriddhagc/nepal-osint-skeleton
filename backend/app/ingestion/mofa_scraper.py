#!/usr/bin/env python3
"""
MoFA (Ministry of Foreign Affairs) Nepal Scraper

Scrapes press releases and news from mofa.gov.np
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

# Month name to number mapping (English)
MONTH_MAP = {
    'january': '01', 'february': '02', 'march': '03', 'april': '04',
    'may': '05', 'june': '06', 'july': '07', 'august': '08',
    'september': '09', 'october': '10', 'november': '11', 'december': '12',
}

# Nepali month names to number mapping (for BS dates)
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


def parse_mofa_date(date_str: str) -> tuple[Optional[str], bool]:
    """
    Parse MOFA date string to ISO format (YYYY-MM-DD).

    Handles formats like:
    - "January 16, 2026, 03:10 PM" (English AD date)
    - "16 January 2026" (English AD date)
    - "२ माघ, २०८२" (Nepali BS date - returns BS date)

    Returns:
        Tuple of (date_string, is_bs) where is_bs indicates if it's a BS date
    """
    if not date_str:
        return None, False

    original_str = date_str.strip()
    date_str = original_str.lower()

    # Try English "Month DD, YYYY" format (AD date)
    match = re.search(r'([a-z]+)\s+(\d{1,2}),?\s+(\d{4})', date_str)
    if match:
        month_name = match.group(1)
        day = match.group(2).zfill(2)
        year = match.group(3)
        month = MONTH_MAP.get(month_name)
        if month:
            return f"{year}-{month}-{day}", False  # AD date

    # Try English "DD Month YYYY" format (AD date)
    match = re.search(r'(\d{1,2})\s+([a-z]+)\s+(\d{4})', date_str)
    if match:
        day = match.group(1).zfill(2)
        month_name = match.group(2)
        year = match.group(3)
        month = MONTH_MAP.get(month_name)
        if month:
            return f"{year}-{month}-{day}", False  # AD date

    # Try Nepali BS date format: "२ माघ, २०८२" or "माघ २, २०८२"
    for month_ne, month_num in NEPALI_MONTHS.items():
        if month_ne in original_str:
            # Convert Nepali digits to Arabic
            converted = nepali_to_arabic(original_str)
            # Extract day and year
            numbers = re.findall(r'\d+', converted)
            if len(numbers) >= 2:
                # First number is usually day, last is year
                day = numbers[0].zfill(2)
                year = numbers[-1] if len(numbers[-1]) == 4 else numbers[1]
                if len(year) == 4 and year.startswith('20'):
                    return f"{year}-{month_num}-{day}", True  # BS date

    return None, False


@dataclass
class MoFAPost:
    """Structured data for a MoFA post/news"""
    id: str
    title: str
    url: str
    date_bs: Optional[str] = None  # Bikram Sambat date (YYYY-MM-DD format)
    date_ad: Optional[datetime] = None  # Gregorian datetime
    category: str = "press-release"
    has_attachment: bool = False
    source: str = "mofa.gov.np"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class MoFAScraper:
    """
    Scraper for Ministry of Foreign Affairs Nepal website.

    Supported categories:
    - press-release: Press releases/news
    """

    BASE_URL = "https://mofa.gov.np"

    # Page URL patterns
    PAGES = {
        'press-release': '/category/presscategory/',
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
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

    def _parse_card_posts(self, soup: BeautifulSoup, category: str) -> List[MoFAPost]:
        """Parse posts from card-based grid layout."""
        posts = []

        # Find all grid cards - MOFA uses grid__card class
        cards = soup.find_all('div', class_=re.compile(r'grid__card', re.I))

        for card in cards:
            # Find the title/link - check multiple possible locations
            link = None
            title = None

            # Try card__details h3 a first
            details = card.find('div', class_='card__details')
            if details:
                h3 = details.find('h3')
                if h3:
                    link = h3.find('a', href=True)
                    if link:
                        title = link.get_text(strip=True)

            # Fallback to card__title
            if not link:
                title_el = card.find(class_=re.compile(r'card__title', re.I))
                if title_el:
                    link = title_el.find('a', href=True) or title_el.parent.find('a', href=True)
                    title = title_el.get_text(strip=True)

            # Fallback to any link in card
            if not link:
                link = card.find('a', href=True)
                if link:
                    title = link.get_text(strip=True)

            if not link or not title:
                continue

            # Skip very short titles (likely navigation)
            if len(title) < 10:
                continue

            # Build URL - clean whitespace/newlines from href
            url = ' '.join(link['href'].split()).strip()
            if not url.startswith('http'):
                url = f"{self.BASE_URL}{url}"

            # Extract date from post__meta or post__date
            parsed_date = None
            is_bs_date = False

            # Try .post__meta .post__date structure first (MOFA uses "meta post__date" as class)
            meta = card.find('div', class_='post__meta')
            if meta:
                # Look for post__date class (div has classes "meta post__date")
                date_div = meta.find(class_=re.compile(r'post__date', re.I))
                if date_div:
                    # Try p element inside
                    p = date_div.find('p')
                    date_text = p.get_text(strip=True) if p else date_div.get_text(strip=True)
                    parsed_date, is_bs_date = parse_mofa_date(date_text)

            # Fallback: try direct post__date class
            if not parsed_date:
                date_el = card.find(class_=re.compile(r'post__date', re.I))
                if date_el:
                    p = date_el.find('p')
                    date_text = p.get_text(strip=True) if p else date_el.get_text(strip=True)
                    parsed_date, is_bs_date = parse_mofa_date(date_text)

            # Fallback: search for any date-like text in card
            if not parsed_date:
                card_text = card.get_text()
                parsed_date, is_bs_date = parse_mofa_date(card_text)

            # Set date_bs or date_ad based on the parsed date type
            date_bs = None
            date_ad = None
            if parsed_date:
                if is_bs_date:
                    date_bs = parsed_date
                else:
                    # Convert AD date string to datetime
                    try:
                        date_ad = datetime.strptime(parsed_date, "%Y-%m-%d")
                    except ValueError:
                        pass

            # Generate unique ID from URL
            post_id = hashlib.md5(url.encode()).hexdigest()[:12]

            posts.append(MoFAPost(
                id=post_id,
                title=title,
                url=url,
                date_bs=date_bs,
                date_ad=date_ad,
                category=category,
                has_attachment=False,
            ))

        return posts

    def _get_pagination_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract pagination information from the page."""
        info = {
            'current_page': 1,
            'total_pages': 1,
            'next_url': None,
        }

        # Find pagination container
        pagination = soup.find('div', class_=re.compile(r'pagination', re.I))
        if not pagination:
            return info

        # Find all page buttons
        buttons = pagination.find_all(['button', 'a'], class_=re.compile(r'pagination__btn', re.I))

        for btn in buttons:
            text = btn.get_text(strip=True)
            if text.isdigit():
                page_num = int(text)
                info['total_pages'] = max(info['total_pages'], page_num)

                # Check if this is active
                classes = btn.get('class', [])
                if 'active' in classes or any('active' in c for c in classes):
                    info['current_page'] = page_num

        # Find next button (might be text or icon)
        next_btns = pagination.find_all(['button', 'a'], class_=re.compile(r'pagination__btn', re.I))
        for btn in next_btns:
            # Check if it's a "next" button by position or text
            text = btn.get_text(strip=True).lower()
            if text in ['next', '›', '»', '>']:
                href = btn.get('href')
                if href:
                    if not href.startswith('http'):
                        href = f"{self.BASE_URL}{href}"
                    info['next_url'] = href

        return info

    def scrape_category(
        self,
        category: str = 'press-release',
        max_pages: int = 10,
    ) -> List[MoFAPost]:
        """
        Scrape all posts from a category.

        Args:
            category: Category key (see PAGES dict)
            max_pages: Maximum pages to scrape

        Returns:
            List of MoFAPost objects
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
                current_url = f"{base_url}page/{page_num + 1}/"
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
    ) -> Dict[str, List[MoFAPost]]:
        """
        Scrape multiple categories.

        Args:
            categories: List of category keys (defaults to press-release)
            max_pages_per_category: Max pages per category

        Returns:
            Dict mapping category to list of posts
        """
        if categories is None:
            categories = ['press-release']

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
        content_el = soup.find('div', class_=re.compile(r'content|body|article|single', re.I)) or \
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

async def fetch_mofa_posts_async(
    category: str = 'press-release',
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """
    Async wrapper for MoFA scraping.

    For use in FastAPI endpoints - runs sync code in executor.
    """
    import asyncio

    def _scrape():
        scraper = MoFAScraper(delay=0.5, verify_ssl=False)
        posts = scraper.scrape_category(category, max_pages=max_pages)
        return [asdict(p) for p in posts]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


async def fetch_all_mofa_categories_async(
    categories: List[str] = None,
    max_pages: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Async wrapper to fetch all categories.
    """
    import asyncio

    if categories is None:
        categories = ['press-release']

    def _scrape():
        scraper = MoFAScraper(delay=0.5, verify_ssl=False)
        results = scraper.scrape_all_categories(categories, max_pages_per_category=max_pages)
        return {cat: [asdict(p) for p in posts] for cat, posts in results.items()}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


# ============ CLI ============

def main():
    print("=" * 60)
    print("MoFA (Ministry of Foreign Affairs) Nepal Scraper")
    print("=" * 60)
    print("\nSupported categories:")
    for key in MoFAScraper.PAGES:
        print(f"  - {key}")
    print()

    scraper = MoFAScraper(delay=0.5, verify_ssl=False)

    print("[1] Scraping press-release (page 1)...")
    posts = scraper.scrape_category('press-release', max_pages=1)

    print(f"\nFound {len(posts)} posts:")
    print("-" * 60)

    for i, post in enumerate(posts[:10], 1):
        print(f"[{i}] {post.title[:60]}")
        print(f"    Date: {post.date}")
        print(f"    URL: {post.url}")
        print()

    if len(posts) > 10:
        print(f"... and {len(posts) - 10} more")

    print("=" * 60)


if __name__ == "__main__":
    main()
