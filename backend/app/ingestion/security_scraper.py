#!/usr/bin/env python3
"""
Security Services Scraper for Nepal

Scrapes announcements from:
- Nepal Police
- Armed Police Force (APF)
- Nepal Army
- National Investigation Department (NID)
- Department of Immigration
- Traffic Police
- Cyber Bureau
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
class SecurityPost:
    """Structured data for security service post."""
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
    alert_type: Optional[str] = None  # wanted, missing, advisory, incident
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class SecuritySourceConfig:
    """Configuration for a security source."""
    source_id: str
    name: str
    name_ne: str
    base_url: str
    endpoints: Dict[str, str]
    page_structure: str = "table"
    priority: int = 1
    poll_interval_mins: int = 30


class SecurityScraper:
    """
    Scraper for Nepal security services websites.

    Handles:
    - Nepal Police - press releases, wanted persons, missing persons
    - Armed Police Force - announcements
    - Nepal Army - press releases
    - Immigration - visa info, notices
    - NID - security alerts
    """

    NEPALI_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')

    SECURITY_SOURCES: Dict[str, SecuritySourceConfig] = {
        'nepalpolice': SecuritySourceConfig(
            source_id='nepalpolice',
            name='Nepal Police',
            name_ne='नेपाल प्रहरी',
            base_url='https://nepalpolice.gov.np',
            endpoints={
                'press_release_en': '/news/press-releases/',
                'latest_news_en': '/news/latest-news/',
                'notice_en': '/notices/other-notices/',
            },
            page_structure='card',
            priority=1,
            poll_interval_mins=30,
        ),
        'apf': SecuritySourceConfig(
            source_id='apf',
            name='Armed Police Force',
            name_ne='सशस्त्र प्रहरी बल',
            base_url='https://apf.gov.np',
            endpoints={
                'notice_ne': '/notices',
                'news_ne': '/news',
                'tender_ne': '/tender-notices',
            },
            page_structure='card',
            priority=1,
            poll_interval_mins=60,
        ),
        'nepalarmy': SecuritySourceConfig(
            source_id='nepalarmy',
            name='Nepal Army',
            name_ne='नेपाली सेना',
            base_url='https://nepalarmy.mil.np',
            endpoints={
                'press_release_en': '/archive/press-release',
                'news_en': '/archive/news',
                'notice_en': '/notices/notices',
            },
            page_structure='card',
            priority=1,
            poll_interval_mins=60,
        ),
        'nid': SecuritySourceConfig(
            source_id='nid',
            name='National Investigation Department',
            name_ne='राष्ट्रिय अनुसन्धान विभाग',
            base_url='https://nid.gov.np',
            endpoints={
                'press_release_ne': '/page/press-release',
                'notice_ne': '/page/notice',
            },
            page_structure='table',
            priority=1,
            poll_interval_mins=60,
        ),
        'immigration': SecuritySourceConfig(
            source_id='immigration',
            name='Department of Immigration',
            name_ne='अध्यागमन विभाग',
            base_url='https://immigration.gov.np',
            endpoints={
                'notice_en': '/page/notice',
                'notice_ne': '/ne/page/notice',
                'press_release_en': '/page/press-release',
            },
            page_structure='table',
            priority=2,
            poll_interval_mins=120,
        ),
        'passport': SecuritySourceConfig(
            source_id='passport',
            name='Department of Passports',
            name_ne='राहदानी विभाग',
            base_url='https://nepalpassport.gov.np',
            endpoints={
                'notice_en': '/page/notice',
                'news_en': '/page/news',
            },
            page_structure='table',
            priority=2,
            poll_interval_mins=120,
        ),
        'traffic': SecuritySourceConfig(
            source_id='traffic',
            name='Traffic Police',
            name_ne='ट्राफिक प्रहरी',
            base_url='https://traffic.nepalpolice.gov.np',
            endpoints={
                'notice_ne': '/notice',
                'news_ne': '/news',
            },
            page_structure='card',
            priority=2,
            poll_interval_mins=120,
        ),
        'cib': SecuritySourceConfig(
            source_id='cib',
            name='Central Investigation Bureau',
            name_ne='केन्द्रीय अनुसन्धान ब्यूरो',
            base_url='https://cib.nepalpolice.gov.np',
            endpoints={
                'press_release_en': '/news/press-releases/',
                'news_en': '/cib-news/',
            },
            page_structure='card',
            priority=1,
            poll_interval_mins=60,
        ),
    }

    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ne;q=0.8',
        })
        self.session.verify = False

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
        return text.translate(self.NEPALI_DIGITS)

    def _extract_bs_date(self, text: str) -> Optional[str]:
        if not text:
            return None
        text = self._convert_nepali_digits(text)
        match = re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})', text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return None

    def _parse_table_posts(
        self,
        soup: BeautifulSoup,
        config: SecuritySourceConfig,
        category: str,
        language: str
    ) -> List[SecurityPost]:
        """Parse posts from table layout."""
        posts = []

        table = soup.find('table')
        if not table:
            table = soup.select_one('.table-responsive table') or soup.select_one('table.table')

        if not table:
            return posts

        tbody = table.find('tbody') or table

        for row in tbody.find_all('tr'):
            link = row.find('a', href=True)
            if not link:
                continue

            title = link.get_text(strip=True)
            title = re.sub(r'\d+\s*(month|day|week|year|hour|minute)s?\s*ago\s*$', '', title, flags=re.I).strip()

            if not title or len(title) < 3:
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

            post_id = hashlib.md5(f"sec:{config.source_id}:{url}".encode()).hexdigest()[:12]

            posts.append(SecurityPost(
                id=post_id,
                title=title,
                url=url,
                source_id=config.source_id,
                source_name=config.name,
                source_domain=config.base_url.replace('https://', '').replace('http://', ''),
                date_bs=date_bs,
                category=category,
                language=language,
                has_attachment=has_attachment,
            ))

        return posts

    def _parse_card_posts(
        self,
        soup: BeautifulSoup,
        config: SecuritySourceConfig,
        category: str,
        language: str
    ) -> List[SecurityPost]:
        """Parse posts from card layout (Nepal Police style)."""
        posts = []

        # Try various card selectors
        cards = soup.select('.card') or soup.select('.news-card') or soup.select('.post-card')
        if not cards:
            # Try list items
            cards = soup.select('.news-list li') or soup.select('.notice-list li')

        for card in cards:
            link = card.find('a', href=True)
            if not link:
                continue

            # Get title from card heading or link text
            title_elem = card.select_one('.card-title') or card.select_one('h4') or card.select_one('h5') or link
            title = title_elem.get_text(strip=True)
            title = re.sub(r'\d+\s*(month|day|week|year)s?\s*ago\s*$', '', title, flags=re.I).strip()

            if not title or len(title) < 3:
                continue

            url = link['href']
            if not url.startswith('http'):
                url = f"{config.base_url}{url}"

            # Try to find date
            date_bs = None
            date_elem = card.select_one('.date') or card.select_one('.card-date') or card.select_one('small')
            if date_elem:
                date_bs = self._extract_bs_date(date_elem.get_text())

            # Get snippet
            snippet_elem = card.select_one('.card-text') or card.select_one('p')
            snippet = snippet_elem.get_text(strip=True)[:200] if snippet_elem else None

            post_id = hashlib.md5(f"sec:{config.source_id}:{url}".encode()).hexdigest()[:12]

            posts.append(SecurityPost(
                id=post_id,
                title=title,
                url=url,
                source_id=config.source_id,
                source_name=config.name,
                source_domain=config.base_url.replace('https://', '').replace('http://', ''),
                date_bs=date_bs,
                category=category,
                language=language,
                content_snippet=snippet,
            ))

        return posts

    def _parse_wanted_missing(
        self,
        soup: BeautifulSoup,
        config: SecuritySourceConfig,
        alert_type: str
    ) -> List[SecurityPost]:
        """Parse wanted/missing persons pages."""
        posts = []

        # These pages often have profile cards
        profiles = soup.select('.profile-card') or soup.select('.wanted-card') or soup.select('.card')

        for profile in profiles:
            link = profile.find('a', href=True)
            name_elem = profile.select_one('.name') or profile.select_one('h4') or profile.select_one('h5')

            if not name_elem:
                continue

            name = name_elem.get_text(strip=True)
            url = link['href'] if link else f"{config.base_url}/{alert_type}"

            if not url.startswith('http'):
                url = f"{config.base_url}{url}"

            # Get additional info
            info_elem = profile.select_one('.info') or profile.select_one('p')
            snippet = info_elem.get_text(strip=True)[:200] if info_elem else None

            post_id = hashlib.md5(f"sec:{config.source_id}:{alert_type}:{name}".encode()).hexdigest()[:12]

            posts.append(SecurityPost(
                id=post_id,
                title=f"{alert_type.title()}: {name}",
                url=url,
                source_id=config.source_id,
                source_name=config.name,
                source_domain=config.base_url.replace('https://', ''),
                category=alert_type,
                language='en',
                content_snippet=snippet,
                alert_type=alert_type,
            ))

        return posts

    def scrape_source(
        self,
        source_id: str,
        endpoints: List[str] = None,
        max_pages: int = 3
    ) -> Dict[str, List[SecurityPost]]:
        """Scrape a single security source."""

        if source_id not in self.SECURITY_SOURCES:
            logger.error(f"Unknown security source: {source_id}")
            return {}

        config = self.SECURITY_SOURCES[source_id]
        results = {}

        if endpoints is None:
            endpoints = list(config.endpoints.keys())

        for endpoint_key in endpoints:
            if endpoint_key not in config.endpoints:
                continue

            endpoint = config.endpoints[endpoint_key]
            language = 'ne' if endpoint_key.endswith('_ne') else 'en'
            category = endpoint_key.replace('_ne', '').replace('_en', '')

            url = f"{config.base_url}{endpoint}"
            all_posts = []

            for page_num in range(1, max_pages + 1):
                page_url = url if page_num == 1 else f"{url}?page={page_num}"

                soup = self._fetch_page(page_url)
                if not soup:
                    break

                # Parse based on endpoint type
                if category in ['wanted', 'missing']:
                    posts = self._parse_wanted_missing(soup, config, category)
                elif config.page_structure == 'card':
                    posts = self._parse_card_posts(soup, config, category, language)
                else:
                    posts = self._parse_table_posts(soup, config, category, language)

                if not posts:
                    break

                all_posts.extend(posts)

            # Deduplicate
            seen = set()
            unique = [p for p in all_posts if p.url not in seen and not seen.add(p.url)]

            results[endpoint_key] = unique
            logger.info(f"Security {source_id} {endpoint_key}: {len(unique)} posts")

        return results

    def scrape_all(self, max_pages: int = 2) -> Dict[str, Dict[str, List[SecurityPost]]]:
        """Scrape all security sources."""
        results = {}

        for source_id in self.SECURITY_SOURCES:
            try:
                results[source_id] = self.scrape_source(source_id, max_pages=max_pages)
            except Exception as e:
                logger.error(f"Error scraping security source {source_id}: {e}")
                results[source_id] = {}

        return results

    def scrape_priority_sources(self, max_pages: int = 2) -> Dict[str, Dict[str, List[SecurityPost]]]:
        """Scrape only priority 1 security sources."""
        results = {}

        for source_id, config in self.SECURITY_SOURCES.items():
            if config.priority == 1:
                try:
                    results[source_id] = self.scrape_source(source_id, max_pages=max_pages)
                except Exception as e:
                    logger.error(f"Error scraping security source {source_id}: {e}")
                    results[source_id] = {}

        return results


# ============ Async wrapper ============

async def scrape_security_async(
    source_ids: List[str] = None,
    max_pages: int = 2,
    max_concurrent: int = 5
) -> Dict[str, Any]:
    """Async scraper for security sources."""
    scraper = SecurityScraper()
    results = {}

    if source_ids is None:
        source_ids = list(scraper.SECURITY_SOURCES.keys())

    semaphore = asyncio.Semaphore(max_concurrent)

    async def scrape_one(source_id: str):
        async with semaphore:
            loop = asyncio.get_event_loop()
            return source_id, await loop.run_in_executor(
                None,
                lambda: scraper.scrape_source(source_id, max_pages=max_pages)
            )

    tasks = [scrape_one(sid) for sid in source_ids]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    for item in completed:
        if isinstance(item, Exception):
            logger.error(f"Security scrape error: {item}")
        else:
            source_id, data = item
            results[source_id] = data

    return results


# ============ CLI ============

def main():
    print("=" * 60)
    print("Security Services Scraper - Nepal")
    print("=" * 60)
    print(f"\nConfigured sources: {len(SecurityScraper.SECURITY_SOURCES)}")
    print()

    for source_id, config in SecurityScraper.SECURITY_SOURCES.items():
        print(f"  {source_id}: {config.name}")
        print(f"          {config.name_ne}")
        print(f"          URL: {config.base_url}")
        print(f"          Priority: {config.priority}")
        print()

    print("-" * 60)
    print("Testing Nepal Army scraper...")

    scraper = SecurityScraper()
    results = scraper.scrape_source('nepalarmy', max_pages=1)

    total_posts = sum(len(posts) for posts in results.values())
    print(f"\nFound {total_posts} posts from Nepal Army:")

    for endpoint, posts in results.items():
        print(f"\n  {endpoint}: {len(posts)} posts")
        for post in posts[:2]:
            print(f"    - {post.title[:60]}")


if __name__ == "__main__":
    main()
