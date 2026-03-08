"""Nepal Electricity Authority (NEA) energy data scraper.

Scrapes energy supply/demand data from https://www.nea.org.np
The website displays a panel showing:
- NEA Subsidiary Companies (MWh)
- IPP - Independent Power Producers (MWh)
- Import from India (MWh)
- Interruption/Outages (MWh)
- Total Energy Demand (MWh)
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.models.energy_data import EnergyDataType, NEA_LABEL_MAPPING

logger = logging.getLogger(__name__)

NEA_URL = "https://www.nea.org.np"


@dataclass
class FetchedEnergyData:
    """Container for fetched energy data from NEA."""
    nea_subsidiary: Optional[Decimal] = None
    ipp: Optional[Decimal] = None
    energy_import: Optional[Decimal] = None
    interruption: Optional[Decimal] = None
    total_demand: Optional[Decimal] = None
    fetched_at: datetime = None
    source_url: str = NEA_URL

    def __post_init__(self):
        if self.fetched_at is None:
            self.fetched_at = datetime.now(timezone.utc)

    def has_any_data(self) -> bool:
        """Check if any data was fetched."""
        return any([
            self.nea_subsidiary,
            self.ipp,
            self.energy_import,
            self.interruption,
            self.total_demand,
        ])

    def to_items(self) -> list[tuple[EnergyDataType, Decimal]]:
        """Convert to list of (data_type, value) tuples."""
        items = []
        if self.nea_subsidiary is not None:
            items.append((EnergyDataType.NEA_SUBSIDIARY, self.nea_subsidiary))
        if self.ipp is not None:
            items.append((EnergyDataType.IPP, self.ipp))
        if self.energy_import is not None:
            items.append((EnergyDataType.IMPORT, self.energy_import))
        if self.interruption is not None:
            items.append((EnergyDataType.INTERRUPTION, self.interruption))
        if self.total_demand is not None:
            items.append((EnergyDataType.TOTAL_DEMAND, self.total_demand))
        return items


def extract_number(text: str) -> Optional[Decimal]:
    """Extract decimal number from text like '5,968 MWh' or '18540 MWh'."""
    # Remove commas and extract number
    cleaned = re.sub(r'[^\d.]', '', text.replace(',', ''))
    if cleaned:
        try:
            return Decimal(cleaned)
        except Exception:
            pass
    return None


def normalize_label(text: str) -> Optional[EnergyDataType]:
    """Normalize label text to EnergyDataType."""
    normalized = text.lower().strip()
    # Remove trailing dashes or special characters
    normalized = re.sub(r'[\s\-–—]+$', '', normalized)

    for label, data_type in NEA_LABEL_MAPPING.items():
        if label in normalized or normalized in label:
            return data_type
    return None


async def fetch_nea_energy_data() -> Optional[FetchedEnergyData]:
    """Fetch energy data from NEA website.

    Returns:
        FetchedEnergyData with energy values, or None if fetch failed.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try multiple URLs - NEA sometimes has different endpoints
            urls_to_try = [
                NEA_URL,
                "https://nea.org.np",
                "https://www.nea.org.np/live",
                "https://www.nea.org.np/loadshedding",
            ]

            response = None
            for url in urls_to_try:
                try:
                    response = await client.get(
                        url,
                        headers={
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                            "Accept-Language": "en-US,en;q=0.9,ne;q=0.8",
                            "Accept-Encoding": "gzip, deflate, br",
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Cache-Control": "no-cache",
                            "Pragma": "no-cache",
                            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                            "Sec-Ch-Ua-Mobile": "?0",
                            "Sec-Ch-Ua-Platform": '"macOS"',
                            "Sec-Fetch-Dest": "document",
                            "Sec-Fetch-Mode": "navigate",
                            "Sec-Fetch-Site": "none",
                            "Sec-Fetch-User": "?1",
                            "Upgrade-Insecure-Requests": "1",
                        },
                        follow_redirects=True,
                    )
                    if response.status_code == 200 and "Request Rejected" not in response.text:
                        logger.info(f"Successfully fetched NEA data from {url}")
                        break
                    response = None
                except Exception as e:
                    logger.debug(f"Failed to fetch {url}: {e}")
                    continue

            if not response:
                logger.warning("All NEA URLs failed or were blocked")
                return None

            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            result = FetchedEnergyData()

            # Strategy 1: Look for Energy Details section/panel
            # The website has an "Energy Details" section showing values like:
            # "Interruption – 400 MWh"
            # "Total Energy Demand – 38716 MWh"
            # "NEA Subsidiary Companies – 6022 MWh"
            # "IPP – 17986 MWh"
            # "Import – 8439 MWh"

            # Get full page text
            text = soup.get_text()

            # Multiple patterns to match the format "Label – Value MWh"
            patterns = [
                # Pattern: "Label – Value MWh" (em dash)
                r'(NEA\s+Subsidiary\s+Companies?|NEA|IPP|Import|Interruption|Total\s+Energy\s+Demand)\s*[–\-—:]\s*([\d,]+)\s*MWh',
                # Pattern with extra whitespace
                r'(NEA\s+Subsidiary\s+Companies?|NEA|IPP|Import|Interruption|Total\s+Energy\s+Demand)\s+[\–\-—:]\s+([\d,]+)\s+MWh',
            ]

            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    label, value_str = match
                    label_lower = label.lower().strip()
                    value = extract_number(value_str)

                    if value:
                        # Map labels to data types
                        if 'subsidiary' in label_lower:
                            result.nea_subsidiary = result.nea_subsidiary or value
                        elif label_lower == 'nea':
                            # "NEA" alone might be separate from "NEA Subsidiary"
                            # Skip if we already have subsidiary data
                            pass
                        elif 'ipp' in label_lower:
                            result.ipp = result.ipp or value
                        elif 'import' in label_lower:
                            result.energy_import = result.energy_import or value
                        elif 'interruption' in label_lower:
                            result.interruption = result.interruption or value
                        elif 'total' in label_lower and 'demand' in label_lower:
                            result.total_demand = result.total_demand or value

            # Strategy 2: Look for tables or structured data
            if not result.has_any_data():
                # Try finding in tables
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        cell_texts = [cell.get_text().strip() for cell in cells]
                        row_text = ' '.join(cell_texts)

                        # Check if this row contains energy data
                        for label_pattern, data_type in NEA_LABEL_MAPPING.items():
                            if label_pattern in row_text.lower():
                                # Find the MWh value in this row
                                for cell_text in cell_texts:
                                    if 'mwh' in cell_text.lower():
                                        value = extract_number(cell_text)
                                        if value:
                                            if data_type == EnergyDataType.NEA_SUBSIDIARY:
                                                result.nea_subsidiary = value
                                            elif data_type == EnergyDataType.IPP:
                                                result.ipp = value
                                            elif data_type == EnergyDataType.IMPORT:
                                                result.energy_import = value
                                            elif data_type == EnergyDataType.INTERRUPTION:
                                                result.interruption = value
                                            elif data_type == EnergyDataType.TOTAL_DEMAND:
                                                result.total_demand = value
                                            break

            # Strategy 3: Look for div/span elements with specific classes
            if not result.has_any_data():
                # Look for elements containing both label and value
                for element in soup.find_all(['div', 'span', 'li', 'p']):
                    element_text = element.get_text()
                    if 'mwh' in element_text.lower():
                        # Try to extract label and value
                        for pattern in patterns:
                            match = re.search(pattern, element_text, re.IGNORECASE)
                            if match:
                                label, value_str = match.groups()
                                data_type = normalize_label(label)
                                value = extract_number(value_str)

                                if data_type and value:
                                    if data_type == EnergyDataType.NEA_SUBSIDIARY:
                                        result.nea_subsidiary = result.nea_subsidiary or value
                                    elif data_type == EnergyDataType.IPP:
                                        result.ipp = result.ipp or value
                                    elif data_type == EnergyDataType.IMPORT:
                                        result.energy_import = result.energy_import or value
                                    elif data_type == EnergyDataType.INTERRUPTION:
                                        result.interruption = result.interruption or value
                                    elif data_type == EnergyDataType.TOTAL_DEMAND:
                                        result.total_demand = result.total_demand or value

            if result.has_any_data():
                logger.info(
                    f"NEA data fetched: NEA={result.nea_subsidiary}, IPP={result.ipp}, "
                    f"Import={result.energy_import}, Interruption={result.interruption}, "
                    f"TotalDemand={result.total_demand}"
                )
                return result
            else:
                logger.warning("Could not extract energy data from NEA website")
                return None

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching NEA data: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching NEA data: {e}")
        return None


async def fetch_nea_summary() -> Optional[dict]:
    """Fetch NEA energy summary for API.

    Returns:
        Dict with energy values or None if fetch failed.
    """
    data = await fetch_nea_energy_data()
    if data:
        return {
            "nea_subsidiary": float(data.nea_subsidiary) if data.nea_subsidiary else None,
            "ipp": float(data.ipp) if data.ipp else None,
            "import": float(data.energy_import) if data.energy_import else None,
            "interruption": float(data.interruption) if data.interruption else None,
            "total_demand": float(data.total_demand) if data.total_demand else None,
            "unit": "MWh",
            "source": "Nepal Electricity Authority",
            "source_url": NEA_URL,
            "fetched_at": data.fetched_at.isoformat(),
        }
    return None
