#!/usr/bin/env python3
"""
Municipality Scraper

Scrapes announcements from Nepal's metropolitan and sub-metropolitan cities.
Includes all 6 metropolitan cities and 11 sub-metropolitan cities.
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
class MunicipalityPost:
    """Structured data for a municipality post."""
    id: str
    title: str
    url: str
    municipality_id: str
    municipality_name: str
    municipality_name_ne: str
    municipality_type: str  # metropolitan, sub-metropolitan
    province: str
    province_id: int
    date_bs: Optional[str] = None
    date_ad: Optional[datetime] = None
    category: str = "notice"
    language: str = "en"
    has_attachment: bool = False
    source_domain: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class MunicipalityConfig:
    """Configuration for a municipality scraper."""
    mun_id: str
    name: str
    name_ne: str
    mun_type: str  # metropolitan, sub-metropolitan
    province: str
    province_id: int
    base_url: str
    endpoints: Dict[str, str]
    page_structure: str = "table"


class MunicipalityScraper:
    """
    Scraper for Nepal's metropolitan and sub-metropolitan municipalities.
    """

    MUNICIPALITIES: Dict[str, MunicipalityConfig] = {
        # ============ METROPOLITAN CITIES (6) ============
        'kathmandu': MunicipalityConfig(
            mun_id='kathmandu',
            name='Kathmandu Metropolitan City',
            name_ne='काठमाडौं महानगरपालिका',
            mun_type='metropolitan',
            province='Bagmati',
            province_id=3,
            base_url='https://kathmandu.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
                'press_release': '/category/press-release/',
            },
            page_structure='category',
        ),
        'lalitpur': MunicipalityConfig(
            mun_id='lalitpur',
            name='Lalitpur Metropolitan City',
            name_ne='ललितपुर महानगरपालिका',
            mun_type='metropolitan',
            province='Bagmati',
            province_id=3,
            base_url='https://lalitpurmun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'pokhara': MunicipalityConfig(
            mun_id='pokhara',
            name='Pokhara Metropolitan City',
            name_ne='पोखरा महानगरपालिका',
            mun_type='metropolitan',
            province='Gandaki',
            province_id=4,
            base_url='https://pokharamun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'bharatpur': MunicipalityConfig(
            mun_id='bharatpur',
            name='Bharatpur Metropolitan City',
            name_ne='भरतपुर महानगरपालिका',
            mun_type='metropolitan',
            province='Bagmati',
            province_id=3,
            base_url='https://bharatpurmun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'biratnagar': MunicipalityConfig(
            mun_id='biratnagar',
            name='Biratnagar Metropolitan City',
            name_ne='विराटनगर महानगरपालिका',
            mun_type='metropolitan',
            province='Koshi',
            province_id=1,
            base_url='https://baboramun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'birgunj': MunicipalityConfig(
            mun_id='birgunj',
            name='Birgunj Metropolitan City',
            name_ne='वीरगञ्ज महानगरपालिका',
            mun_type='metropolitan',
            province='Madhesh',
            province_id=2,
            base_url='https://birgunjmun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),

        # ============ SUB-METROPOLITAN CITIES (11) ============
        'dharan': MunicipalityConfig(
            mun_id='dharan',
            name='Dharan Sub-Metropolitan City',
            name_ne='धरान उपमहानगरपालिका',
            mun_type='sub-metropolitan',
            province='Koshi',
            province_id=1,
            base_url='https://dharanmun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'itahari': MunicipalityConfig(
            mun_id='itahari',
            name='Itahari Sub-Metropolitan City',
            name_ne='इटहरी उपमहानगरपालिका',
            mun_type='sub-metropolitan',
            province='Koshi',
            province_id=1,
            base_url='https://itaharimun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'hetauda': MunicipalityConfig(
            mun_id='hetauda',
            name='Hetauda Sub-Metropolitan City',
            name_ne='हेटौंडा उपमहानगरपालिका',
            mun_type='sub-metropolitan',
            province='Bagmati',
            province_id=3,
            base_url='https://hetaudamun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'janakpur': MunicipalityConfig(
            mun_id='janakpur',
            name='Janakpur Sub-Metropolitan City',
            name_ne='जनकपुरधाम उपमहानगरपालिका',
            mun_type='sub-metropolitan',
            province='Madhesh',
            province_id=2,
            base_url='https://janakpurmun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'nepalgunj': MunicipalityConfig(
            mun_id='nepalgunj',
            name='Nepalgunj Sub-Metropolitan City',
            name_ne='नेपालगञ्ज उपमहानगरपालिका',
            mun_type='sub-metropolitan',
            province='Lumbini',
            province_id=5,
            base_url='https://nepalgunjmun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'butwal': MunicipalityConfig(
            mun_id='butwal',
            name='Butwal Sub-Metropolitan City',
            name_ne='बुटवल उपमहानगरपालिका',
            mun_type='sub-metropolitan',
            province='Lumbini',
            province_id=5,
            base_url='https://butwalmun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'dhangadhi': MunicipalityConfig(
            mun_id='dhangadhi',
            name='Dhangadhi Sub-Metropolitan City',
            name_ne='धनगढी उपमहानगरपालिका',
            mun_type='sub-metropolitan',
            province='Sudurpashchim',
            province_id=7,
            base_url='https://dhangadhimun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'tulsipur': MunicipalityConfig(
            mun_id='tulsipur',
            name='Tulsipur Sub-Metropolitan City',
            name_ne='तुलसीपुर उपमहानगरपालिका',
            mun_type='sub-metropolitan',
            province='Lumbini',
            province_id=5,
            base_url='https://tulsipurmun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'ghorahi': MunicipalityConfig(
            mun_id='ghorahi',
            name='Ghorahi Sub-Metropolitan City',
            name_ne='घोराही उपमहानगरपालिका',
            mun_type='sub-metropolitan',
            province='Lumbini',
            province_id=5,
            base_url='https://ghorahimun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'siddharthanagar': MunicipalityConfig(
            mun_id='siddharthanagar',
            name='Siddharthanagar Municipality',
            name_ne='सिद्धार्थनगर नगरपालिका',
            mun_type='sub-metropolitan',
            province='Lumbini',
            province_id=5,
            base_url='https://siddharthanagarmun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
        ),
        'birendranagar': MunicipalityConfig(
            mun_id='birendranagar',
            name='Birendranagar Municipality',
            name_ne='वीरेन्द्रनगर नगरपालिका',
            mun_type='sub-metropolitan',
            province='Karnali',
            province_id=6,
            base_url='https://birendranagarmun.gov.np',
            endpoints={
                'news': '/category/news/',
                'notice': '/category/notice/',
            },
            page_structure='category',
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
        config: MunicipalityConfig,
        category: str,
        language: str = "ne"
    ) -> List[MunicipalityPost]:
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
            if parent:
                has_attachment = bool(parent.find('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)))

            post_id = hashlib.md5(f"{config.mun_id}:{url}".encode()).hexdigest()[:12]

            posts.append(MunicipalityPost(
                id=post_id,
                title=title,
                url=url,
                municipality_id=config.mun_id,
                municipality_name=config.name,
                municipality_name_ne=config.name_ne,
                municipality_type=config.mun_type,
                province=config.province,
                province_id=config.province_id,
                date_bs=date_bs,
                category=category,
                language=language,
                has_attachment=has_attachment,
                source_domain=base_url.replace('https://', '').replace('http://', ''),
            ))

        return posts

    def _parse_posts(
        self,
        soup: BeautifulSoup,
        config: MunicipalityConfig,
        category: str,
        language: str
    ) -> List[MunicipalityPost]:
        """Parse posts from page."""
        posts = []

        # Try table first
        table = soup.find('table')
        if table:
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

                post_id = hashlib.md5(f"{config.mun_id}:{url}".encode()).hexdigest()[:12]

                posts.append(MunicipalityPost(
                    id=post_id,
                    title=title,
                    url=url,
                    municipality_id=config.mun_id,
                    municipality_name=config.name,
                    municipality_name_ne=config.name_ne,
                    municipality_type=config.mun_type,
                    province=config.province,
                    province_id=config.province_id,
                    date_bs=date_bs,
                    category=category,
                    language=language,
                    has_attachment=has_attachment,
                    source_domain=config.base_url.replace('https://', '').replace('http://', ''),
                ))

            return posts

        # Try card/list layout
        containers = soup.find_all('div', class_=re.compile(r'news|post|article|list-item|card', re.I))
        if not containers:
            containers = soup.find_all('article')

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

            post_id = hashlib.md5(f"{config.mun_id}:{url}".encode()).hexdigest()[:12]

            posts.append(MunicipalityPost(
                id=post_id,
                title=title,
                url=url,
                municipality_id=config.mun_id,
                municipality_name=config.name,
                municipality_name_ne=config.name_ne,
                municipality_type=config.mun_type,
                province=config.province,
                province_id=config.province_id,
                date_bs=date_bs,
                category=category,
                language=language,
                has_attachment=has_attachment,
                source_domain=config.base_url.replace('https://', '').replace('http://', ''),
            ))

        return posts

    def scrape_municipality(
        self,
        mun_id: str,
        endpoints: List[str] = None,
        max_pages: int = 3,
    ) -> Dict[str, List[MunicipalityPost]]:
        """Scrape a single municipality."""

        if mun_id not in self.MUNICIPALITIES:
            raise ValueError(f"Unknown municipality: {mun_id}")

        config = self.MUNICIPALITIES[mun_id]
        results = {}

        if endpoints is None:
            endpoints = list(config.endpoints.keys())

        for endpoint_key in endpoints:
            if endpoint_key not in config.endpoints:
                continue

            endpoint = config.endpoints[endpoint_key]
            # Determine language - default to Nepali for most municipalities
            language = "en" if "_en" in endpoint_key else "ne"
            category = endpoint_key.replace("_en", "").replace("_ne", "")

            url = f"{config.base_url}{endpoint}"
            all_posts = []
            tried_homepage = False

            for page_num in range(1, max_pages + 1):
                page_url = url if page_num == 1 else f"{url}?page={page_num}"

                logger.info(f"Scraping {mun_id} {endpoint_key} page {page_num}")

                soup = self._fetch_page(page_url)

                # If category page fails, try homepage
                if not soup and page_num == 1 and not tried_homepage:
                    logger.info(f"Category page failed, trying homepage: {config.base_url}")
                    soup = self._fetch_page(config.base_url)
                    tried_homepage = True
                    if not soup:
                        logger.error(f"Homepage also failed")
                        break

                if not soup:
                    break

                # Try content links first (most common pattern for /category/ pages)
                posts = self._parse_content_links(soup, config, category, language)

                # Fallback to table/card parsing
                if not posts:
                    posts = self._parse_posts(soup, config, category, language)

                if not posts:
                    break

                all_posts.extend(posts)

                # If we fell back to homepage, don't try pagination
                if tried_homepage:
                    break

            # Deduplicate
            seen = set()
            unique = [p for p in all_posts if p.url not in seen and not seen.add(p.url)]

            results[endpoint_key] = unique
            logger.info(f"{mun_id} {endpoint_key}: {len(unique)} posts")

        return results

    def scrape_metros(
        self,
        max_pages: int = 2,
    ) -> Dict[str, Dict[str, List[MunicipalityPost]]]:
        """Scrape all metropolitan cities."""
        results = {}

        for mun_id, config in self.MUNICIPALITIES.items():
            if config.mun_type != 'metropolitan':
                continue

            try:
                results[mun_id] = self.scrape_municipality(mun_id, max_pages=max_pages)
            except Exception as e:
                logger.error(f"Error scraping {mun_id}: {e}")
                results[mun_id] = {}

        return results

    def scrape_all(
        self,
        max_pages: int = 2,
    ) -> Dict[str, Dict[str, List[MunicipalityPost]]]:
        """Scrape all municipalities."""
        results = {}

        for mun_id in self.MUNICIPALITIES:
            try:
                results[mun_id] = self.scrape_municipality(mun_id, max_pages=max_pages)
            except Exception as e:
                logger.error(f"Error scraping {mun_id}: {e}")
                results[mun_id] = {}

        return results


# ============ Async wrapper ============

async def scrape_municipality_async(
    mun_id: str,
    max_pages: int = 3,
) -> Dict[str, List[Dict]]:
    """Async wrapper for municipality scraping."""
    def _scrape():
        scraper = MunicipalityScraper()
        results = scraper.scrape_municipality(mun_id, max_pages=max_pages)
        return {k: [asdict(p) for p in v] for k, v in results.items()}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


async def scrape_all_municipalities_async(
    max_pages: int = 2,
) -> Dict[str, Dict[str, List[Dict]]]:
    """Async wrapper for all municipalities."""
    def _scrape():
        scraper = MunicipalityScraper()
        results = scraper.scrape_all(max_pages=max_pages)
        return {
            mun_id: {k: [asdict(p) for p in v] for k, v in endpoints.items()}
            for mun_id, endpoints in results.items()
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


# ============ CLI ============

def main():
    print("=" * 60)
    print("Municipality Scraper - Nepal")
    print("=" * 60)

    scraper = MunicipalityScraper()

    metros = [m for m, c in scraper.MUNICIPALITIES.items() if c.mun_type == 'metropolitan']
    submetros = [m for m, c in scraper.MUNICIPALITIES.items() if c.mun_type == 'sub-metropolitan']

    print(f"\nMetropolitan Cities ({len(metros)}):")
    for mun_id in metros:
        config = scraper.MUNICIPALITIES[mun_id]
        print(f"  - {config.name}")

    print(f"\nSub-Metropolitan Cities ({len(submetros)}):")
    for mun_id in submetros:
        config = scraper.MUNICIPALITIES[mun_id]
        print(f"  - {config.name}")

    print("\n" + "-" * 60)
    print("Testing Kathmandu Metropolitan scraper...")

    results = scraper.scrape_municipality('kathmandu', max_pages=1)

    total = sum(len(posts) for posts in results.values())
    print(f"\nFound {total} posts from Kathmandu Metro:")

    for endpoint, posts in results.items():
        print(f"\n  {endpoint}: {len(posts)} posts")
        for post in posts[:2]:
            print(f"    - {post.title[:50]}...")


if __name__ == "__main__":
    main()
