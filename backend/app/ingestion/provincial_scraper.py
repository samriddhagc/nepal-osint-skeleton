#!/usr/bin/env python3
"""
Provincial Government Scraper

Scrapes press releases and announcements from all 7 provincial
government websites in Nepal.
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
class ProvincialPost:
    """Structured data for a provincial government post."""
    id: str
    title: str
    url: str
    province: str
    date_bs: Optional[str] = None
    date: Optional[str] = None
    category: str = "press-release"
    has_attachment: bool = False
    source: str = ""
    source_name: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ProvincialScraper:
    """
    Scraper for Nepal's 7 provincial government websites.

    All provincial sites follow a similar structure based on
    Nepal government website templates.
    """

    # Provincial government websites (updated with working URLs)
    PROVINCES = {
        'koshi': {
            'name': 'Koshi Province',
            'name_ne': 'कोशी प्रदेश',
            'base_url': 'https://ocmcm.koshi.gov.np',
            'alt_urls': ['https://koshi.gov.np'],
            'capital': 'Biratnagar',
        },
        'madhesh': {
            'name': 'Madhesh Province',
            'name_ne': 'मधेश प्रदेश',
            'base_url': 'https://ocmcm.madhesh.gov.np',
            'alt_urls': ['https://madhesh.gov.np'],
            'capital': 'Janakpur',
        },
        'bagmati': {
            'name': 'Bagmati Province',
            'name_ne': 'बागमती प्रदेश',
            'base_url': 'https://bagmati.gov.np',
            'alt_urls': ['https://bagamati.gov.np'],
            'capital': 'Hetauda',
        },
        'gandaki': {
            'name': 'Gandaki Province',
            'name_ne': 'गण्डकी प्रदेश',
            'base_url': 'https://gandaki.gov.np',
            'alt_urls': ['https://ocmcm.gandaki.gov.np'],
            'capital': 'Pokhara',
        },
        'lumbini': {
            'name': 'Lumbini Province',
            'name_ne': 'लुम्बिनी प्रदेश',
            'base_url': 'https://ocmcm.lumbini.gov.np',
            'alt_urls': ['https://lumbini.gov.np'],
            'capital': 'Butwal',
        },
        'karnali': {
            'name': 'Karnali Province',
            'name_ne': 'कर्णाली प्रदेश',
            'base_url': 'https://ocmcm.karnali.gov.np',
            'alt_urls': ['https://karnali.gov.np'],
            'capital': 'Surkhet',
        },
        'sudurpashchim': {
            'name': 'Sudurpashchim Province',
            'name_ne': 'सुदूरपश्चिम प्रदेश',
            'base_url': 'https://ocmcm.sudurpashchim.gov.np',
            'alt_urls': ['https://sudurpashchim.gov.np'],
            'capital': 'Godawari',
        },
    }

    # Page URL patterns (updated - use /category/ for newer sites)
    PAGES = {
        'press-release': '/category/press-release/',
        'press-release-ne': '/category/press-release/',
        'news': '/category/news/',
        'news-ne': '/category/news/',
        'notice': '/category/notice/',
        'notice-ne': '/category/notice/',
        'cabinet-decision': '/category/cabinet-decision/',
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
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ne;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
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

    def _parse_table_posts(self, soup: BeautifulSoup, province_key: str, category: str) -> List[ProvincialPost]:
        """Parse posts from table-based layout (common in govt sites)."""
        posts = []
        province_info = self.PROVINCES[province_key]

        table = soup.find('table')
        if not table:
            # Try card-based layout
            return self._parse_card_posts(soup, province_key, category)

        tbody = table.find('tbody') or table

        for row in tbody.find_all('tr'):
            cells = row.find_all('td')
            if not cells:
                continue

            link = row.find('a', href=True)
            if not link:
                continue

            # Extract title
            title = link.get_text(strip=True)
            title = re.sub(r'\d+\s*(month|day|week|year|hour|minute)s?\s*ago\s*$', '', title, flags=re.I).strip()

            if not title:
                continue

            # Build URL
            url = link['href']
            if not url.startswith('http'):
                url = f"{province_info['base_url']}{url}"

            # Extract date
            date_bs = None
            for cell in cells:
                text = cell.get_text(strip=True)
                bs_match = re.search(r'(20\d{2}-\d{2}-\d{2})', text)
                if bs_match:
                    date_bs = bs_match.group(1)
                    break

            # Check for attachments
            has_attachment = bool(row.find('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)))

            # Generate unique ID
            post_id = hashlib.md5(url.encode()).hexdigest()[:12]

            posts.append(ProvincialPost(
                id=post_id,
                title=title,
                url=url,
                province=province_info['name'],
                date_bs=date_bs,
                category=category,
                has_attachment=has_attachment,
                source=f"{province_key}.gov.np",
                source_name=province_info['name'],
            ))

        return posts

    def _parse_card_posts(self, soup: BeautifulSoup, province_key: str, category: str) -> List[ProvincialPost]:
        """Parse posts from card/grid layout."""
        posts = []
        province_info = self.PROVINCES[province_key]

        # Common card containers
        cards = soup.find_all('div', class_=re.compile(r'card|news-item|post-item|list-item', re.I))
        if not cards:
            cards = soup.find_all('article')

        for card in cards:
            link = card.find('a', href=True)
            if not link:
                continue

            # Title from link or heading
            title_el = card.find(['h2', 'h3', 'h4', 'h5']) or link
            title = title_el.get_text(strip=True)

            if not title or len(title) < 5:
                continue

            # URL
            url = link['href']
            if not url.startswith('http'):
                url = f"{province_info['base_url']}{url}"

            # Date
            date_bs = None
            date_el = card.find(class_=re.compile(r'date|time|posted', re.I))
            if date_el:
                text = date_el.get_text(strip=True)
                bs_match = re.search(r'(20\d{2}-\d{2}-\d{2})', text)
                if bs_match:
                    date_bs = bs_match.group(1)

            # Attachments
            has_attachment = bool(card.find('a', href=re.compile(r'\.(pdf|doc|docx)$', re.I)))

            post_id = hashlib.md5(url.encode()).hexdigest()[:12]

            posts.append(ProvincialPost(
                id=post_id,
                title=title,
                url=url,
                province=province_info['name'],
                date_bs=date_bs,
                category=category,
                has_attachment=has_attachment,
                source=f"{province_key}.gov.np",
                source_name=province_info['name'],
            ))

        return posts

    def _parse_content_links(self, soup: BeautifulSoup, province_key: str, category: str) -> List[ProvincialPost]:
        """Parse posts from content link pattern (/content/{id}/)."""
        posts = []
        province_info = self.PROVINCES[province_key]
        base_url = province_info['base_url']

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
                parent = link.find_parent(['div', 'li', 'article', 'h2', 'h3', 'h4'])
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
                date_text = parent.get_text()
                bs_match = re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})', date_text)
                if bs_match:
                    year, month, day = bs_match.groups()
                    date_bs = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

            # Check for attachments
            has_attachment = False
            if parent:
                has_attachment = bool(parent.find('a', href=re.compile(r'\.(pdf|doc|docx|xls|xlsx)$', re.I)))

            post_id = hashlib.md5(url.encode()).hexdigest()[:12]

            posts.append(ProvincialPost(
                id=post_id,
                title=title,
                url=url,
                province=province_info['name'],
                date_bs=date_bs,
                category=category,
                has_attachment=has_attachment,
                source=base_url.replace('https://', ''),
                source_name=province_info['name'],
            ))

        return posts

    def _get_pagination_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract pagination information."""
        info = {
            'current_page': 1,
            'total_pages': 1,
            'next_url': None,
        }

        pagination = soup.find('nav', {'aria-label': 'Pagination Navigation'}) or \
                     soup.find('ul', class_=re.compile(r'pagination', re.I)) or \
                     soup.find('div', class_=re.compile(r'pagination', re.I))

        if not pagination:
            return info

        page_links = pagination.find_all('a', href=True)
        for link in page_links:
            text = link.get_text(strip=True)
            if text.isdigit():
                info['total_pages'] = max(info['total_pages'], int(text))

        next_link = pagination.find('a', {'rel': 'next'}) or \
                    pagination.find('a', string=re.compile(r'next|»|>', re.I))
        if next_link:
            info['next_url'] = next_link.get('href', '')

        return info

    def scrape_province(
        self,
        province_key: str,
        category: str = 'press-release',
        max_pages: int = 5,
    ) -> List[ProvincialPost]:
        """
        Scrape posts from a specific province.

        Args:
            province_key: Province identifier (e.g., 'koshi', 'bagmati')
            category: Category key (see PAGES dict)
            max_pages: Maximum pages to scrape

        Returns:
            List of ProvincialPost objects
        """
        if province_key not in self.PROVINCES:
            raise ValueError(f"Unknown province: {province_key}. Valid: {list(self.PROVINCES.keys())}")

        if category not in self.PAGES:
            raise ValueError(f"Unknown category: {category}. Valid: {list(self.PAGES.keys())}")

        province_info = self.PROVINCES[province_key]
        base_url = f"{province_info['base_url']}{self.PAGES[category]}"
        all_posts = []
        current_url = base_url
        tried_homepage = False

        for page_num in range(1, max_pages + 1):
            logger.info(f"Scraping {province_key} {category} page {page_num}: {current_url}")

            soup = self._fetch_page(current_url)

            # If category page fails, try homepage for sites that don't have category structure
            if not soup and page_num == 1 and not tried_homepage:
                logger.info(f"Category page failed, trying homepage: {province_info['base_url']}")
                soup = self._fetch_page(province_info['base_url'])
                tried_homepage = True
                if not soup:
                    logger.error(f"Homepage also failed")
                    break
            elif not soup:
                logger.error(f"Failed to fetch page {page_num}")
                break

            # Try content links first (most common pattern)
            posts = self._parse_content_links(soup, province_key, category)

            # Fallback to table/card parsing
            if not posts:
                posts = self._parse_table_posts(soup, province_key, category)

            if not posts:
                logger.info(f"No posts found on page {page_num}, stopping")
                break

            all_posts.extend(posts)
            logger.info(f"Found {len(posts)} posts on page {page_num}")

            # If we fell back to homepage, don't try pagination
            if tried_homepage:
                break

            pagination = self._get_pagination_info(soup)
            if pagination['next_url']:
                next_url = pagination['next_url']
                if not next_url.startswith('http'):
                    next_url = f"{province_info['base_url']}{next_url}"
                current_url = next_url
            elif page_num < pagination['total_pages']:
                current_url = f"{base_url}?page={page_num + 1}"
            else:
                break

        # Deduplicate
        seen_urls = set()
        unique_posts = []
        for post in all_posts:
            if post.url not in seen_urls:
                seen_urls.add(post.url)
                unique_posts.append(post)

        logger.info(f"Total unique posts from {province_key} {category}: {len(unique_posts)}")
        return unique_posts

    def scrape_all_provinces(
        self,
        categories: List[str] = None,
        max_pages_per_category: int = 3,
    ) -> Dict[str, List[ProvincialPost]]:
        """
        Scrape from all provinces.

        Args:
            categories: List of category keys (defaults to press releases)
            max_pages_per_category: Max pages per category

        Returns:
            Dict mapping province to list of posts
        """
        if categories is None:
            categories = ['press-release', 'news']

        results = {}
        for province_key in self.PROVINCES:
            province_posts = []
            for category in categories:
                try:
                    posts = self.scrape_province(province_key, category, max_pages=max_pages_per_category)
                    province_posts.extend(posts)
                except Exception as e:
                    logger.error(f"Error scraping {province_key} {category}: {e}")

            results[province_key] = province_posts

        return results


# ============ Async wrapper for FastAPI ============

async def fetch_provincial_posts_async(
    province_key: str,
    category: str = 'press-release',
    max_pages: int = 3,
) -> List[Dict[str, Any]]:
    """
    Async wrapper for provincial scraping.

    For use in FastAPI endpoints - runs sync code in executor.
    """
    import asyncio

    def _scrape():
        scraper = ProvincialScraper(delay=0.5, verify_ssl=False)
        posts = scraper.scrape_province(province_key, category, max_pages=max_pages)
        return [asdict(p) for p in posts]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


async def fetch_all_provincial_posts_async(
    categories: List[str] = None,
    max_pages: int = 2,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Async wrapper to fetch from all provinces.
    """
    import asyncio

    if categories is None:
        categories = ['press-release', 'news']

    def _scrape():
        scraper = ProvincialScraper(delay=0.5, verify_ssl=False)
        results = scraper.scrape_all_provinces(categories, max_pages_per_category=max_pages)
        return {prov: [asdict(p) for p in posts] for prov, posts in results.items()}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


# Alias for backwards compatibility
scrape_all_provinces_async = fetch_all_provincial_posts_async


# ============ CLI ============

def main():
    print("=" * 60)
    print("Provincial Government Scraper - Nepal")
    print("=" * 60)
    print("\nAvailable provinces:")
    for key, info in ProvincialScraper.PROVINCES.items():
        print(f"  - {key}: {info['name']} ({info['name_ne']})")
    print()

    scraper = ProvincialScraper(delay=0.5, verify_ssl=False)

    print("[1] Scraping Bagmati Province press releases (page 1)...")
    posts = scraper.scrape_province('bagmati', 'press-release-en', max_pages=1)

    print(f"\nFound {len(posts)} posts:")
    print("-" * 60)

    for i, post in enumerate(posts[:5], 1):
        print(f"[{i}] {post.title[:60]}")
        print(f"    Province: {post.province}")
        print(f"    Date (BS): {post.date_bs}")
        print(f"    URL: {post.url}")
        print()

    if len(posts) > 5:
        print(f"... and {len(posts) - 5} more")


if __name__ == "__main__":
    main()
