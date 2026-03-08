#!/usr/bin/env python3
"""
Bolpatra (e-GP) Government Contract Scraper

Scrapes e-Contract search results from Nepal's public procurement portal
(bolpatra.gov.np). This is public transparency data — government contracts
with award amounts, contractor names, and procuring entities.
"""

import re
import hashlib
import logging
import time
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field

import requests
from bs4 import BeautifulSoup
import urllib3

# Suppress SSL warnings for Nepal govt sites
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class BolpatraContract:
    """Structured data for a single contract from bolpatra.gov.np."""
    ifb_number: str
    project_name: str
    procuring_entity: str
    procurement_type: str
    contract_award_date: Optional[str] = None  # DD-MM-YYYY raw string
    contract_amount_npr: Optional[float] = None
    contractor_name: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)


class BolpatraScraper:
    """
    Scraper for bolpatra.gov.np e-GP (electronic Government Procurement) portal.

    Fetches e-Contract search results — public transparency data on
    government contracts with award amounts, contractor names, and procuring entities.
    """

    BASE_URL = "https://bolpatra.gov.np/egp"
    # Step 1: GET this page to establish session/cookies
    SESSION_URL = f"{BASE_URL}/search-Econtact"
    # Step 2: POST AJAX to this endpoint to fetch contract data
    SEARCH_URL = f"{BASE_URL}/getNextContractListToView"

    def __init__(self, delay: float = 0.5):
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ne;q=0.8',
        })
        self.delay = delay

    def scrape_contracts(self, page_size: int = 5000) -> List[BolpatraContract]:
        """
        Fetch all e-Contract records from bolpatra.gov.np.

        Two-step process:
        1. GET the e-Contract search page to establish session
        2. POST the AJAX endpoint with empty filters to get all records

        Args:
            page_size: Number of records per page. 5000 fetches all records in one request.

        Returns:
            List of BolpatraContract dataclass objects.
        """
        logger.info(f"Fetching contracts from bolpatra.gov.np (page_size={page_size})")

        try:
            # Step 1: Establish session by visiting the e-Contract search page
            time.sleep(self.delay)
            self.session.get(self.SESSION_URL, timeout=60)

            # Step 2: AJAX POST to fetch contract list (empty filters = all records)
            time.sleep(self.delay)
            response = self.session.post(
                self.SEARCH_URL,
                data={
                    "contractAwardTO.publicEntityTitle": "",
                    "contractAwardTO.publicEntity": "",
                    "contractAwardTO.contractorNameTitle": "",
                    "contractAwardTO.contractorName": "",
                    "contractAwardTO.contractAwardDateFrom": "",
                    "contractAwardTO.contractAwardDateTo": "",
                    "contractAwardTO.contractAwardValueFrom": "",
                    "contractAwardTO.contractAwardValueTo": "",
                    "contractAwardTO.Proc_CategoryId": "-1",
                    "contractAwardTO.Proc_Method_Id": "-1",
                    "currentPageIndexInput": "1",
                    "pageSizeInput": str(page_size),
                    "pageActionInput": "first",
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=120,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch bolpatra contracts: {e}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        contracts = self._parse_contracts_table(soup)
        logger.info(f"Parsed {len(contracts)} contracts from bolpatra")
        return contracts

    def _parse_contracts_table(self, soup: BeautifulSoup) -> List[BolpatraContract]:
        """Parse HTML table rows into BolpatraContract objects."""
        contracts = []

        table = soup.find('table')
        if not table:
            logger.warning("No table found in bolpatra response")
            return contracts

        tbody = table.find('tbody') or table
        rows = tbody.find_all('tr')
        logger.info(f"Found {len(rows)} table rows")

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 7:
                continue

            try:
                # Extract 7 columns: SN, IFB No, Project Name, PE Name, Procurement Type,
                # Contract Award Date, Contract Amount (NRs), Contractor Name
                # Note: first column may be S.N. (serial number)
                raw_texts = [cell.get_text(strip=True) for cell in cells]

                # Determine offset: if first cell is a number (SN), skip it
                offset = 0
                if raw_texts[0].isdigit() and len(cells) >= 8:
                    offset = 1

                ifb_number = raw_texts[offset + 0]
                project_name = raw_texts[offset + 1]
                procuring_entity = raw_texts[offset + 2]
                procurement_type = raw_texts[offset + 3]
                award_date_str = raw_texts[offset + 4]
                amount_str = raw_texts[offset + 5]
                contractor_name = raw_texts[offset + 6]

                if not ifb_number or not project_name:
                    continue

                contract = BolpatraContract(
                    ifb_number=ifb_number,
                    project_name=project_name,
                    procuring_entity=procuring_entity,
                    procurement_type=procurement_type,
                    contract_award_date=award_date_str if award_date_str else None,
                    contract_amount_npr=self._parse_amount(amount_str),
                    contractor_name=contractor_name,
                    raw_data={
                        "all_columns": raw_texts,
                        "award_date_raw": award_date_str,
                        "amount_raw": amount_str,
                    },
                )
                contracts.append(contract)
            except (IndexError, ValueError) as e:
                logger.debug(f"Skipping row: {e}")
                continue

        return contracts

    @staticmethod
    def _parse_amount(text: str) -> Optional[float]:
        """Parse comma-formatted amount string to float.

        Examples:
            '2,608,928.00' → 2608928.0
            '15,00,000.00' → 1500000.0
            '' → None
        """
        if not text or not text.strip():
            return None
        try:
            cleaned = text.strip().replace(',', '')
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_date(text: str) -> Optional[date]:
        """Parse DD-MM-YYYY date string to date object.

        Examples:
            '02-06-2025' → date(2025, 6, 2)
            '' → None
        """
        if not text or not text.strip():
            return None
        try:
            return datetime.strptime(text.strip(), "%d-%m-%Y").date()
        except (ValueError, TypeError):
            # Try alternate format YYYY-MM-DD
            try:
                return datetime.strptime(text.strip(), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return None

    @staticmethod
    def _extract_fiscal_year(ifb_no: str) -> Optional[str]:
        """Extract Nepali fiscal year from IFB number.

        Examples:
            '07/081/082' → '081/082'
            'KUKL/BB/2081/082/02' → '081/082'
            'NCB-01/080/81' → '080/081'
            '2081/082' → '081/082'
            'GWRIDD/MAINTENANCE/SQ/09/2082-83' → '082/083'
        """
        if not ifb_no:
            return None

        # Pattern 1: explicit 3-digit/3-digit with / or - (e.g., 081/082 or 081-082)
        match = re.search(r'(0\d{2})\s*[/-]\s*(0\d{2})', ifb_no)
        if match:
            return f"{match.group(1)}/{match.group(2)}"

        # Pattern 2: 4-digit year / 3-digit (e.g., 2081/082 or 2081-082)
        match = re.search(r'(20\d{2})\s*[/-]\s*(0\d{2})', ifb_no)
        if match:
            year_short = match.group(1)[-3:]  # 2081 → 081
            return f"{year_short}/{match.group(2)}"

        # Pattern 3: 4-digit year / 4-digit year (e.g., 2081/2082)
        match = re.search(r'(20\d{2})\s*[/-]\s*(20\d{2})', ifb_no)
        if match:
            year_short = match.group(1)[-3:]  # 2081 → 081
            second_short = match.group(2)[-3:]  # 2082 → 082
            return f"{year_short}/{second_short}"

        # Pattern 4: 4-digit year - 2-digit (e.g., 2082-83)
        match = re.search(r'(20\d{2})\s*[/-]\s*(\d{2})(?!\d)', ifb_no)
        if match:
            year_short = match.group(1)[-3:]  # 2082 → 082
            second = match.group(2)
            second = f"0{second}"
            return f"{year_short}/{second}"

        # Pattern 5: 3-digit/2-digit (e.g., 080/81)
        match = re.search(r'(0\d{2})\s*[/-]\s*(\d{2})(?!\d)', ifb_no)
        if match:
            first = match.group(1)
            second = match.group(2)
            if len(second) == 2:
                second = f"0{second}"
            return f"{first}/{second}"

        # Pattern 6: 2-digit/2-digit at end (e.g., 78/79, 80-81)
        match = re.search(r'(\d{2})\s*[/-]\s*(\d{2})(?!\d)', ifb_no)
        if match:
            first = match.group(1)
            second = match.group(2)
            # Validate it looks like a fiscal year (consecutive years in 70-89 range)
            try:
                f_int, s_int = int(first), int(second)
                if 70 <= f_int <= 89 and s_int == f_int + 1:
                    return f"0{first}/0{second}"
            except ValueError:
                pass

        return None

    @staticmethod
    def generate_external_id(ifb_number: str, procuring_entity: str) -> str:
        """Generate a deterministic external ID for deduplication.

        Uses hash of ifb_number + procuring_entity to handle cases
        where different entities may reuse the same IFB number format.
        """
        key = f"{ifb_number.strip()}|{procuring_entity.strip()}"
        return hashlib.sha256(key.encode()).hexdigest()[:40]


# ============ Async wrapper for FastAPI ============

async def scrape_bolpatra_async(page_size: int = 5000) -> List[Dict[str, Any]]:
    """
    Async wrapper for Bolpatra scraping.

    For use in FastAPI endpoints — runs sync code in executor.
    """
    import asyncio

    def _scrape():
        scraper = BolpatraScraper(delay=0.5)
        contracts = scraper.scrape_contracts(page_size=page_size)
        return [asdict(c) for c in contracts]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape)


# ============ CLI ============

def main():
    print("=" * 60)
    print("Bolpatra (e-GP) Government Contract Scraper")
    print("=" * 60)

    scraper = BolpatraScraper(delay=0.5)

    print("\nFetching contracts from bolpatra.gov.np...")
    contracts = scraper.scrape_contracts(page_size=100)

    print(f"\nFound {len(contracts)} contracts:")
    print("-" * 60)

    for i, c in enumerate(contracts[:10], 1):
        print(f"[{i}] {c.project_name[:60]}")
        print(f"    IFB: {c.ifb_number}")
        print(f"    PE: {c.procuring_entity}")
        print(f"    Type: {c.procurement_type}")
        print(f"    Amount: NRs {c.contract_amount_npr:,.2f}" if c.contract_amount_npr else "    Amount: N/A")
        print(f"    Contractor: {c.contractor_name}")
        print(f"    Date: {c.contract_award_date}")
        fy = BolpatraScraper._extract_fiscal_year(c.ifb_number)
        print(f"    FY: {fy}")
        print()

    if len(contracts) > 10:
        print(f"... and {len(contracts) - 10} more")


if __name__ == "__main__":
    main()
