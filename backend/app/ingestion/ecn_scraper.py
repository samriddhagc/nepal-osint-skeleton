#!/usr/bin/env python3
"""
ECN (Election Commission Nepal) Scraper

Scrapes press releases and notices from election.gov.np
Uses Playwright for JavaScript-rendered content.
"""

import asyncio
import hashlib
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Month name to number mapping (English)
MONTH_MAP = {
    'january': '01', 'february': '02', 'march': '03', 'april': '04',
    'may': '05', 'june': '06', 'july': '07', 'august': '08',
    'september': '09', 'october': '10', 'november': '11', 'december': '12',
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'jun': '06', 'jul': '07', 'aug': '08', 'sep': '09',
    'oct': '10', 'nov': '11', 'dec': '12',
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


def parse_ecn_date(date_str: str) -> tuple[Optional[str], Optional[datetime], bool]:
    """
    Parse ECN date string.

    Returns:
        Tuple of (date_bs, date_ad, is_bs) where:
        - date_bs is BS date string (YYYY-MM-DD) if BS date found
        - date_ad is datetime object if AD date found
        - is_bs indicates if the primary date is BS
    """
    if not date_str:
        return None, None, False

    original_str = date_str.strip()
    date_str_lower = original_str.lower()

    # Try English date formats (AD)
    # Format: "January 16, 2026" or "16 January 2026" or "2026-01-16"

    # ISO format
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str_lower)
    if match:
        try:
            date_ad = datetime.strptime(match.group(0), "%Y-%m-%d")
            return None, date_ad, False
        except ValueError:
            pass

    # "Month DD, YYYY" format
    match = re.search(r'([a-z]+)\s+(\d{1,2}),?\s+(\d{4})', date_str_lower)
    if match:
        month_name = match.group(1)
        day = match.group(2).zfill(2)
        year = match.group(3)
        month = MONTH_MAP.get(month_name)
        if month:
            try:
                date_ad = datetime(int(year), int(month), int(day))
                return None, date_ad, False
            except ValueError:
                pass

    # "DD Month YYYY" format
    match = re.search(r'(\d{1,2})\s+([a-z]+)\s+(\d{4})', date_str_lower)
    if match:
        day = match.group(1).zfill(2)
        month_name = match.group(2)
        year = match.group(3)
        month = MONTH_MAP.get(month_name)
        if month:
            try:
                date_ad = datetime(int(year), int(month), int(day))
                return None, date_ad, False
            except ValueError:
                pass

    # Try Nepali BS date format
    for month_ne, month_num in NEPALI_MONTHS.items():
        if month_ne in original_str:
            converted = nepali_to_arabic(original_str)
            numbers = re.findall(r'\d+', converted)
            if len(numbers) >= 2:
                day = numbers[0].zfill(2)
                year = numbers[-1] if len(numbers[-1]) == 4 else numbers[1]
                if len(year) == 4 and year.startswith('20'):
                    date_bs = f"{year}-{month_num}-{day}"
                    return date_bs, None, True

    return None, None, False


def extract_date_from_url(url: str) -> Optional[str]:
    """
    Extract BS date from ECN URL/filename.

    ECN often uses filenames like:
    - 2082-10-13.jpg
    - 2082-10-11 Second.jpg
    - 2082-10-11 Third Press Release.pdf

    Returns BS date string (YYYY-MM-DD) or None.
    """
    if not url:
        return None

    # Look for BS date pattern (20XX-MM-DD) in URL
    # BS years are typically 2080-2090 range currently
    match = re.search(r'(20[78]\d)-(\d{1,2})-(\d{1,2})', url)
    if match:
        year = match.group(1)
        month = match.group(2).zfill(2)
        day = match.group(3).zfill(2)
        return f"{year}-{month}-{day}"

    return None


@dataclass
class ECNPost:
    """Structured data for an ECN post/press release"""
    id: str
    title: str
    url: str
    date_bs: Optional[str] = None
    date_ad: Optional[datetime] = None
    category: str = "press-release"
    has_attachment: bool = False
    source: str = "election.gov.np"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ECNScraper:
    """
    Scraper for Election Commission Nepal website.
    Uses Playwright for JavaScript-rendered content.

    Supported categories:
    - press-release: Press releases (English)
    - press-release-ne: Press releases (Nepali)
    - notice: Notices
    """

    BASE_URL = "https://election.gov.np"

    # Page URL patterns
    PAGES = {
        'press-release': '/en/press-release',
        'press-release-ne': '/np/press-release',
        'notice': '/en/notice',
        'notice-ne': '/np/notice',
    }

    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Initialize the scraper.

        Args:
            headless: Run browser in headless mode
            timeout: Page load timeout in milliseconds
        """
        self.headless = headless
        self.timeout = timeout
        self._browser = None
        self._playwright = None

    async def __aenter__(self):
        """Async context manager entry."""
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _fetch_page_content(self, url: str) -> Optional[str]:
        """Fetch page content using Playwright."""
        if not self._browser:
            raise RuntimeError("Browser not initialized. Use 'async with' context manager.")

        page = await self._browser.new_page()
        try:
            logger.info(f"Fetching: {url}")
            await page.goto(url, timeout=self.timeout, wait_until='networkidle')

            # Wait for content to load - look for common content containers
            try:
                await page.wait_for_selector('.content, .list, table, .card, article', timeout=10000)
            except Exception:
                # Content might already be loaded
                pass

            # Give extra time for dynamic content
            await asyncio.sleep(1)

            content = await page.content()
            return content
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
        finally:
            await page.close()

    def _parse_posts_from_html(self, html: str, category: str) -> List[ECNPost]:
        """Parse posts from HTML content."""
        from bs4 import BeautifulSoup

        posts = []
        soup = BeautifulSoup(html, 'html.parser')

        # Skip patterns for navigation/UI elements
        SKIP_TITLES = [
            'quick links', 'social media', 'contact us', 'home', 'about',
            'login', 'register', 'search', 'menu', 'navigation',
            'election commission nepal', 'निर्वाचन आयोग',
        ]

        def should_skip(title: str, url: str) -> bool:
            """Check if this is a navigation link to skip."""
            title_lower = title.lower().strip()
            url_lower = url.lower()

            # Skip very short titles
            if len(title) < 15:
                return True

            # Skip known navigation patterns
            for skip in SKIP_TITLES:
                if skip in title_lower:
                    return True

            # Skip if URL is just the homepage
            if url_lower.rstrip('/') == self.BASE_URL.lower():
                return True

            # Skip external social media links
            if any(sm in url_lower for sm in ['facebook.com', 'twitter.com', 'youtube.com', 'instagram.com']):
                return True

            return False

        # Try different common patterns for listing items
        # Pattern 1: Table rows
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                # Skip header rows
                if row.find('th'):
                    continue

                cells = row.find_all('td')
                if len(cells) >= 2:
                    # Find link and title
                    link = row.find('a', href=True)
                    if link:
                        title = link.get_text(strip=True)
                        href = link['href']

                        if not title or len(title) < 5:
                            continue

                        url = href if href.startswith('http') else f"{self.BASE_URL}{href}"

                        # Skip navigation links
                        if should_skip(title, url):
                            continue

                        # Try to find date in cells
                        date_bs, date_ad = None, None
                        for cell in cells:
                            cell_text = cell.get_text(strip=True)
                            if cell_text and cell != link.parent:
                                parsed_bs, parsed_ad, _ = parse_ecn_date(cell_text)
                                if parsed_bs:
                                    date_bs = parsed_bs
                                if parsed_ad:
                                    date_ad = parsed_ad

                        # If no date found from HTML, try extracting from URL
                        if not date_bs and not date_ad:
                            date_bs = extract_date_from_url(url)

                        post_id = hashlib.md5(url.encode()).hexdigest()[:12]
                        posts.append(ECNPost(
                            id=post_id,
                            title=title,
                            url=url,
                            date_bs=date_bs,
                            date_ad=date_ad,
                            category=category,
                        ))

        # Pattern 2: Card/List items
        cards = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'card|item|post|news|list', re.I))
        for card in cards:
            link = card.find('a', href=True)
            if not link:
                continue

            # Get title from link or heading
            title_el = card.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']) or link
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

            if not title or len(title) < 5:
                continue

            href = link['href']
            url = href if href.startswith('http') else f"{self.BASE_URL}{href}"

            # Skip navigation links
            if should_skip(title, url):
                continue

            # Skip if already found from table
            if any(p.url == url for p in posts):
                continue

            # Try to find date
            date_bs, date_ad = None, None
            date_el = card.find(class_=re.compile(r'date|time|meta', re.I))
            if date_el:
                parsed_bs, parsed_ad, _ = parse_ecn_date(date_el.get_text(strip=True))
                if parsed_bs:
                    date_bs = parsed_bs
                if parsed_ad:
                    date_ad = parsed_ad

            # If no date found from HTML, try extracting from URL
            if not date_bs and not date_ad:
                date_bs = extract_date_from_url(url)

            post_id = hashlib.md5(url.encode()).hexdigest()[:12]
            posts.append(ECNPost(
                id=post_id,
                title=title,
                url=url,
                date_bs=date_bs,
                date_ad=date_ad,
                category=category,
            ))

        # Pattern 3: Simple link lists (fallback)
        if not posts:
            for link in soup.find_all('a', href=True):
                href = link['href']
                title = link.get_text(strip=True)

                # Filter out navigation links
                if not title or len(title) < 10:
                    continue
                if href.startswith('#') or href.startswith('javascript:'):
                    continue
                if any(skip in href.lower() for skip in ['login', 'logout', 'register', 'contact', 'about']):
                    continue

                url = href if href.startswith('http') else f"{self.BASE_URL}{href}"

                # Skip navigation links using should_skip
                if should_skip(title, url):
                    continue

                # Check if it looks like a press release link
                if 'press' in href.lower() or 'notice' in href.lower() or 'news' in href.lower() or '.pdf' in href.lower() or '.jpg' in href.lower():
                    if any(p.url == url for p in posts):
                        continue

                    # Try to extract date from URL
                    date_bs = extract_date_from_url(url)

                    post_id = hashlib.md5(url.encode()).hexdigest()[:12]
                    posts.append(ECNPost(
                        id=post_id,
                        title=title,
                        url=url,
                        date_bs=date_bs,
                        category=category,
                    ))

        return posts

    async def scrape_category(
        self,
        category: str = 'press-release',
        max_pages: int = 3,
    ) -> List[ECNPost]:
        """
        Scrape all posts from a category.

        Args:
            category: Category key (see PAGES dict)
            max_pages: Maximum pages to scrape

        Returns:
            List of ECNPost objects
        """
        if category not in self.PAGES:
            raise ValueError(f"Unknown category: {category}. Valid: {list(self.PAGES.keys())}")

        base_url = f"{self.BASE_URL}{self.PAGES[category]}"
        all_posts = []

        for page_num in range(1, max_pages + 1):
            # Construct page URL - try common pagination patterns
            if page_num == 1:
                url = base_url
            else:
                # Try different pagination patterns
                url = f"{base_url}?page={page_num}"

            logger.info(f"Scraping {category} page {page_num}: {url}")

            html = await self._fetch_page_content(url)
            if not html:
                logger.error(f"Failed to fetch page {page_num}")
                break

            posts = self._parse_posts_from_html(html, category)
            if not posts:
                logger.info(f"No posts found on page {page_num}, stopping")
                break

            # Check for duplicates to detect end of pagination
            new_posts = [p for p in posts if not any(ep.url == p.url for ep in all_posts)]
            if not new_posts:
                logger.info("No new posts found, stopping pagination")
                break

            all_posts.extend(new_posts)
            logger.info(f"Found {len(new_posts)} new posts on page {page_num}")

        # Deduplicate by URL
        seen_urls = set()
        unique_posts = []
        for post in all_posts:
            if post.url not in seen_urls:
                seen_urls.add(post.url)
                unique_posts.append(post)

        logger.info(f"Total unique posts from {category}: {len(unique_posts)}")
        return unique_posts

    async def scrape_all_categories(
        self,
        categories: List[str] = None,
        max_pages_per_category: int = 3,
    ) -> Dict[str, List[ECNPost]]:
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
                posts = await self.scrape_category(category, max_pages=max_pages_per_category)
                results[category] = posts
            except Exception as e:
                logger.error(f"Error scraping {category}: {e}")
                results[category] = []

        return results

    async def get_post_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full details for a single post.

        Args:
            url: URL of the post

        Returns:
            Dict with post details including full content
        """
        html = await self._fetch_page_content(url)
        if not html:
            return None

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

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
                     soup.find('article') or \
                     soup.find('main')
        if content_el:
            detail['content'] = content_el.get_text(strip=True)

        # Extract attachments (PDFs, docs)
        for link in soup.find_all('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)):
            href = link['href']
            if not href.startswith('http'):
                href = f"{self.BASE_URL}{href}"
            detail['attachments'].append({
                'name': link.get_text(strip=True) or href.split('/')[-1],
                'url': href,
            })

        return detail


# ============ Async functions for service integration ============

async def fetch_ecn_posts_async(
    category: str = 'press-release',
    max_pages: int = 3,
    headless: bool = True,
) -> List[Dict[str, Any]]:
    """
    Fetch ECN posts asynchronously.

    For use in FastAPI endpoints.
    """
    async with ECNScraper(headless=headless) as scraper:
        posts = await scraper.scrape_category(category, max_pages=max_pages)
        return [asdict(p) for p in posts]


async def fetch_all_ecn_categories_async(
    categories: List[str] = None,
    max_pages: int = 3,
    headless: bool = True,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch all ECN categories asynchronously.
    """
    if categories is None:
        categories = ['press-release']

    async with ECNScraper(headless=headless) as scraper:
        results = await scraper.scrape_all_categories(categories, max_pages_per_category=max_pages)
        return {cat: [asdict(p) for p in posts] for cat, posts in results.items()}


# ============ CLI ============

async def main():
    print("=" * 60)
    print("ECN (Election Commission Nepal) Scraper")
    print("=" * 60)
    print("\nSupported categories:")
    for key in ECNScraper.PAGES:
        print(f"  - {key}")
    print()

    print("[1] Scraping press-release (page 1)...")

    async with ECNScraper(headless=True) as scraper:
        posts = await scraper.scrape_category('press-release', max_pages=1)

        print(f"\nFound {len(posts)} posts:")
        print("-" * 60)

        for i, post in enumerate(posts[:10], 1):
            print(f"[{i}] {post.title[:60]}")
            print(f"    Date BS: {post.date_bs}")
            print(f"    Date AD: {post.date_ad}")
            print(f"    URL: {post.url}")
            print()

        if len(posts) > 10:
            print(f"... and {len(posts) - 10} more")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
