"""NEPSE (Nepal Stock Exchange) index scraper.

Primary source: merolagani.com/Indices.aspx
Fallback: sharesansar.com
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MEROLAGANI_INDICES_URL = "https://merolagani.com/Indices.aspx"
SHARESANSAR_URL = "https://www.sharesansar.com/"


@dataclass
class NepseIndex:
    """NEPSE index data."""
    value: Decimal
    change_points: Decimal
    change_percent: Decimal
    date: datetime
    source: str


def extract_number(text: str) -> Optional[Decimal]:
    """Extract decimal number from text like '2,731.59' or '+5.08'."""
    # Remove commas and extract number
    cleaned = re.sub(r'[^\d.\-+]', '', text.replace(',', ''))
    if cleaned:
        try:
            return Decimal(cleaned)
        except Exception:
            pass
    return None


async def fetch_from_merolagani() -> Optional[NepseIndex]:
    """Fetch NEPSE index from merolagani.com."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                MEROLAGANI_INDICES_URL,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                },
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            index_value = None
            change_points = None
            change_percent = None

            # Strategy 1: Look for the data table with date, index, change columns
            # Merolagani table format: # | Date (AD) | Index Value | Absolute Change | % Change
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows[1:]:  # Skip header row
                    cells = row.find_all(["td"])
                    if len(cells) >= 5:
                        cell_texts = [cell.get_text().strip() for cell in cells]

                        # Check if second cell looks like a date (YYYY/MM/DD)
                        date_cell = cell_texts[1] if len(cell_texts) > 1 else ""
                        if re.match(r'\d{4}/\d{2}/\d{2}', date_cell):
                            # This is a data row with format: [#, date, value, change, percent]
                            # Cell 2: Index value (e.g., "2,695.73")
                            if len(cell_texts) > 2:
                                val = extract_number(cell_texts[2])
                                if val and val > 1000 and val < 10000:
                                    index_value = val

                            # Cell 3: Absolute change (e.g., "1.53" or "-5.23")
                            if len(cell_texts) > 3:
                                change_points = extract_number(cell_texts[3])

                            # Cell 4: Percentage change (e.g., "0.05%" or "-0.19%")
                            if len(cell_texts) > 4:
                                pct_text = cell_texts[4].replace('%', '')
                                change_percent = extract_number(pct_text)

                            if index_value:
                                break
                    if index_value:
                        break
                if index_value:
                    break

            # Strategy 2: Look for specific class/id patterns
            if not index_value:
                # Try to find index in common class names
                for class_name in ['index-value', 'nepse-value', 'current-value']:
                    elem = soup.find(class_=re.compile(class_name, re.I))
                    if elem:
                        val = extract_number(elem.get_text())
                        if val and val > 1000 and val < 10000:
                            index_value = val
                            break

            # Strategy 3: Regex fallback on page text
            if not index_value:
                text = soup.get_text()
                # Look for index values in typical NEPSE range
                index_matches = re.findall(r'(\d{1},?\d{3}\.\d{2})', text)
                for match in index_matches:
                    val = extract_number(match)
                    if val and val > 1500 and val < 5000:  # More typical NEPSE range
                        index_value = val
                        break

            # Try to extract change values if not found
            if index_value and change_percent is None:
                text = soup.get_text()
                # Look for percentage values
                pct_matches = re.findall(r'([+\-]?\d+\.\d+)\s*%', text)
                for match in pct_matches:
                    pct = extract_number(match)
                    if pct and abs(pct) < 10:
                        change_percent = pct
                        break

            if index_value:
                logger.info(f"NEPSE index found: {index_value}, change: {change_points}, pct: {change_percent}")
                return NepseIndex(
                    value=index_value,
                    change_points=change_points or Decimal(0),
                    change_percent=change_percent or Decimal(0),
                    date=datetime.now(timezone.utc),
                    source="merolagani.com",
                )

            logger.warning("Could not find NEPSE index value on merolagani.com")
            return None

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching NEPSE from merolagani: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching NEPSE from merolagani: {e}")
        return None


async def fetch_from_nepalstock() -> Optional[NepseIndex]:
    """Fetch NEPSE index from official nepalstock.com.np API."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try the official NEPSE API
            response = await client.get(
                "https://www.nepalstock.com.np/api/nots/nepse-index",
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                },
            )
            response.raise_for_status()

            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                latest = data[0]  # First item is most recent
                index_value = extract_number(str(latest.get("currentValue", "")))
                change_points = extract_number(str(latest.get("change", "")))
                change_percent = extract_number(str(latest.get("perChange", "")))

                if index_value and index_value > 1000:
                    logger.info(f"NEPSE from nepalstock.com.np: {index_value}")
                    return NepseIndex(
                        value=index_value,
                        change_points=change_points or Decimal(0),
                        change_percent=change_percent or Decimal(0),
                        date=datetime.now(timezone.utc),
                        source="nepalstock.com.np",
                    )
            return None

    except Exception as e:
        logger.debug(f"Could not fetch from nepalstock.com.np: {e}")
        return None


async def fetch_nepse_index() -> Optional[NepseIndex]:
    """Fetch NEPSE index data.

    Tries multiple sources in order:
    1. nepalstock.com.np (official API)
    2. merolagani.com (web scraping)
    """
    # Try official NEPSE API first
    result = await fetch_from_nepalstock()
    if result:
        return result

    # Try merolagani
    result = await fetch_from_merolagani()
    if result:
        return result

    logger.warning("Could not fetch NEPSE index from any source")
    return None


async def fetch_nepse_summary() -> Optional[dict]:
    """Fetch NEPSE index summary for API.

    Returns:
        Dict with 'value', 'change', 'change_percent', 'date' or None
    """
    index = await fetch_nepse_index()
    if index:
        return {
            "value": float(index.value),
            "change": float(index.change_points),
            "change_percent": float(index.change_percent),
            "date": index.date,
            "source": index.source,
            "source_url": MEROLAGANI_INDICES_URL,
        }
    return None
