#!/usr/bin/env python3
"""
Generic Ministry Scraper for Nepal Government Websites

Most Nepal government ministry websites follow a similar structure using /category/ URLs.
This generic scraper handles the common patterns and can be configured
for any ministry or government department.

URL Patterns:
- Category listings: /category/press-release/, /category/notice/, /category/news/
- Individual posts: /content/{id}/{slug}/
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
import asyncio

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class GovtPost:
    """Generic government post structure."""
    id: str
    title: str
    url: str
    source_id: str
    source_name: str
    source_domain: str
    date_bs: Optional[str] = None
    date_ad: Optional[datetime] = None
    category: str = "press-release"
    language: str = "en"
    has_attachment: bool = False
    attachment_urls: List[str] = field(default_factory=list)
    content_snippet: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class GenericMinistryScraperConfig:
    """Configuration for a ministry scraper."""
    source_id: str
    name: str
    name_ne: str
    base_url: str
    endpoints: Dict[str, str]
    page_structure: str = "category"  # category, table, list, card
    date_selector: Optional[str] = None
    title_selector: Optional[str] = None
    pagination_type: str = "standard"  # standard, livewire, ajax
    priority: int = 2  # 1=high, 2=medium, 3=low
    poll_interval_mins: int = 60


class GenericMinistryScraper:
    """
    Generic scraper for Nepal government ministry websites.

    Handles common patterns:
    - Category-based listings (/category/press-release/)
    - Content links (/content/{id}/)
    - Table-based layouts
    - Card-based layouts
    - Standard pagination (?page=N)
    """

    # Common selectors across govt sites
    TABLE_SELECTORS = ['table.table', 'table', '.table-responsive table']
    LIST_SELECTORS = ['.news-list', '.notice-list', 'ul.list-group', '.post-list']
    CARD_SELECTORS = ['.card', '.news-card', '.post-card', '.content-card']

    # Nepali digit conversion
    NEPALI_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')

    def __init__(self, config: GenericMinistryScraperConfig, delay: float = 0.5):
        self.config = config
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ne;q=0.8',
        })
        self.session.verify = False  # Nepal govt SSL issues

    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a page."""
        try:
            import time
            time.sleep(self.delay)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def _convert_nepali_digits(self, text: str) -> str:
        """Convert Nepali digits to Arabic."""
        return text.translate(self.NEPALI_DIGITS)

    def _extract_bs_date(self, text: str) -> Optional[str]:
        """Extract BS date from text."""
        if not text:
            return None
        text = self._convert_nepali_digits(text)
        # Match YYYY-MM-DD where year starts with 20 (BS years 2000+)
        match = re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})', text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return None

    def _parse_category_posts(self, soup: BeautifulSoup, category: str, language: str) -> List[GovtPost]:
        """Parse posts from category listing page (most common format)."""
        posts = []

        # Find all content links (/content/{id}/)
        content_links = soup.find_all('a', href=re.compile(r'/content/\d+/'))

        seen_urls = set()
        for link in content_links:
            url = link['href']
            if not url.startswith('http'):
                url = f"{self.config.base_url}{url}"

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Get title from link text or parent
            title = link.get_text(strip=True)

            # Sometimes title is in a parent or sibling element
            if not title or len(title) < 5:
                parent = link.find_parent(['div', 'li', 'article', 'h2', 'h3', 'h4'])
                if parent:
                    title_el = parent.find(['h2', 'h3', 'h4', 'h5', '.title', '.post-title'])
                    if title_el:
                        title = title_el.get_text(strip=True)
                    else:
                        title = parent.get_text(strip=True)[:150]

            # Clean title
            title = re.sub(r'\d+\s*(month|day|week|year|hour|minute)s?\s*ago\s*$', '', title, flags=re.I).strip()
            title = re.sub(r'\s+', ' ', title)

            if not title or len(title) < 5:
                continue

            # Limit title length
            if len(title) > 200:
                title = title[:197] + '...'

            # Try to find date
            date_bs = None
            parent = link.find_parent(['div', 'li', 'article', 'tr'])
            if parent:
                # Look for date in various places
                date_text = parent.get_text()
                date_bs = self._extract_bs_date(date_text)

            # Check for attachments
            has_attachment = False
            if parent:
                has_attachment = bool(parent.find('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)))

            post_id = hashlib.md5(f"{self.config.source_id}:{url}".encode()).hexdigest()[:12]

            posts.append(GovtPost(
                id=post_id,
                title=title,
                url=url,
                source_id=self.config.source_id,
                source_name=self.config.name,
                source_domain=self.config.base_url.replace('https://', '').replace('http://', ''),
                date_bs=date_bs,
                category=category,
                language=language,
                has_attachment=has_attachment,
            ))

        return posts

    def _parse_table_posts(self, soup: BeautifulSoup, category: str, language: str) -> List[GovtPost]:
        """Parse posts from table layout."""
        posts = []

        table = None
        for selector in self.TABLE_SELECTORS:
            table = soup.select_one(selector)
            if table:
                break

        if not table:
            return posts

        tbody = table.find('tbody') or table

        for row in tbody.find_all('tr'):
            link = row.find('a', href=True)
            if not link:
                continue

            title = link.get_text(strip=True)
            title = re.sub(r'\d+\s*(month|day|week|year|hour|minute)s?\s*ago\s*$', '', title, flags=re.I).strip()

            if not title or len(title) < 5:
                continue

            url = link['href']
            if not url.startswith('http'):
                url = f"{self.config.base_url}{url}"

            date_bs = None
            for cell in row.find_all('td'):
                date_bs = self._extract_bs_date(cell.get_text())
                if date_bs:
                    break

            has_attachment = bool(row.find('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)))

            post_id = hashlib.md5(f"{self.config.source_id}:{url}".encode()).hexdigest()[:12]

            posts.append(GovtPost(
                id=post_id,
                title=title,
                url=url,
                source_id=self.config.source_id,
                source_name=self.config.name,
                source_domain=self.config.base_url.replace('https://', '').replace('http://', ''),
                date_bs=date_bs,
                category=category,
                language=language,
                has_attachment=has_attachment,
            ))

        return posts

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str, page_num: int) -> Optional[str]:
        """Find next page URL."""
        # Try rel="next" link
        next_link = soup.find('a', {'rel': 'next'})
        if next_link and next_link.get('href'):
            href = next_link['href']
            if not href.startswith('http'):
                href = f"{self.config.base_url}{href}"
            return href

        # Try pagination with page number
        pagination = soup.find('nav', {'aria-label': re.compile(r'pagination', re.I)}) or \
                     soup.find('ul', class_=re.compile(r'pagination', re.I)) or \
                     soup.find('div', class_=re.compile(r'pagination', re.I))

        if pagination:
            next_page = pagination.find('a', string=str(page_num + 1))
            if not next_page:
                next_page = pagination.find('a', string=re.compile(f'^{page_num + 1}$'))
            if next_page and next_page.get('href'):
                href = next_page['href']
                if not href.startswith('http'):
                    href = f"{self.config.base_url}{href}"
                return href

        # Try query param pattern
        base = current_url.split('?')[0]
        return f"{base}?page={page_num + 1}"

    def scrape_endpoint(self, endpoint_key: str, max_pages: int = 5) -> List[GovtPost]:
        """Scrape a specific endpoint."""
        if endpoint_key not in self.config.endpoints:
            raise ValueError(f"Unknown endpoint: {endpoint_key}")

        endpoint = self.config.endpoints[endpoint_key]
        language = "ne" if endpoint_key.endswith("_ne") or "_ne" in endpoint_key else "en"
        category = endpoint_key.replace("_en", "").replace("_ne", "").replace("-", "_")

        url = f"{self.config.base_url}{endpoint}"
        all_posts = []

        for page_num in range(1, max_pages + 1):
            logger.info(f"Scraping {self.config.source_id} {endpoint_key} page {page_num}")

            soup = self._fetch_page(url)
            if not soup:
                break

            # Parse based on page structure
            if self.config.page_structure == "table":
                posts = self._parse_table_posts(soup, category, language)
            else:
                # Default to category parsing (most common)
                posts = self._parse_category_posts(soup, category, language)

            # Fallback to table if no posts found
            if not posts:
                posts = self._parse_table_posts(soup, category, language)

            if not posts:
                logger.info(f"No posts found on page {page_num}, stopping")
                break

            all_posts.extend(posts)

            # Get next page
            next_url = self._get_next_page_url(soup, url, page_num)
            if next_url and next_url != url:
                url = next_url
            else:
                break

        # Deduplicate
        seen_urls = set()
        unique_posts = []
        for post in all_posts:
            if post.url not in seen_urls:
                seen_urls.add(post.url)
                unique_posts.append(post)

        logger.info(f"Total {self.config.source_id} {endpoint_key}: {len(unique_posts)} posts")
        return unique_posts

    def scrape_all(self, max_pages_per_endpoint: int = 3) -> Dict[str, List[GovtPost]]:
        """Scrape all configured endpoints."""
        results = {}
        for endpoint_key in self.config.endpoints:
            try:
                posts = self.scrape_endpoint(endpoint_key, max_pages=max_pages_per_endpoint)
                results[endpoint_key] = posts
            except Exception as e:
                logger.error(f"Error scraping {endpoint_key}: {e}")
                results[endpoint_key] = []
        return results


# ============ Async wrapper ============

async def scrape_ministry_async(
    config: GenericMinistryScraperConfig,
    endpoints: List[str] = None,
    max_pages: int = 3,
) -> Dict[str, List[Dict]]:
    """Async wrapper for ministry scraping."""
    def _scrape():
        scraper = GenericMinistryScraper(config)
        if endpoints:
            return {ep: [asdict(p) for p in scraper.scrape_endpoint(ep, max_pages)] for ep in endpoints if ep in config.endpoints}
        else:
            return {k: [asdict(p) for p in v] for k, v in scraper.scrape_all(max_pages).items()}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


# ============ Pre-configured ministries with CORRECT URLs ============

MINISTRY_CONFIGS = {
    # ============ Working Ministries (verified) ============
    'mof': GenericMinistryScraperConfig(
        source_id='mof',
        name='Ministry of Finance',
        name_ne='अर्थ मन्त्रालय',
        base_url='https://mof.gov.np',
        endpoints={
            'circular': '/category/circular',
        },
        page_structure='category',
        priority=1,
        poll_interval_mins=60,
    ),
    'moest': GenericMinistryScraperConfig(
        source_id='moest',
        name='Ministry of Education, Science and Technology',
        name_ne='शिक्षा, विज्ञान तथा प्रविधि मन्त्रालय',
        base_url='https://moest.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
            'news': '/category/news/',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
    'mohp': GenericMinistryScraperConfig(
        source_id='mohp',
        name='Ministry of Health and Population',
        name_ne='स्वास्थ्य तथा जनसङ्ख्या मन्त्रालय',
        base_url='https://mohp.gov.np',
        endpoints={
            'press_release': '/category/pressrelease',
        },
        page_structure='category',
        priority=1,
        poll_interval_mins=60,
    ),
    'mod': GenericMinistryScraperConfig(
        source_id='mod',
        name='Ministry of Defence',
        name_ne='रक्षा मन्त्रालय',
        base_url='https://mod.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
            'news': '/category/news/',
        },
        page_structure='category',
        priority=1,
        poll_interval_mins=60,
    ),
    'moald': GenericMinistryScraperConfig(
        source_id='moald',
        name='Ministry of Agriculture and Livestock Development',
        name_ne='कृषि तथा पशुपन्छी विकास मन्त्रालय',
        base_url='https://moald.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
    'moics': GenericMinistryScraperConfig(
        source_id='moics',
        name='Ministry of Industry, Commerce and Supplies',
        name_ne='उद्योग, वाणिज्य तथा आपूर्ति मन्त्रालय',
        base_url='https://moics.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
            'news': '/category/news/',
            'circular': '/category/circular',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
    'moewri': GenericMinistryScraperConfig(
        source_id='moewri',
        name='Ministry of Energy, Water Resources and Irrigation',
        name_ne='ऊर्जा, जलस्रोत तथा सिँचाइ मन्त्रालय',
        base_url='https://moewri.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
    'mocit': GenericMinistryScraperConfig(
        source_id='mocit',
        name='Ministry of Communications and Information Technology',
        name_ne='सञ्चार तथा सूचना प्रविधि मन्त्रालय',
        base_url='https://mocit.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
            'news': '/category/news/',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
    'moless': GenericMinistryScraperConfig(
        source_id='moless',
        name='Ministry of Labour, Employment and Social Security',
        name_ne='श्रम, रोजगार तथा सामाजिक सुरक्षा मन्त्रालय',
        base_url='https://moless.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
            'news': '/category/news/',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
    'mowcsc': GenericMinistryScraperConfig(
        source_id='mowcsc',
        name='Ministry of Women, Children and Senior Citizens',
        name_ne='महिला, बालबालिका तथा ज्येष्ठ नागरिक मन्त्रालय',
        base_url='https://mowcsc.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
        },
        page_structure='category',
        priority=3,
        poll_interval_mins=180,
    ),
    'mofe': GenericMinistryScraperConfig(
        source_id='mofe',
        name='Ministry of Forests and Environment',
        name_ne='वन तथा वातावरण मन्त्रालय',
        base_url='https://mofe.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'news': '/category/news/',
            'circular': '/category/circular',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
    'mopit': GenericMinistryScraperConfig(
        source_id='mopit',
        name='Ministry of Physical Infrastructure and Transport',
        name_ne='भौतिक पूर्वाधार तथा यातायात मन्त्रालय',
        base_url='https://mopit.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'news': '/category/news/',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),

    # ============ Ministries needing verification ============
    'moljpa': GenericMinistryScraperConfig(
        source_id='moljpa',
        name='Ministry of Law, Justice and Parliamentary Affairs',
        name_ne='कानून, न्याय तथा संसदीय मामिला मन्त्रालय',
        base_url='https://moljpa.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
    'mofaga': GenericMinistryScraperConfig(
        source_id='mofaga',
        name='Ministry of Federal Affairs and General Administration',
        name_ne='संघीय मामिला तथा सामान्य प्रशासन मन्त्रालय',
        base_url='https://mofaga.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
            'circular': '/category/circular',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
    'moys': GenericMinistryScraperConfig(
        source_id='moys',
        name='Ministry of Youth and Sports',
        name_ne='युवा तथा खेलकुद मन्त्रालय',
        base_url='https://moys.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
        },
        page_structure='category',
        priority=3,
        poll_interval_mins=180,
    ),
    'mowss': GenericMinistryScraperConfig(
        source_id='mowss',
        name='Ministry of Water Supply',
        name_ne='खानेपानी मन्त्रालय',
        base_url='https://mowss.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
        },
        page_structure='category',
        priority=3,
        poll_interval_mins=180,
    ),
    'mohud': GenericMinistryScraperConfig(
        source_id='mohud',
        name='Ministry of Urban Development',
        name_ne='सहरी विकास मन्त्रालय',
        base_url='https://mohud.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
    'mocta': GenericMinistryScraperConfig(
        source_id='mocta',
        name='Ministry of Culture, Tourism and Civil Aviation',
        name_ne='संस्कृति, पर्यटन तथा नागरिक उड्डयन मन्त्रालय',
        base_url='https://mocta.gov.np',
        endpoints={
            'press_release': '/category/press-release/',
            'notice': '/category/notice/',
        },
        page_structure='category',
        priority=2,
        poll_interval_mins=120,
    ),
}


def get_ministry_scraper(ministry_id: str) -> GenericMinistryScraper:
    """Factory function to get a configured ministry scraper."""
    if ministry_id not in MINISTRY_CONFIGS:
        raise ValueError(f"Unknown ministry: {ministry_id}. Available: {list(MINISTRY_CONFIGS.keys())}")
    return GenericMinistryScraper(MINISTRY_CONFIGS[ministry_id])


def add_ministry_config(config: GenericMinistryScraperConfig) -> None:
    """Add a new ministry configuration."""
    MINISTRY_CONFIGS[config.source_id] = config


# ============ CLI ============

def main():
    print("=" * 60)
    print("Generic Ministry Scraper - Nepal Government")
    print("=" * 60)
    print(f"\nConfigured ministries: {len(MINISTRY_CONFIGS)}")
    print()

    for ministry_id, config in MINISTRY_CONFIGS.items():
        print(f"  {ministry_id}: {config.name}")
        print(f"          URL: {config.base_url}")
        print(f"          Endpoints: {list(config.endpoints.keys())}")
        print()

    print("-" * 60)
    print("Testing MOEST scraper...")

    scraper = get_ministry_scraper('moest')
    posts = scraper.scrape_endpoint('press_release', max_pages=1)

    print(f"\nFound {len(posts)} posts from Ministry of Education:")
    for i, post in enumerate(posts[:5], 1):
        print(f"  [{i}] {post.title[:60]}")
        print(f"      Date: {post.date_bs}")
        print()


if __name__ == "__main__":
    main()
