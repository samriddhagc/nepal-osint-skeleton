"""
Parliament Scraper for Nepal Parliament websites.

Scrapes MP profiles, bills, committees, attendance, and questions from:
- hr.parliament.gov.np (House of Representatives)
- na.parliament.gov.np (National Assembly)

Note: Sites have SSL certificate issues - uses verify=False.
"""

import asyncio
import hashlib
import logging
import re
import ssl
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text:
        return ""
    return " ".join(text.strip().split())


def generate_id(url: str) -> str:
    """Generate a unique ID from URL."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


# District name to province mapping (based on Nepal's administrative divisions)
# Maps district names from the parliament API to province numbers (1-7)
DISTRICT_TO_PROVINCE = {
    # Province 1 (Koshi)
    'Taplejung': 1, 'Panchthar': 1, 'Ilam': 1, 'Jhapa': 1, 'Morang': 1,
    'Sunsari': 1, 'Dhankuta': 1, 'Terhathum': 1, 'Sankhuwasabha': 1,
    'Bhojpur': 1, 'Solukhumbu': 1, 'Okhaldhunga': 1, 'Khotang': 1, 'Udayapur': 1,
    # Province 2 (Madhesh)
    'Saptari': 2, 'Siraha': 2, 'Dhanusha': 2, 'Mahottari': 2, 'Sarlahi': 2,
    'Rautahat': 2, 'Bara': 2, 'Parsa': 2,
    # Province 3 (Bagmati)
    'Dolakha': 3, 'Sindhupalchok': 3, 'Rasuwa': 3, 'Dhading': 3, 'Nuwakot': 3,
    'Kathmandu': 3, 'Bhaktapur': 3, 'Lalitpur': 3, 'Kavrepalanchok': 3,
    'Ramechhap': 3, 'Sindhuli': 3, 'Makwanpur': 3, 'Chitwan': 3,
    # Province 4 (Gandaki)
    'Gorkha': 4, 'Lamjung': 4, 'Tanahu': 4, 'Syangja': 4, 'Kaski': 4,
    'Manang': 4, 'Mustang': 4, 'Myagdi': 4, 'Parbat': 4, 'Baglung': 4, 'Nawalparasi East': 4,
    # Province 5 (Lumbini)
    'Nawalparasi West': 5, 'Rupandehi': 5, 'Kapilvastu': 5, 'Palpa': 5,
    'Arghakhanchi': 5, 'Gulmi': 5, 'Pyuthan': 5, 'Rolpa': 5, 'Rukum East': 5,
    'Dang': 5, 'Banke': 5, 'Bardiya': 5,
    # Province 6 (Karnali)
    'Rukum West': 6, 'Salyan': 6, 'Dolpa': 6, 'Humla': 6, 'Jumla': 6,
    'Kalikot': 6, 'Mugu': 6, 'Surkhet': 6, 'Dailekh': 6, 'Jajarkot': 6,
    'Western Rukum': 6,
    # Province 7 (Sudurpashchim)
    'Bajura': 7, 'Bajhang': 7, 'Achham': 7, 'Doti': 7, 'Kailali': 7,
    'Kanchanpur': 7, 'Dadeldhura': 7, 'Baitadi': 7, 'Darchula': 7,
}


# ============ Data Classes ============

@dataclass
class MPProfile:
    """Scraped MP profile data."""
    mp_id: str  # Parliament website ID
    name_en: str
    name_ne: Optional[str] = None
    party: Optional[str] = None
    party_ne: Optional[str] = None
    constituency: Optional[str] = None
    province_id: Optional[int] = None
    election_type: Optional[str] = None  # 'fptp' or 'pr'
    chamber: str = "hor"  # 'hor' or 'na'
    term: Optional[str] = None
    photo_url: Optional[str] = None
    is_minister: bool = False
    ministry_portfolio: Optional[str] = None
    profile_url: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class BillData:
    """Scraped bill data."""
    external_id: str
    title_en: str
    title_ne: Optional[str] = None
    bill_type: Optional[str] = None
    status: Optional[str] = None
    presented_date: Optional[str] = None  # ISO format
    passed_date: Optional[str] = None
    presenting_mp_name: Optional[str] = None
    ministry: Optional[str] = None
    chamber: str = "hor"
    term: Optional[str] = None
    pdf_url: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class CommitteeData:
    """Scraped committee data."""
    external_id: str
    name_en: str
    name_ne: Optional[str] = None
    committee_type: Optional[str] = None  # 'thematic', 'procedural', 'special'
    chamber: str = "hor"
    term: Optional[str] = None
    is_active: bool = True
    members: List[Dict[str, Any]] = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class AttendanceRecord:
    """Scraped attendance record."""
    mp_name: str
    session_date: str  # ISO format
    session_type: Optional[str] = None
    present: bool = False
    chamber: str = "hor"
    term: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class QuestionData:
    """Scraped parliamentary question."""
    external_id: str
    asker_name: str
    question_type: Optional[str] = None  # 'zero_hour', 'special_hour', 'written', 'starred'
    question_text: Optional[str] = None
    question_date: Optional[str] = None  # ISO format
    ministry_addressed: Optional[str] = None
    answered: bool = False
    answerer_name: Optional[str] = None
    chamber: str = "hor"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class VideoRecord:
    """Scraped parliament video record with speaker information."""
    external_id: str
    title: str
    speaker_name: Optional[str] = None  # Extracted speaker name (Nepali)
    speaker_name_normalized: Optional[str] = None  # Cleaned up name for matching
    video_url: Optional[str] = None
    video_date: Optional[str] = None  # ISO format
    duration: Optional[str] = None
    session_info: Optional[str] = None
    chamber: str = "hor"
    term: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ============ Parliament Scraper Class ============

class ParliamentScraper:
    """
    Async scraper for Nepal Parliament websites.

    Supports scraping from both houses:
    - House of Representatives (hr.parliament.gov.np) - 275 members
    - National Assembly (na.parliament.gov.np) - 59 members

    Note: Sites have SSL certificate issues, so verification is disabled.
    """

    # JSON API endpoints (the website loads data via AJAX)
    API_ENDPOINTS = {
        # House of Representatives - JSON API
        'members_hor': 'https://hr.parliament.gov.np/api/v1/members?member_type=member&registered_date=2079&show_member=active',
        'bills_hor': 'https://hr.parliament.gov.np/api/v1/bills',
        'committees_hor': 'https://hr.parliament.gov.np/api/v1/committees',

        # National Assembly - JSON API
        'members_na': 'https://na.parliament.gov.np/api/v1/members?member_type=member&show_member=active',
        'bills_na': 'https://na.parliament.gov.np/api/v1/bills',
        'committees_na': 'https://na.parliament.gov.np/api/v1/committees',
    }

    # Legacy HTML endpoints (kept for reference/fallback)
    ENDPOINTS = {
        # House of Representatives
        'members_hor': 'https://hr.parliament.gov.np/en/members',
        'members_hor_ne': 'https://hr.parliament.gov.np/np/members',
        'bills_registered_hor': 'https://hr.parliament.gov.np/en/bills?type=reg',
        'bills_passed_hor': 'https://hr.parliament.gov.np/en/bills?type=auth',
        'bills_state_hor': 'https://hr.parliament.gov.np/en/bills?type=state',
        'bills_state_na': 'https://na.parliament.gov.np/en/bills?type=state',
        'committees_hor': 'https://hr.parliament.gov.np/en/committees',
        'committees_list_hor': 'https://hr.parliament.gov.np/en/committees-2074',  # For list page
        'today_parliament_hor': 'https://hr.parliament.gov.np/en/today-parliament',

        # National Assembly
        'members_na': 'https://na.parliament.gov.np/en/members',
        'members_na_ne': 'https://na.parliament.gov.np/np/members',
        'bills_registered_na': 'https://na.parliament.gov.np/en/bills?type=reg',
        'bills_passed_na': 'https://na.parliament.gov.np/en/bills?type=auth',
        'committees_na': 'https://na.parliament.gov.np/en/committees',
        'today_parliament_na': 'https://na.parliament.gov.np/en/today-parliament',

        # Video Archives (for tracking who speaks in parliament)
        'videos_hor': 'https://hr.parliament.gov.np/en/videos',
        'videos_na': 'https://na.parliament.gov.np/en/videos',
    }

    BASE_URLS = {
        'hor': 'https://hr.parliament.gov.np',
        'na': 'https://na.parliament.gov.np',
    }

    def __init__(
        self,
        rate_limit: float = 1.0,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize the scraper.

        Args:
            rate_limit: Seconds between requests (default 1.0)
            timeout: Request timeout in seconds
            max_retries: Maximum retries for failed requests
        """
        self.rate_limit = rate_limit
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry."""
        # Create SSL context that doesn't verify certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,ne;q=0.8',
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch a page with rate limiting and retries.

        Args:
            url: URL to fetch

        Returns:
            HTML content or None if failed
        """
        if not self.session:
            raise RuntimeError("Session not initialized. Use 'async with' context manager.")

        await asyncio.sleep(self.rate_limit)

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1})")
                async with self.session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(f"HTTP {response.status} for {url}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout for {url}, attempt {attempt + 1}")
            except aiohttp.ClientError as e:
                logger.warning(f"Client error for {url}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error for {url}: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        logger.error(f"Failed to fetch {url} after {self.max_retries} attempts")
        return None

    # ============ Member Scraping ============

    async def scrape_members(self, chamber: str = 'hor') -> List[MPProfile]:
        """
        Scrape MP profiles from parliament API with pagination.

        Args:
            chamber: 'hor' for House of Representatives, 'na' for National Assembly

        Returns:
            List of MPProfile objects
        """
        url = self.API_ENDPOINTS.get(f'members_{chamber}')
        if not url:
            logger.error(f"Unknown chamber: {chamber}")
            return []

        all_members = []
        page = 1
        while True:
            page_url = f"{url}&page={page}" if '?' in url else f"{url}?page={page}"
            json_data = await self.fetch_json(page_url)
            if not json_data:
                break

            # Handle nested response: {"data": {"total": N, "data": [...]}}
            items = json_data
            if isinstance(items, dict) and 'data' in items:
                inner = items['data']
                if isinstance(inner, dict) and 'data' in inner:
                    # Nested: {"data": {"total":..., "data": [...]}}
                    last_page = inner.get('last_page', 1)
                    items = inner['data']
                elif isinstance(inner, list):
                    items = inner
                    last_page = items.get('last_page', 1) if isinstance(items, dict) else 1
                else:
                    items = inner
                    last_page = 1
            else:
                last_page = 1

            if not items or not isinstance(items, list):
                break

            members = self._parse_members_json(items, chamber)
            if not members:
                break

            all_members.extend(members)
            logger.info(f"Page {page}: {len(members)} members (total: {len(all_members)})")

            # Check if there are more pages
            if page >= last_page:
                break

            # Safety: stop if we got fewer items than typical page size
            if len(items) < 50:
                break

            page += 1

        logger.info(f"Total members scraped from {chamber}: {len(all_members)}")
        return all_members

    async def fetch_json(self, url: str) -> Optional[Any]:
        """
        Fetch JSON from API with rate limiting and retries.

        Args:
            url: URL to fetch

        Returns:
            Parsed JSON or None if failed
        """
        if not self.session:
            raise RuntimeError("Session not initialized. Use 'async with' context manager.")

        await asyncio.sleep(self.rate_limit)

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Fetching JSON: {url} (attempt {attempt + 1})")
                async with self.session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"HTTP {response.status} for {url}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout for {url}, attempt {attempt + 1}")
            except aiohttp.ClientError as e:
                logger.warning(f"Client error for {url}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error for {url}: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        logger.error(f"Failed to fetch {url} after {self.max_retries} attempts")
        return None

    def _parse_members_json(self, items: List[Dict[str, Any]], chamber: str) -> List[MPProfile]:
        """Parse MP profiles from JSON API response."""
        members = []
        base_url = self.BASE_URLS[chamber]

        for item in items:
            # Only include actual MPs (member_type == 'member')
            if item.get('member_type') != 'member':
                continue

            # Get translations
            translations = item.get('parliament_member_translations', [])
            en_trans = next((t for t in translations if t.get('locale') == 'en'), {})
            np_trans = next((t for t in translations if t.get('locale') == 'np'), {})

            name_en = en_trans.get('name', '').strip()
            name_ne = np_trans.get('name', '').strip() or None

            if not name_en:
                continue

            # Get party info
            party_info = item.get('political_party', {}) or {}
            party = party_info.get('party_name_en')
            party_ne = party_info.get('party_name_np')

            # Get district info
            district_info = item.get('district', {}) or {}
            district_en = district_info.get('name_en', '')
            constituency_num = item.get('election_area_no', 0)
            constituency = f"{district_en}-{constituency_num}" if district_en and constituency_num else district_en

            # Map district to province
            province_id = DISTRICT_TO_PROVINCE.get(district_en)

            # Determine election type (FPTP = Direct, PR = Indirect)
            election_type_info = item.get('election_type', {}) or {}
            election_type_en = election_type_info.get('election_type_en', '').lower()
            election_type = 'fptp' if election_type_en == 'direct' else 'pr' if election_type_en == 'indirect' else None

            # Get photo URL
            photo_url = None
            images = item.get('images', {}) or {}
            if images and images.get('images', {}).get('original'):
                photo_url = f"{base_url}/uploads/parliament_members/{images['images']['original']}"

            # Check if minister (by designation)
            designation = en_trans.get('designation') or ''
            is_minister = 'minister' in designation.lower()
            ministry_portfolio = designation if is_minister else None

            # Get term from registered_date
            term = str(item.get('registered_date', ''))

            members.append(MPProfile(
                mp_id=str(item.get('id')),
                name_en=name_en,
                name_ne=name_ne,
                party=party,
                party_ne=party_ne,
                constituency=constituency,
                province_id=province_id,
                election_type=election_type,
                chamber=chamber,
                term=term,
                photo_url=photo_url,
                is_minister=is_minister,
                ministry_portfolio=ministry_portfolio,
                profile_url=f"{base_url}/en/members/{item.get('slug', '')}",
            ))

        logger.info(f"Parsed {len(members)} MPs from {chamber} API")
        return members

    def _parse_members(self, html: str, chamber: str) -> List[MPProfile]:
        """Parse member profiles from HTML."""
        members = []
        soup = BeautifulSoup(html, 'html.parser')
        base_url = self.BASE_URLS[chamber]

        # Look for member cards/items in common patterns
        # Pattern 1: Table rows
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                if row.find('th'):  # Skip header
                    continue

                cells = row.find_all('td')
                if len(cells) < 2:
                    continue

                # Try to extract member info
                link = row.find('a', href=True)
                if not link:
                    continue

                name_en = clean_text(link.get_text())
                if not name_en or len(name_en) < 3:
                    continue

                href = link['href']
                profile_url = href if href.startswith('http') else urljoin(base_url, href)
                mp_id = generate_id(profile_url)

                # Try to find party and constituency from other cells
                party = None
                constituency = None
                for cell in cells:
                    cell_text = clean_text(cell.get_text())
                    if cell_text == name_en:
                        continue
                    if not party and len(cell_text) > 2:
                        # First non-name cell is usually party
                        if any(kw in cell_text.lower() for kw in ['congress', 'uml', 'maoist', 'janamat', 'loktantrik']):
                            party = cell_text
                        elif not constituency:
                            constituency = cell_text

                # Try to find photo
                photo_el = row.find('img', src=True)
                photo_url = None
                if photo_el:
                    src = photo_el['src']
                    photo_url = src if src.startswith('http') else urljoin(base_url, src)

                members.append(MPProfile(
                    mp_id=mp_id,
                    name_en=name_en,
                    party=party,
                    constituency=constituency,
                    chamber=chamber,
                    photo_url=photo_url,
                    profile_url=profile_url,
                ))

        # Pattern 2: Card/list items
        for card in soup.find_all(['div', 'article', 'li'], class_=re.compile(r'member|card|item', re.I)):
            link = card.find('a', href=True)
            if not link:
                continue

            # Get name from heading or link
            name_el = card.find(['h1', 'h2', 'h3', 'h4', 'h5']) or link
            name_en = clean_text(name_el.get_text()) if name_el else None
            if not name_en or len(name_en) < 3:
                continue

            href = link['href']
            profile_url = href if href.startswith('http') else urljoin(base_url, href)
            mp_id = generate_id(profile_url)

            # Skip if already found
            if any(m.mp_id == mp_id for m in members):
                continue

            # Find party
            party_el = card.find(class_=re.compile(r'party|political', re.I))
            party = clean_text(party_el.get_text()) if party_el else None

            # Find constituency
            const_el = card.find(class_=re.compile(r'constituency|district', re.I))
            constituency = clean_text(const_el.get_text()) if const_el else None

            # Find photo
            photo_el = card.find('img', src=True)
            photo_url = None
            if photo_el:
                src = photo_el['src']
                photo_url = src if src.startswith('http') else urljoin(base_url, src)

            members.append(MPProfile(
                mp_id=mp_id,
                name_en=name_en,
                party=party,
                constituency=constituency,
                chamber=chamber,
                photo_url=photo_url,
                profile_url=profile_url,
            ))

        logger.info(f"Parsed {len(members)} members from {chamber}")
        return members

    async def scrape_member_detail(self, profile_url: str, chamber: str = 'hor') -> Optional[Dict[str, Any]]:
        """
        Scrape detailed profile for a single MP.

        Args:
            profile_url: URL to the MP's profile page
            chamber: 'hor' or 'na'

        Returns:
            Dict with detailed profile info
        """
        html = await self.fetch_page(profile_url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')
        detail = {
            'profile_url': profile_url,
            'name_en': None,
            'name_ne': None,
            'party': None,
            'constituency': None,
            'province_id': None,
            'election_type': None,
            'photo_url': None,
            'is_minister': False,
            'ministry_portfolio': None,
        }

        # Try to extract info from profile page
        # Title/Name
        title = soup.find('h1') or soup.find('h2', class_=re.compile(r'name|title', re.I))
        if title:
            detail['name_en'] = clean_text(title.get_text())

        # Look for info table/list
        info_container = soup.find(class_=re.compile(r'profile|info|detail', re.I))
        if info_container:
            for row in info_container.find_all(['tr', 'li', 'div']):
                text = clean_text(row.get_text())
                text_lower = text.lower()

                if 'party' in text_lower or 'political' in text_lower:
                    # Extract party value
                    value = row.find('td') or row.find(class_=re.compile(r'value', re.I))
                    if value:
                        detail['party'] = clean_text(value.get_text())

                if 'constituency' in text_lower or 'निर्वाचन क्षेत्र' in text:
                    value = row.find('td') or row.find(class_=re.compile(r'value', re.I))
                    if value:
                        detail['constituency'] = clean_text(value.get_text())

                if 'province' in text_lower or 'प्रदेश' in text:
                    value = row.find('td') or row.find(class_=re.compile(r'value', re.I))
                    if value:
                        try:
                            province_text = clean_text(value.get_text())
                            numbers = re.findall(r'\d+', nepali_to_arabic(province_text))
                            if numbers:
                                detail['province_id'] = int(numbers[0])
                        except ValueError:
                            pass

                if 'minister' in text_lower or 'मन्त्री' in text:
                    detail['is_minister'] = True
                    value = row.find('td') or row.find(class_=re.compile(r'value', re.I))
                    if value:
                        detail['ministry_portfolio'] = clean_text(value.get_text())

                if 'fptp' in text_lower or 'direct' in text_lower or 'प्रत्यक्ष' in text:
                    detail['election_type'] = 'fptp'
                elif 'proportional' in text_lower or 'pr' in text_lower or 'समानुपातिक' in text:
                    detail['election_type'] = 'pr'

        # Photo
        photo = soup.find('img', class_=re.compile(r'photo|profile|avatar', re.I))
        if photo and photo.get('src'):
            src = photo['src']
            base_url = self.BASE_URLS[chamber]
            detail['photo_url'] = src if src.startswith('http') else urljoin(base_url, src)

        return detail

    # ============ Bill Scraping ============

    async def scrape_bills(
        self,
        bill_type: str = 'registered',
        chamber: str = 'hor',
        max_pages: int = 5,
    ) -> List[BillData]:
        """
        Scrape bills from parliament website.

        Args:
            bill_type: 'registered', 'passed', or 'state'
            chamber: 'hor' or 'na'
            max_pages: Maximum pages to scrape

        Returns:
            List of BillData objects
        """
        endpoint_key = f'bills_{bill_type}_{chamber}'
        url = self.ENDPOINTS.get(endpoint_key)
        if not url:
            logger.error(f"Unknown endpoint: {endpoint_key}")
            return []

        all_bills = []
        for page_num in range(1, max_pages + 1):
            page_url = url if page_num == 1 else f"{url}&page={page_num}"

            html = await self.fetch_page(page_url)
            if not html:
                break

            bills = self._parse_bills(html, chamber, bill_type)
            if not bills:
                break

            # Check for duplicates
            new_bills = [b for b in bills if not any(eb.external_id == b.external_id for eb in all_bills)]
            if not new_bills:
                break

            all_bills.extend(new_bills)
            logger.info(f"Found {len(new_bills)} bills on page {page_num}")

        logger.info(f"Total bills scraped from {chamber} ({bill_type}): {len(all_bills)}")
        return all_bills

    def _parse_bills(self, html: str, chamber: str, bill_type: str) -> List[BillData]:
        """Parse bills from HTML."""
        bills = []
        soup = BeautifulSoup(html, 'html.parser')
        base_url = self.BASE_URLS[chamber]

        # Status mapping based on bill_type
        status_map = {
            'registered': 'registered',
            'passed': 'passed',
            'state': None,  # Will be parsed from content
        }
        default_status = status_map.get(bill_type)

        # Look for bill listings in tables
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                if row.find('th'):  # Skip header
                    continue

                cells = row.find_all('td')
                if len(cells) < 2:
                    continue

                # Find title link
                link = row.find('a', href=True)
                if not link:
                    continue

                title_en = clean_text(link.get_text())
                if not title_en or len(title_en) < 5:
                    continue

                href = link['href']
                bill_url = href if href.startswith('http') else urljoin(base_url, href)
                external_id = generate_id(bill_url)

                # Try to extract date, presenter, status from cells
                presented_date = None
                presenting_mp_name = None
                status = default_status
                ministry = None

                for cell in cells:
                    cell_text = clean_text(cell.get_text())
                    if cell_text == title_en:
                        continue

                    # Date detection
                    date_match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', nepali_to_arabic(cell_text))
                    if date_match:
                        presented_date = date_match.group(0)
                        continue

                    # Status detection
                    cell_lower = cell_text.lower()
                    if 'passed' in cell_lower or 'प्रमाणीकरण' in cell_text:
                        status = 'passed'
                    elif 'pending' in cell_lower or 'विचाराधीन' in cell_text:
                        status = 'committee'
                    elif 'rejected' in cell_lower or 'अस्वीकृत' in cell_text:
                        status = 'rejected'

                    # Ministry detection
                    if 'ministry' in cell_lower or 'मन्त्रालय' in cell_text:
                        ministry = cell_text

                # Determine bill type from title/content
                detected_bill_type = 'government'
                title_lower = title_en.lower()
                if 'amendment' in title_lower or 'संशोधन' in title_en:
                    detected_bill_type = 'amendment'
                elif 'money' in title_lower or 'विनियोजन' in title_en or 'आर्थिक' in title_en:
                    detected_bill_type = 'money'

                # Store the bill detail URL for later fetching
                detail_url = bill_url if not bill_url.endswith('.pdf') else None

                bills.append(BillData(
                    external_id=external_id,
                    title_en=title_en,
                    bill_type=detected_bill_type,
                    status=status,
                    presented_date=presented_date,
                    presenting_mp_name=presenting_mp_name,
                    ministry=ministry,
                    chamber=chamber,
                    pdf_url=bill_url if bill_url.endswith('.pdf') else detail_url,
                ))

        return bills

    async def scrape_bill_detail(self, bill_url: str) -> Optional[Dict[str, Any]]:
        """
        Scrape detailed bill information including presenter.

        Args:
            bill_url: URL to the bill detail page

        Returns:
            Dict with bill details including presenter name
        """
        html = await self.fetch_page(bill_url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')
        detail = {
            'presenter': None,
            'ministry': None,
            'registration_no': None,
            'registration_date': None,
            'session': None,
            'category': None,
            'bill_type': None,  # Governmental/Non-Governmental
            'original_or_amendment': None,
        }

        # Look for info in table or definition list format
        # The bill page has format like:
        # Presenter: Hon. Ramnath AdhikarI
        # Ministry: Ministry of Agriculture...

        # Method 1: Look for labeled rows
        for container in soup.find_all(['table', 'div', 'dl']):
            text = container.get_text()

            # Presenter detection - multiple patterns
            patterns = [
                (r'Presenter[:\s]+([^\n]+)', 'presenter'),
                (r'प्रस्तुतकर्ता[:\s]+([^\n]+)', 'presenter'),
                (r'Hon\.\s*([A-Za-z\s\.]+)', 'presenter'),
                (r'Ministry[:\s]+([^\n]+)', 'ministry'),
                (r'मन्त्रालय[:\s]+([^\n]+)', 'ministry'),
                (r'Registration No\.?[:\s]+(\d+)', 'registration_no'),
                (r'दर्ता नं\.?[:\s]+([०-९\d]+)', 'registration_no'),
                (r'Registration Date[:\s]+([\d\-]+)', 'registration_date'),
                (r'दर्ता मिति[:\s]+([\d\-०-९]+)', 'registration_date'),
                (r'Session[:\s]+(\d+)', 'session'),
                (r'अधिवेशन[:\s]+([०-९\d]+)', 'session'),
                (r'Governmental/Non Governmental[:\s]+(\w+)', 'bill_type'),
                (r'Original/Amendment[:\s]+(\w+)', 'original_or_amendment'),
            ]

            for pattern, field in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match and not detail[field]:
                    value = match.group(1).strip()
                    # Clean up the value
                    value = re.sub(r'\s+', ' ', value)
                    value = value.strip()
                    if value and len(value) > 1:
                        detail[field] = nepali_to_arabic(value) if field in ['registration_no', 'session'] else value

        # Method 2: Look for labeled table cells (Parliament uses <td>Label</td><td>Value</td> format)
        all_tds = soup.find_all('td')
        for i, td in enumerate(all_tds):
            td_text = clean_text(td.get_text())

            # Find Presenter label and get next td
            if td_text == 'Presenter' or 'प्रस्तुतकर्ता' in td_text:
                if i + 1 < len(all_tds):
                    value_td = all_tds[i + 1]
                    presenter = clean_text(value_td.get_text())
                    if presenter and not detail['presenter']:
                        detail['presenter'] = presenter

            # Find Ministry label and get next td
            if td_text == 'Ministry' or 'मन्त्रालय' in td_text:
                if i + 1 < len(all_tds):
                    value_td = all_tds[i + 1]
                    ministry = clean_text(value_td.get_text())
                    if ministry and not detail['ministry']:
                        detail['ministry'] = ministry

            # Registration Number
            if 'Registration No' in td_text or 'दर्ता नं' in td_text:
                if i + 1 < len(all_tds):
                    value = clean_text(all_tds[i + 1].get_text())
                    if value and not detail['registration_no']:
                        detail['registration_no'] = nepali_to_arabic(value)

            # Session
            if td_text == 'Session' or 'अधिवेशन' in td_text:
                if i + 1 < len(all_tds):
                    value = clean_text(all_tds[i + 1].get_text())
                    if value and not detail['session']:
                        detail['session'] = nepali_to_arabic(value)

            # Category (Governmental/Non-Governmental)
            if 'Governmental/Non Governmental' in td_text:
                if i + 1 < len(all_tds):
                    value = clean_text(all_tds[i + 1].get_text())
                    if value and not detail['bill_type']:
                        detail['bill_type'] = value.lower()

            # Original/Amendment
            if 'Original/Amendment' in td_text:
                if i + 1 < len(all_tds):
                    value = clean_text(all_tds[i + 1].get_text())
                    if value and not detail['original_or_amendment']:
                        detail['original_or_amendment'] = value.lower()

        # Clean up presenter name
        if detail['presenter']:
            # Remove "Hon." prefix
            presenter = detail['presenter']
            presenter = re.sub(r'^Hon\.?\s*', '', presenter, flags=re.IGNORECASE)
            presenter = re.sub(r'^माननीय\s*', '', presenter)
            detail['presenter'] = presenter.strip()

        logger.debug(f"Bill detail: presenter={detail['presenter']}, ministry={detail['ministry']}")
        return detail

    async def scrape_bills_with_details(
        self,
        bill_type: str = 'registered',
        chamber: str = 'hor',
        max_pages: int = 5,
        fetch_details: bool = True,
    ) -> List[BillData]:
        """
        Scrape bills with optional detail page fetching for presenter info.

        Args:
            bill_type: 'registered', 'passed', or 'state'
            chamber: 'hor' or 'na'
            max_pages: Maximum pages to scrape
            fetch_details: If True, fetch each bill's detail page for presenter info

        Returns:
            List of BillData objects with presenter information
        """
        # First get basic bill list
        bills = await self.scrape_bills(bill_type, chamber, max_pages)

        if not fetch_details:
            return bills

        # Now fetch detail pages to get presenter info
        logger.info(f"Fetching detail pages for {len(bills)} bills...")

        base_url = self.BASE_URLS[chamber]

        for i, bill in enumerate(bills):
            # Skip if we already have presenter
            if bill.presenting_mp_name:
                continue

            # Use the URL captured from the list page (stored in pdf_url for non-PDF links)
            bill_url = bill.pdf_url
            if not bill_url or bill_url.endswith('.pdf'):
                continue

            try:
                detail = await self.scrape_bill_detail(bill_url)
                if detail and detail.get('presenter'):
                    bill.presenting_mp_name = detail['presenter']
                    if detail.get('ministry') and not bill.ministry:
                        bill.ministry = detail['ministry']
                    logger.info(f"[{i+1}/{len(bills)}] {bill.title_en[:40]}... -> {detail['presenter']}")
                else:
                    logger.debug(f"[{i+1}/{len(bills)}] {bill.title_en[:40]}... -> no presenter found")
            except Exception as e:
                logger.warning(f"[{i+1}/{len(bills)}] Error fetching detail: {e}")

        presenter_count = sum(1 for b in bills if b.presenting_mp_name)
        logger.info(f"Found presenters for {presenter_count}/{len(bills)} bills")

        return bills

    # ============ Committee Scraping ============

    async def scrape_committees(self, chamber: str = 'hor') -> List[CommitteeData]:
        """
        Scrape committees and their members.

        Uses the committees page (not committees-2074) which has working member links.
        URL pattern: /en/committees/Committee-Name/members

        Args:
            chamber: 'hor' or 'na'

        Returns:
            List of CommitteeData objects
        """
        base_url = self.BASE_URLS.get(chamber)
        if not base_url:
            logger.error(f"Unknown chamber: {chamber}")
            return []

        # Use the main committees page (not committees-2074)
        list_url = f"{base_url}/en/committees"
        html = await self.fetch_page(list_url)
        if not html:
            return []

        committees = self._parse_committees(html, chamber)
        logger.info(f"Found {len(committees)} committees to scrape")

        # Fetch members for each committee using the full URL
        for committee in committees:
            if committee.external_id:
                # Build member URL: /en/committees/{slug}/members
                members_url = f"{base_url}/en/committees/{committee.external_id}/members"
                members_html = await self.fetch_page(members_url)
                if members_html:
                    committee.members = self._parse_committee_members(members_html)
                    logger.info(f"  {committee.name_en[:40]}: {len(committee.members)} members")

        logger.info(f"Scraped {len(committees)} committees from {chamber}")
        return committees

    def _parse_committees(self, html: str, chamber: str) -> List[CommitteeData]:
        """Parse committee list from HTML.

        Looks for links to /en/committees/{slug} and extracts committee info.
        """
        committees = []
        soup = BeautifulSoup(html, 'html.parser')
        seen_slugs = set()

        # Look for committee links - must be /en/committees/{slug} pattern
        for link in soup.find_all('a', href=True):
            href = link['href']

            # Match pattern: /en/committees/{slug} or full URL
            # Skip members/attendance subpages
            if '/committees/' not in href:
                continue
            if '/members' in href or '/attendance' in href:
                continue

            # Extract slug from URL
            # href could be: /en/committees/Finance-Committee or full URL
            parts = href.rstrip('/').split('/committees/')
            if len(parts) < 2:
                continue

            slug = parts[-1].split('/')[0]  # Get just the committee slug
            if not slug or slug in seen_slugs:
                continue

            # Skip list pages and navigation
            if slug in ['committees', 'committees-2074', 'en', 'np']:
                continue

            name_en = clean_text(link.get_text())
            if not name_en or len(name_en) < 5:
                continue

            seen_slugs.add(slug)

            # Determine committee type
            committee_type = 'thematic'
            name_lower = name_en.lower()
            if 'procedural' in name_lower or 'व्यवस्था' in name_en:
                committee_type = 'procedural'
            elif 'special' in name_lower or 'विशेष' in name_en:
                committee_type = 'special'
            elif 'joint' in name_lower or 'संयुक्त' in name_en:
                committee_type = 'joint'
            elif 'public account' in name_lower:
                committee_type = 'oversight'
            elif 'hearing' in name_lower:
                committee_type = 'procedural'

            committees.append(CommitteeData(
                external_id=slug,
                name_en=name_en,
                committee_type=committee_type,
                chamber=chamber,
            ))

        return committees

    def _parse_committee_members(self, html: str) -> List[Dict[str, Any]]:
        """Parse committee members from HTML.

        Parliament website uses table format with rows like:
        | Photo | <b><a>Hon. Name</a></b><br/> Party |

        Returns list of dicts with 'name', 'party', and 'role' keys.
        """
        members = []
        soup = BeautifulSoup(html, 'html.parser')

        # Find the members table (first table with "Photo" header)
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            if not rows:
                continue

            # Check if this is the members table
            header_text = rows[0].get_text().lower()
            if 'photo' not in header_text and 'introdution' not in header_text:
                continue

            # Parse member rows (skip header)
            for row in rows[1:]:
                cells = row.find_all('td')
                if len(cells) < 2:
                    continue

                cell = cells[1]

                # Extract name from <b><a> tag (structure: <b><a>Hon. Name</a></b><br/> Party)
                name_tag = cell.find('a')
                if not name_tag:
                    name_tag = cell.find('b')
                if not name_tag:
                    continue

                name_text = name_tag.get_text().strip()
                name = re.sub(r'^Hon\.?\s*', '', name_text, flags=re.IGNORECASE).strip()
                if not name or len(name) < 3:
                    continue

                # Extract party: text after <br/> tag
                party = None
                br_tag = cell.find('br')
                if br_tag and br_tag.next_sibling:
                    party_text = str(br_tag.next_sibling).strip()
                    if party_text:
                        party = party_text

                # If no party found, try getting text after the name
                if not party:
                    full_text = cell.get_text()
                    if name in full_text:
                        after_name = full_text.split(name)[-1].strip()
                        if after_name:
                            party = after_name

                # Determine role
                role = 'member'
                row_text = row.get_text().lower()
                if 'chairperson' in row_text or 'chair' in row_text:
                    if 'vice' in row_text:
                        role = 'vice_chair'
                    else:
                        role = 'chair'
                elif 'सभापति' in row.get_text():
                    if 'उप' in row.get_text():
                        role = 'vice_chair'
                    else:
                        role = 'chair'

                members.append({
                    'name': name,
                    'party': party,
                    'role': role,
                })

            # Only process first matching table
            if members:
                break

        logger.debug(f"Parsed {len(members)} committee members")

        return members

    # ============ Committee Attendance Scraping ============

    async def scrape_committee_attendance(
        self,
        committee_slug: str,
        chamber: str = 'hor',
        max_pages: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Scrape committee meeting attendance records.

        URL pattern: /en/committees/{slug}/meeting-attendance
        Returns list of dicts with meeting_date, attendees list.

        Note: Attendance data is often in linked PDFs, so this
        extracts what's available from the HTML listing.
        """
        base_url = self.BASE_URLS.get(chamber)
        if not base_url:
            return []

        url = f"{base_url}/en/committees/{committee_slug}/meeting-attendance"
        meetings = []

        for page_num in range(1, max_pages + 1):
            page_url = url if page_num == 1 else f"{url}?page={page_num}"
            html = await self.fetch_page(page_url)
            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')
            page_meetings = []

            for table in soup.find_all('table'):
                for row in table.find_all('tr'):
                    if row.find('th'):
                        continue
                    cells = row.find_all('td')
                    if len(cells) < 2:
                        continue

                    # Extract meeting info (typically: S.N., Title/Date, Attachment)
                    meeting_text = clean_text(row.get_text())
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', nepali_to_arabic(meeting_text))

                    meeting = {
                        'committee_slug': committee_slug,
                        'chamber': chamber,
                        'title': clean_text(cells[1].get_text()) if len(cells) > 1 else meeting_text,
                        'date': date_match.group(1) if date_match else None,
                    }

                    # Check for PDF attachment
                    link = row.find('a', href=True)
                    if link and link['href'].endswith('.pdf'):
                        meeting['pdf_url'] = link['href'] if link['href'].startswith('http') else urljoin(base_url, link['href'])

                    page_meetings.append(meeting)

            if not page_meetings:
                break
            meetings.extend(page_meetings)

        logger.info(f"Found {len(meetings)} meeting attendance records for {committee_slug}")
        return meetings

    # ============ Attendance Scraping ============

    async def scrape_attendance(self, chamber: str = 'hor') -> List[AttendanceRecord]:
        """
        Scrape session attendance from today-parliament page.

        Args:
            chamber: 'hor' or 'na'

        Returns:
            List of AttendanceRecord objects
        """
        url = self.ENDPOINTS.get(f'today_parliament_{chamber}')
        if not url:
            logger.error(f"Unknown chamber: {chamber}")
            return []

        html = await self.fetch_page(url)
        if not html:
            return []

        return self._parse_attendance(html, chamber)

    def _parse_attendance(self, html: str, chamber: str) -> List[AttendanceRecord]:
        """Parse attendance records from HTML."""
        records = []
        soup = BeautifulSoup(html, 'html.parser')
        today = date.today().isoformat()

        # Look for attendance section (हाजिरीको विवरण)
        attendance_section = soup.find(text=re.compile(r'हाजिरी|attendance', re.I))
        if attendance_section:
            parent = attendance_section.find_parent(['div', 'section', 'table'])
            if parent:
                soup = parent

        # Parse attendance table
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                if row.find('th'):
                    continue

                cells = row.find_all('td')
                if len(cells) < 2:
                    continue

                # Find member name
                name_cell = cells[0]
                mp_name = clean_text(name_cell.get_text())
                if not mp_name:
                    continue

                # Find attendance status
                present = False
                for cell in cells[1:]:
                    cell_text = cell.get_text().lower()
                    if 'present' in cell_text or 'उपस्थित' in cell.get_text() or '✓' in cell_text:
                        present = True
                        break
                    elif 'absent' in cell_text or 'अनुपस्थित' in cell.get_text():
                        present = False
                        break

                records.append(AttendanceRecord(
                    mp_name=mp_name,
                    session_date=today,
                    session_type='plenary',
                    present=present,
                    chamber=chamber,
                ))

        logger.info(f"Parsed {len(records)} attendance records from {chamber}")
        return records

    # ============ Video Archive Scraping ============

    async def scrape_videos(
        self,
        chamber: str = 'hor',
        max_pages: int = 10,
        max_sessions: int = 50,
    ) -> List[VideoRecord]:
        """
        Scrape parliament video archives to track who speaks in sessions.

        The video archive has two levels:
        1. Session list page (/en/videos) - lists parliament sessions
        2. Session detail page (/en/videos/Meeting-...) - lists individual speaker videos

        Individual speaker videos have titles like:
        - "Video - Ashok Kumar Chaudhari"
        - "भिडियो - मा. अशोक कुमार चौधरी"

        Args:
            chamber: 'hor' or 'na'
            max_pages: Maximum pages of sessions to scrape
            max_sessions: Maximum session detail pages to fetch

        Returns:
            List of VideoRecord objects with speaker information
        """
        url = self.ENDPOINTS.get(f'videos_{chamber}')
        if not url:
            logger.error(f"Unknown chamber for videos: {chamber}")
            return []

        base_url = self.BASE_URLS[chamber]

        # Step 1: Get session URLs from list pages
        session_urls = []
        for page_num in range(1, max_pages + 1):
            page_url = url if page_num == 1 else f"{url}?page={page_num}"

            html = await self.fetch_page(page_url)
            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')

            # Find session links (unique session pages)
            page_sessions = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/videos/' not in href:
                    continue

                # Build full URL
                session_url = href if href.startswith('http') else urljoin(base_url, href)

                # Skip list pages and duplicates
                if session_url.endswith('/videos') or session_url.endswith('/videos/'):
                    continue
                if '?page=' in session_url:
                    continue
                if session_url in session_urls:
                    continue

                session_urls.append(session_url)
                page_sessions.append(session_url)

            if not page_sessions:
                break

            logger.info(f"Page {page_num}: Found {len(page_sessions)} session URLs")

            if len(session_urls) >= max_sessions:
                session_urls = session_urls[:max_sessions]
                break

        logger.info(f"Total session URLs to fetch: {len(session_urls)}")

        # Step 2: Fetch each session's detail page to get individual speaker videos
        all_videos = []
        for i, session_url in enumerate(session_urls):
            html = await self.fetch_page(session_url)
            if not html:
                continue

            # Extract session date from URL
            session_date = None
            # URL format: /videos/Meeting-of-House-of-Representative-2025-Sep-04-thursday-...
            date_match = re.search(r'(\d{4})-([A-Za-z]+)-(\d{1,2})', session_url)
            if date_match:
                year, month_name, day = date_match.groups()
                month_map = {
                    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
                }
                month = month_map.get(month_name.lower()[:3], '01')
                session_date = f"{year}-{month}-{day.zfill(2)}"

            videos = self._parse_session_videos(html, chamber, session_date, session_url)
            all_videos.extend(videos)

            logger.info(f"[{i+1}/{len(session_urls)}] {session_url.split('/')[-1][:40]}... -> {len(videos)} speaker videos")

        logger.info(f"Total speaker videos scraped from {chamber}: {len(all_videos)}")
        return all_videos

    def _parse_session_videos(
        self,
        html: str,
        chamber: str,
        session_date: Optional[str],
        session_url: str,
    ) -> List[VideoRecord]:
        """Parse individual speaker videos from a session detail page.

        Looks for video items with titles like:
        - "Video - Ashok Kumar Chaudhari"
        - "भिडियो - मा. अशोक कुमार चौधरी"
        """
        videos = []
        soup = BeautifulSoup(html, 'html.parser')
        base_url = self.BASE_URLS[chamber]

        # Look for grid items with video content
        for item in soup.find_all(['div', 'article', 'li'], class_=re.compile(r'grid|video|media', re.I)):
            text = clean_text(item.get_text())

            # Skip session-level titles
            if 'Meeting of House' in text or 'बैठक' in text:
                continue

            # Look for speaker video patterns
            if 'Video -' not in text and 'भिडियो -' not in text and 'Video–' not in text:
                continue

            # Extract speaker name
            speaker_name, speaker_normalized = self._extract_speaker_from_title(text)

            if not speaker_name:
                continue

            # Get video link if available
            link = item.find('a', href=True)
            video_url = None
            if link:
                href = link['href']
                video_url = href if href.startswith('http') else urljoin(base_url, href)

            external_id = generate_id(video_url or f"{session_url}_{speaker_name}")

            videos.append(VideoRecord(
                external_id=external_id,
                title=text[:200],
                speaker_name=speaker_name,
                speaker_name_normalized=speaker_normalized,
                video_url=video_url,
                video_date=session_date,
                session_info=session_url.split('/')[-1] if session_url else None,
                chamber=chamber,
            ))

        return videos

    def _parse_videos(self, html: str, chamber: str) -> List[VideoRecord]:
        """Parse video records from HTML and extract speaker names.

        The parliament video archive has titles like:
        - "भिडियो - मा. अशोक कुमार चौधरी" (Video - Hon. Ashok Kumar Chaudhary)
        - "भिडियो - मा. डा. धवल शम्सेर ज.व.रा." (Video - Hon. Dr. Dhawal Shamsher J.B.R.)

        We extract the speaker name from these titles to track who speaks.
        """
        videos = []
        soup = BeautifulSoup(html, 'html.parser')
        base_url = self.BASE_URLS[chamber]

        # Look for video cards/items
        # Pattern 1: Look for links with video-related content
        for link in soup.find_all('a', href=True):
            href = link['href']

            # Skip non-video links
            if '/videos/' not in href and 'video' not in href.lower():
                continue

            # Get title
            title_text = clean_text(link.get_text())
            if not title_text or len(title_text) < 5:
                continue

            # Skip navigation/pagination links
            if title_text.isdigit() or title_text.lower() in ['next', 'previous', 'first', 'last']:
                continue

            video_url = href if href.startswith('http') else urljoin(base_url, href)
            external_id = generate_id(video_url)

            # Extract speaker name from title
            speaker_name, speaker_normalized = self._extract_speaker_from_title(title_text)

            videos.append(VideoRecord(
                external_id=external_id,
                title=title_text,
                speaker_name=speaker_name,
                speaker_name_normalized=speaker_normalized,
                video_url=video_url,
                chamber=chamber,
            ))

        # Pattern 2: Look for video cards in common layouts
        for card in soup.find_all(['div', 'article', 'li'], class_=re.compile(r'video|media|card', re.I)):
            link = card.find('a', href=True)
            if not link:
                continue

            href = link['href']
            video_url = href if href.startswith('http') else urljoin(base_url, href)
            external_id = generate_id(video_url)

            # Skip if already found
            if any(v.external_id == external_id for v in videos):
                continue

            # Get title from heading or link
            title_el = card.find(['h1', 'h2', 'h3', 'h4', 'h5']) or link
            title_text = clean_text(title_el.get_text()) if title_el else None
            if not title_text or len(title_text) < 5:
                continue

            # Extract speaker
            speaker_name, speaker_normalized = self._extract_speaker_from_title(title_text)

            # Try to find date
            video_date = None
            date_el = card.find(class_=re.compile(r'date|time', re.I))
            if date_el:
                date_text = clean_text(date_el.get_text())
                date_match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', nepali_to_arabic(date_text))
                if date_match:
                    video_date = date_match.group(0)

            videos.append(VideoRecord(
                external_id=external_id,
                title=title_text,
                speaker_name=speaker_name,
                speaker_name_normalized=speaker_normalized,
                video_url=video_url,
                video_date=video_date,
                chamber=chamber,
            ))

        # Pattern 3: Look for table rows with video content
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                if row.find('th'):
                    continue

                link = row.find('a', href=True)
                if not link:
                    continue

                href = link['href']
                video_url = href if href.startswith('http') else urljoin(base_url, href)
                external_id = generate_id(video_url)

                if any(v.external_id == external_id for v in videos):
                    continue

                title_text = clean_text(link.get_text())
                if not title_text or len(title_text) < 5:
                    continue

                speaker_name, speaker_normalized = self._extract_speaker_from_title(title_text)

                # Try to find date in other cells
                video_date = None
                for cell in row.find_all('td'):
                    cell_text = clean_text(cell.get_text())
                    date_match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', nepali_to_arabic(cell_text))
                    if date_match:
                        video_date = date_match.group(0)
                        break

                videos.append(VideoRecord(
                    external_id=external_id,
                    title=title_text,
                    speaker_name=speaker_name,
                    speaker_name_normalized=speaker_normalized,
                    video_url=video_url,
                    video_date=video_date,
                    chamber=chamber,
                ))

        logger.info(f"Parsed {len(videos)} video records from {chamber}")
        return videos

    def _extract_speaker_from_title(self, title: str) -> tuple[Optional[str], Optional[str]]:
        """
        Extract speaker name from video title.

        Patterns:
        - "भिडियो - मा. अशोक कुमार चौधरी" -> "अशोक कुमार चौधरी"
        - "Video - Hon. Ashok Kumar Chaudhary" -> "Ashok Kumar Chaudhary"
        - "भिडियो - मा. डा. धवल शम्सेर ज.व.रा." -> "धवल शम्सेर"

        Returns:
            Tuple of (raw_speaker_name, normalized_speaker_name)
        """
        if not title:
            return None, None

        speaker_name = None
        normalized = None

        # Nepali pattern: भिडियो - मा. Name
        nepali_patterns = [
            r'भिडियो\s*[-–—]\s*मा\.?\s*(.+)',  # "भिडियो - मा. Name"
            r'भिडियो\s*[-–—]\s*(.+)',  # "भिडियो - Name"
            r'मा\.?\s+(.+)',  # Just "मा. Name"
        ]

        for pattern in nepali_patterns:
            match = re.search(pattern, title)
            if match:
                speaker_name = match.group(1).strip()
                break

        # English pattern: Video - Hon. Name
        if not speaker_name:
            english_patterns = [
                r'Video\s*[-–—]\s*Hon\.?\s*(.+)',
                r'Video\s*[-–—]\s*(.+)',
                r'Hon\.?\s+(.+)',
            ]

            for pattern in english_patterns:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    speaker_name = match.group(1).strip()
                    break

        if speaker_name:
            # Normalize the name
            normalized = speaker_name

            # Remove honorifics
            honorifics_ne = ['डा.', 'डा ', 'प्रा.', 'प्रा ', 'श्री', 'माननीय', 'मा.', 'मा ']
            honorifics_en = ['Dr.', 'Dr ', 'Prof.', 'Prof ', 'Mr.', 'Mrs.', 'Ms.', 'Hon.', 'Hon ']

            for h in honorifics_ne + honorifics_en:
                normalized = normalized.replace(h, '')

            # Remove trailing abbreviations like "ज.व.रा." (J.B.R.)
            normalized = re.sub(r'\s+[ज-ज़]\.[व-व़]\.[र-ऱ]\.?$', '', normalized)
            normalized = re.sub(r'\s+J\.?B\.?R\.?$', '', normalized, flags=re.IGNORECASE)

            # Clean up whitespace
            normalized = ' '.join(normalized.split())

        # Filter out non-person entries (procedural items, office names, etc.)
        non_person_keywords = [
            # Procedural items (English)
            'zero hour', 'speaker', 'prastav', 'prastut', 'nirnay',
            'question', 'answer', 'jawapha', 'motion', 'resolution',
            'pratibedan', 'report', 'uttar', 'karyakram', 'program',
            'tebul', 'table',  # "Table" for tabling items
            # Office/ministry names
            'karyalaya', 'mantralaya', 'ministry', 'office',
            'pradhanmantri', 'prime minister', 'rastrapati', 'president',
            'patra', 'letter', 'notice',
            # Session items
            'meeting', 'session', 'baithak', 'बैठक',
            # Other procedural
            'agenda', 'business', 'order', 'pesh',
            # Nepali procedural
            'प्रतिवेदन', 'प्रश्न', 'उत्तर', 'कार्यक्रम',
        ]

        speaker_lower = speaker_name.lower() if speaker_name else ''
        for keyword in non_person_keywords:
            if keyword in speaker_lower:
                return None, None

        # Skip if result is too short (likely not a real name)
        if normalized and len(normalized) < 3:
            return None, None

        return speaker_name, normalized

    async def count_speeches_by_mp(
        self,
        chamber: str = 'hor',
        max_pages: int = 20,
    ) -> Dict[str, int]:
        """
        Count how many times each MP appears in video archives (speeches).

        Returns:
            Dict mapping normalized speaker names to speech counts
        """
        videos = await self.scrape_videos(chamber, max_pages)

        speech_counts: Dict[str, int] = {}
        for video in videos:
            if video.speaker_name_normalized:
                name = video.speaker_name_normalized
                speech_counts[name] = speech_counts.get(name, 0) + 1

        # Sort by count descending
        sorted_counts = dict(sorted(speech_counts.items(), key=lambda x: x[1], reverse=True))

        logger.info(f"Found speech counts for {len(sorted_counts)} unique speakers")
        return sorted_counts

    # ============ Full Sync Methods ============

    async def sync_all_members(self) -> Dict[str, List[MPProfile]]:
        """
        Sync all members from both houses.

        Returns:
            Dict with 'hor' and 'na' keys containing member lists
        """
        results = {}
        for chamber in ['hor', 'na']:
            try:
                members = await self.scrape_members(chamber)
                results[chamber] = members
            except Exception as e:
                logger.error(f"Error scraping {chamber} members: {e}")
                results[chamber] = []

        return results

    async def sync_all_bills(self) -> Dict[str, List[BillData]]:
        """
        Sync all bills from both houses.

        Returns:
            Dict with chamber_type keys containing bill lists
        """
        results = {}
        for chamber in ['hor', 'na']:
            for bill_type in ['registered', 'passed']:
                key = f"{chamber}_{bill_type}"
                try:
                    bills = await self.scrape_bills(bill_type=bill_type, chamber=chamber)
                    results[key] = bills
                except Exception as e:
                    logger.error(f"Error scraping {key} bills: {e}")
                    results[key] = []

        return results


# ============ Async Functions for Service Integration ============

async def fetch_parliament_members_async(chamber: str = 'hor') -> List[Dict[str, Any]]:
    """Fetch parliament members asynchronously."""
    from dataclasses import asdict
    async with ParliamentScraper() as scraper:
        members = await scraper.scrape_members(chamber)
        return [asdict(m) for m in members]


async def fetch_parliament_bills_async(
    bill_type: str = 'registered',
    chamber: str = 'hor',
) -> List[Dict[str, Any]]:
    """Fetch parliament bills asynchronously."""
    from dataclasses import asdict
    async with ParliamentScraper() as scraper:
        bills = await scraper.scrape_bills(bill_type=bill_type, chamber=chamber)
        return [asdict(b) for b in bills]


async def fetch_parliament_committees_async(chamber: str = 'hor') -> List[Dict[str, Any]]:
    """Fetch parliament committees asynchronously."""
    from dataclasses import asdict
    async with ParliamentScraper() as scraper:
        committees = await scraper.scrape_committees(chamber)
        return [asdict(c) for c in committees]


async def fetch_parliament_videos_async(
    chamber: str = 'hor',
    max_pages: int = 10,
) -> List[Dict[str, Any]]:
    """Fetch parliament video archives asynchronously."""
    from dataclasses import asdict
    async with ParliamentScraper() as scraper:
        videos = await scraper.scrape_videos(chamber, max_pages)
        return [asdict(v) for v in videos]


async def count_mp_speeches_async(chamber: str = 'hor', max_pages: int = 20) -> Dict[str, int]:
    """Count speeches per MP from video archives."""
    async with ParliamentScraper() as scraper:
        return await scraper.count_speeches_by_mp(chamber, max_pages)


# ============ CLI ============

async def main():
    """CLI entry point for testing."""
    print("=" * 60)
    print("Nepal Parliament Scraper")
    print("=" * 60)
    print("\nEndpoints:")
    for key in ParliamentScraper.ENDPOINTS:
        print(f"  - {key}")
    print()

    print("[1] Scraping House of Representatives members...")
    async with ParliamentScraper() as scraper:
        members = await scraper.scrape_members('hor')
        print(f"\nFound {len(members)} HoR members:")
        print("-" * 60)

        for i, member in enumerate(members[:5], 1):
            print(f"[{i}] {member.name_en}")
            print(f"    Party: {member.party}")
            print(f"    Constituency: {member.constituency}")
            print(f"    Profile: {member.profile_url}")
            print()

        if len(members) > 5:
            print(f"... and {len(members) - 5} more")

        print("\n[2] Scraping registered bills...")
        bills = await scraper.scrape_bills(bill_type='registered', chamber='hor', max_pages=1)
        print(f"\nFound {len(bills)} registered bills:")
        for i, bill in enumerate(bills[:3], 1):
            print(f"[{i}] {bill.title_en[:60]}")
            print(f"    Status: {bill.status}")
            print(f"    Date: {bill.presented_date}")
            print()

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
