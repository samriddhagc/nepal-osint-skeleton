#!/usr/bin/env python3
"""
Constitutional Bodies and Regulatory Agencies Scraper

Scrapes announcements from Nepal's constitutional bodies including:
- CIAA (Commission for Investigation of Abuse of Authority)
- Office of the Auditor General
- Public Service Commission
- National Human Rights Commission
- Various regulatory bodies (NRB, SEBON, NTA, etc.)
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
class ConstitutionalPost:
    """Structured data for a constitutional body post."""
    id: str
    title: str
    url: str
    body_id: str
    body_name: str
    body_name_ne: str
    body_type: str  # constitutional, regulatory, judiciary
    date_bs: Optional[str] = None
    date_ad: Optional[datetime] = None
    category: str = "press-release"
    language: str = "en"
    has_attachment: bool = False
    attachment_urls: List[str] = field(default_factory=list)
    source_domain: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ConstitutionalBodyConfig:
    """Configuration for a constitutional body scraper."""
    body_id: str
    name: str
    name_ne: str
    body_type: str  # constitutional, regulatory, judiciary
    base_url: str
    endpoints: Dict[str, str]
    page_structure: str = "table"
    priority: int = 1


class ConstitutionalScraper:
    """
    Scraper for Nepal's constitutional and regulatory bodies.
    """

    BODIES: Dict[str, ConstitutionalBodyConfig] = {
        # Constitutional Bodies
        'ciaa': ConstitutionalBodyConfig(
            body_id='ciaa',
            name='Commission for Investigation of Abuse of Authority',
            name_ne='अख्तियार दुरुपयोग अनुसन्धान आयोग',
            body_type='constitutional',
            base_url='https://ciaa.gov.np',
            endpoints={
                'press_release': '/category/press-release/',
                'notice': '/category/notice/',
            },
            page_structure='category',
            priority=1,
        ),
        'oag': ConstitutionalBodyConfig(
            body_id='oag',
            name='Office of the Auditor General',
            name_ne='महालेखा परीक्षकको कार्यालय',
            body_type='constitutional',
            base_url='https://oag.gov.np',
            endpoints={
                'press_release': '/category/press-release/',
                'notice': '/category/notice/',
                'report': '/category/reports/',
            },
            page_structure='category',
            priority=1,
        ),
        'psc': ConstitutionalBodyConfig(
            body_id='psc',
            name='Public Service Commission',
            name_ne='लोक सेवा आयोग',
            body_type='constitutional',
            base_url='https://psc.gov.np',
            endpoints={
                'notice': '/category/notice/',
                'result': '/category/result/',
            },
            page_structure='category',
            priority=1,
        ),
        'nhrc': ConstitutionalBodyConfig(
            body_id='nhrc',
            name='National Human Rights Commission',
            name_ne='राष्ट्रिय मानव अधिकार आयोग',
            body_type='constitutional',
            base_url='https://nhrcnepal.org',
            endpoints={
                'press_release': '/category/press-release/',
                'notice': '/category/notice/',
            },
            page_structure='category',
            priority=1,
        ),
        'nwc': ConstitutionalBodyConfig(
            body_id='nwc',
            name='National Women Commission',
            name_ne='राष्ट्रिय महिला आयोग',
            body_type='constitutional',
            base_url='https://nwc.gov.np',
            endpoints={
                'press_release': '/category/press-release/',
                'notice': '/category/notice/',
            },
            page_structure='category',
            priority=2,
        ),

        # Regulatory Bodies
        'nrb': ConstitutionalBodyConfig(
            body_id='nrb',
            name='Nepal Rastra Bank',
            name_ne='नेपाल राष्ट्र बैंक',
            body_type='regulatory',
            base_url='https://nrb.org.np',
            endpoints={
                'press_release': '/contents/press-release',
                'notice': '/contents/notice',
                'circular': '/contents/circular',
            },
            page_structure='list',
            priority=1,
        ),
        'sebon': ConstitutionalBodyConfig(
            body_id='sebon',
            name='Securities Board of Nepal',
            name_ne='नेपाल धितोपत्र बोर्ड',
            body_type='regulatory',
            base_url='https://sebon.gov.np',
            endpoints={
                'press_release': '/category/press-release/',
                'notice': '/category/notice/',
                'circular': '/category/circular/',
            },
            page_structure='category',
            priority=1,
        ),
        'nib': ConstitutionalBodyConfig(
            body_id='nib',
            name='Nepal Insurance Board',
            name_ne='नेपाल बीमा समिति',
            body_type='regulatory',
            base_url='https://nib.gov.np',
            endpoints={
                'notice': '/category/notice/',
                'circular': '/category/circular/',
            },
            page_structure='category',
            priority=2,
        ),
        'nta': ConstitutionalBodyConfig(
            body_id='nta',
            name='Nepal Telecommunications Authority',
            name_ne='नेपाल दूरसञ्चार प्राधिकरण',
            body_type='regulatory',
            base_url='https://nta.gov.np',
            endpoints={
                'press_release': '/category/press-release/',
                'notice': '/category/notice/',
            },
            page_structure='category',
            priority=2,
        ),
        'nerc': ConstitutionalBodyConfig(
            body_id='nerc',
            name='Nepal Electricity Regulatory Commission',
            name_ne='विद्युत नियामक आयोग',
            body_type='regulatory',
            base_url='https://nerc.gov.np',
            endpoints={
                'notice': '/category/notice/',
            },
            page_structure='category',
            priority=2,
        ),
        'caan': ConstitutionalBodyConfig(
            body_id='caan',
            name='Civil Aviation Authority of Nepal',
            name_ne='नेपाल नागरिक उड्डयन प्राधिकरण',
            body_type='regulatory',
            base_url='https://caanepal.gov.np',
            endpoints={
                'press_release': '/category/press-release/',
                'notice': '/category/notice/',
            },
            page_structure='category',
            priority=1,
        ),
        'dda': ConstitutionalBodyConfig(
            body_id='dda',
            name='Department of Drug Administration',
            name_ne='औषधि व्यवस्था विभाग',
            body_type='regulatory',
            base_url='https://dda.gov.np',
            endpoints={
                'notice': '/category/notice/',
            },
            page_structure='category',
            priority=2,
        ),

        # Judiciary
        'supremecourt': ConstitutionalBodyConfig(
            body_id='supremecourt',
            name='Supreme Court of Nepal',
            name_ne='सर्वोच्च अदालत',
            body_type='judiciary',
            base_url='https://supremecourt.gov.np',
            endpoints={
                'press_release': '/category/press-release/',
                'notice': '/category/notice/',
            },
            page_structure='category',
            priority=1,
        ),
        'jc': ConstitutionalBodyConfig(
            body_id='jc',
            name='Judicial Council',
            name_ne='न्याय परिषद्',
            body_type='judiciary',
            base_url='https://jc.gov.np',
            endpoints={
                'notice': '/category/notice/',
            },
            page_structure='category',
            priority=2,
        ),
    }

    NEPALI_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')

    def __init__(self, delay: float = 0.5, verify_ssl: bool = False):
        self.delay = delay
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ne;q=0.8',
        })

    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a page."""
        try:
            import time
            time.sleep(self.delay)
            response = self.session.get(url, verify=self.verify_ssl, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def _convert_nepali_digits(self, text: str) -> str:
        return text.translate(self.NEPALI_DIGITS)

    def _extract_bs_date(self, text: str) -> Optional[str]:
        if not text:
            return None
        text = self._convert_nepali_digits(text)
        match = re.search(r'(20\d{2})-(\d{1,2})-(\d{1,2})', text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return None

    def _parse_content_links(
        self,
        soup: BeautifulSoup,
        config: ConstitutionalBodyConfig,
        category: str,
        language: str = "en"
    ) -> List[ConstitutionalPost]:
        """Parse posts from /content/{id}/ link pattern."""
        posts = []
        base_url = config.base_url

        # Find all content links
        content_links = soup.find_all('a', href=re.compile(r'/content/\d+/'))

        seen_urls = set()
        for link in content_links:
            url = link['href']
            if not url.startswith('http'):
                url = f"{base_url}{url}"

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Get title
            title = link.get_text(strip=True)

            # Sometimes title is in parent element
            if not title or len(title) < 5:
                parent = link.find_parent(['div', 'li', 'article', 'h2', 'h3', 'h4', 'tr'])
                if parent:
                    title_el = parent.find(['h2', 'h3', 'h4', 'h5'])
                    if title_el:
                        title = title_el.get_text(strip=True)
                    else:
                        title = parent.get_text(strip=True)[:150]

            # Clean title
            title = re.sub(r'\d+\s*(month|day|week|year|hour|minute)s?\s*ago\s*$', '', title, flags=re.I).strip()
            title = re.sub(r'\s+', ' ', title)

            if not title or len(title) < 5:
                continue

            if len(title) > 200:
                title = title[:197] + '...'

            # Try to find date
            date_bs = None
            parent = link.find_parent(['div', 'li', 'article', 'tr'])
            if parent:
                date_bs = self._extract_bs_date(parent.get_text())

            # Check for attachments
            has_attachment = False
            attachment_urls = []
            if parent:
                for att_link in parent.find_all('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)):
                    has_attachment = True
                    att_url = att_link['href']
                    if not att_url.startswith('http'):
                        att_url = f"{base_url}{att_url}"
                    attachment_urls.append(att_url)

            post_id = hashlib.md5(f"{config.body_id}:{url}".encode()).hexdigest()[:12]

            posts.append(ConstitutionalPost(
                id=post_id,
                title=title,
                url=url,
                body_id=config.body_id,
                body_name=config.name,
                body_name_ne=config.name_ne,
                body_type=config.body_type,
                date_bs=date_bs,
                category=category,
                language=language,
                has_attachment=has_attachment,
                attachment_urls=attachment_urls,
                source_domain=base_url.replace('https://', '').replace('http://', ''),
            ))

        return posts

    def _parse_table_posts(
        self,
        soup: BeautifulSoup,
        config: ConstitutionalBodyConfig,
        category: str,
        language: str
    ) -> List[ConstitutionalPost]:
        """Parse posts from table layout."""
        posts = []

        table = soup.find('table')
        if not table:
            return self._parse_list_posts(soup, config, category, language)

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
                url = f"{config.base_url}{url}"

            date_bs = None
            for cell in row.find_all('td'):
                date_bs = self._extract_bs_date(cell.get_text())
                if date_bs:
                    break

            has_attachment = bool(row.find('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)))
            attachment_urls = []
            for att_link in row.find_all('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)):
                att_url = att_link['href']
                if not att_url.startswith('http'):
                    att_url = f"{config.base_url}{att_url}"
                attachment_urls.append(att_url)

            post_id = hashlib.md5(f"{config.body_id}:{url}".encode()).hexdigest()[:12]

            posts.append(ConstitutionalPost(
                id=post_id,
                title=title,
                url=url,
                body_id=config.body_id,
                body_name=config.name,
                body_name_ne=config.name_ne,
                body_type=config.body_type,
                date_bs=date_bs,
                category=category,
                language=language,
                has_attachment=has_attachment,
                attachment_urls=attachment_urls,
                source_domain=config.base_url.replace('https://', '').replace('http://', ''),
            ))

        return posts

    def _parse_list_posts(
        self,
        soup: BeautifulSoup,
        config: ConstitutionalBodyConfig,
        category: str,
        language: str
    ) -> List[ConstitutionalPost]:
        """Parse posts from list/card layout."""
        posts = []

        # Try various containers
        containers = soup.find_all('div', class_=re.compile(r'news|post|article|list-item|card', re.I))
        if not containers:
            containers = soup.find_all('article')
        if not containers:
            ul = soup.find('ul', class_=re.compile(r'list|news|post', re.I))
            if ul:
                containers = ul.find_all('li')

        for container in containers:
            link = container.find('a', href=True)
            if not link:
                continue

            title_el = container.find(['h2', 'h3', 'h4', 'h5']) or link
            title = title_el.get_text(strip=True)

            if not title or len(title) < 5:
                continue

            url = link['href']
            if not url.startswith('http'):
                url = f"{config.base_url}{url}"

            date_bs = None
            date_el = container.find(class_=re.compile(r'date|time|posted', re.I))
            if date_el:
                date_bs = self._extract_bs_date(date_el.get_text())

            has_attachment = bool(container.find('a', href=re.compile(r'\.(pdf|doc|docx)$', re.I)))

            post_id = hashlib.md5(f"{config.body_id}:{url}".encode()).hexdigest()[:12]

            posts.append(ConstitutionalPost(
                id=post_id,
                title=title,
                url=url,
                body_id=config.body_id,
                body_name=config.name,
                body_name_ne=config.name_ne,
                body_type=config.body_type,
                date_bs=date_bs,
                category=category,
                language=language,
                has_attachment=has_attachment,
                source_domain=config.base_url.replace('https://', '').replace('http://', ''),
            ))

        return posts

    def scrape_body(
        self,
        body_id: str,
        endpoints: List[str] = None,
        max_pages: int = 3,
    ) -> Dict[str, List[ConstitutionalPost]]:
        """Scrape a single constitutional/regulatory body."""

        if body_id not in self.BODIES:
            raise ValueError(f"Unknown body: {body_id}")

        config = self.BODIES[body_id]
        results = {}

        if endpoints is None:
            endpoints = list(config.endpoints.keys())

        for endpoint_key in endpoints:
            if endpoint_key not in config.endpoints:
                continue

            endpoint = config.endpoints[endpoint_key]
            # Determine language from endpoint key or default to en
            language = "ne" if "_ne" in endpoint_key else "en"
            category = endpoint_key.replace("_en", "").replace("_ne", "")

            url = f"{config.base_url}{endpoint}"
            all_posts = []

            for page_num in range(1, max_pages + 1):
                page_url = url if page_num == 1 else f"{url}?page={page_num}"

                logger.info(f"Scraping {body_id} {endpoint_key} page {page_num}")

                soup = self._fetch_page(page_url)
                if not soup:
                    break

                # Try content links first (most common pattern for /category/ pages)
                posts = self._parse_content_links(soup, config, category, language)

                # Fallback to table parsing
                if not posts and config.page_structure == "table":
                    posts = self._parse_table_posts(soup, config, category, language)

                # Fallback to list parsing
                if not posts:
                    posts = self._parse_list_posts(soup, config, category, language)

                if not posts:
                    break

                all_posts.extend(posts)

            # Deduplicate
            seen = set()
            unique = [p for p in all_posts if p.url not in seen and not seen.add(p.url)]

            results[endpoint_key] = unique
            logger.info(f"{body_id} {endpoint_key}: {len(unique)} posts")

        return results

    def scrape_by_type(
        self,
        body_type: str,
        max_pages: int = 2,
    ) -> Dict[str, Dict[str, List[ConstitutionalPost]]]:
        """Scrape all bodies of a specific type."""
        results = {}

        for body_id, config in self.BODIES.items():
            if config.body_type != body_type:
                continue

            try:
                results[body_id] = self.scrape_body(body_id, max_pages=max_pages)
            except Exception as e:
                logger.error(f"Error scraping {body_id}: {e}")
                results[body_id] = {}

        return results

    def scrape_all(
        self,
        max_pages: int = 2,
    ) -> Dict[str, Dict[str, List[ConstitutionalPost]]]:
        """Scrape all constitutional and regulatory bodies."""
        results = {}

        for body_id in self.BODIES:
            try:
                results[body_id] = self.scrape_body(body_id, max_pages=max_pages)
            except Exception as e:
                logger.error(f"Error scraping {body_id}: {e}")
                results[body_id] = {}

        return results


# ============ Async wrapper ============

async def scrape_constitutional_async(
    body_id: str,
    max_pages: int = 3,
) -> Dict[str, List[Dict]]:
    """Async wrapper for constitutional body scraping."""
    def _scrape():
        scraper = ConstitutionalScraper()
        results = scraper.scrape_body(body_id, max_pages=max_pages)
        return {k: [asdict(p) for p in v] for k, v in results.items()}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


async def scrape_all_constitutional_async(
    max_pages: int = 2,
) -> Dict[str, Dict[str, List[Dict]]]:
    """Async wrapper for all constitutional bodies."""
    def _scrape():
        scraper = ConstitutionalScraper()
        results = scraper.scrape_all(max_pages=max_pages)
        return {
            body_id: {k: [asdict(p) for p in v] for k, v in endpoints.items()}
            for body_id, endpoints in results.items()
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


# ============ CLI ============

def main():
    print("=" * 60)
    print("Constitutional Bodies & Regulatory Agencies Scraper")
    print("=" * 60)

    scraper = ConstitutionalScraper()

    print(f"\nConfigured bodies: {len(scraper.BODIES)}")
    print()

    for body_id, config in scraper.BODIES.items():
        print(f"  {body_id}: {config.name}")
        print(f"          Type: {config.body_type}")
        print(f"          URL: {config.base_url}")
        print()

    print("-" * 60)
    print("Testing CIAA scraper...")

    results = scraper.scrape_body('ciaa', max_pages=1)

    total = sum(len(posts) for posts in results.values())
    print(f"\nFound {total} posts from CIAA:")

    for endpoint, posts in results.items():
        print(f"\n  {endpoint}: {len(posts)} posts")
        for post in posts[:2]:
            print(f"    - {post.title[:50]}...")


if __name__ == "__main__":
    main()
