"""Nepal Oil Corporation (NOC) fuel price scraper.

URL: https://noc.org.np/retailprice
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

NOC_RETAIL_URL = "https://noc.org.np/retailprice"


@dataclass
class FuelPrices:
    """Fuel price data from NOC."""
    petrol: Decimal  # Per litre
    diesel: Decimal  # Per litre
    kerosene: Decimal  # Per litre
    lpg: Decimal  # Per cylinder
    effective_date: Optional[datetime] = None
    effective_date_bs: Optional[str] = None  # Bikram Sambat date


def parse_price(text: str) -> Optional[Decimal]:
    """Extract numeric price from text like 'NRs 161.00' or '161.00/L'."""
    # Remove currency and unit markers
    cleaned = re.sub(r'[^\d.]', '', text)
    if cleaned:
        try:
            return Decimal(cleaned)
        except Exception:
            pass
    return None


def parse_bs_date(date_str: str) -> Optional[datetime]:
    """Parse BS date string like '2082.05.15' to datetime.

    Note: This returns an approximate AD date (not exact conversion).
    """
    try:
        # BS dates are approximately 56-57 years ahead of AD
        parts = date_str.strip().split('.')
        if len(parts) == 3:
            bs_year = int(parts[0])
            bs_month = int(parts[1])
            bs_day = int(parts[2])

            # Approximate conversion (BS year - 57 for rough AD year)
            ad_year = bs_year - 57
            # Month/day mapping isn't exact, using same values as approximation
            month = min(bs_month, 12)
            day = min(bs_day, 28)  # Safe day value

            return datetime(ad_year, month, day, tzinfo=timezone.utc)
    except Exception:
        pass
    return None


async def fetch_fuel_prices() -> Optional[FuelPrices]:
    """Fetch fuel prices from NOC website.

    Returns:
        FuelPrices object or None if fetch fails
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                NOC_RETAIL_URL,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "Nepal-OSINT-Monitor/1.0",
                },
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            # Find the price table
            table = soup.find("table", class_="table")
            if not table:
                logger.warning("Could not find price table on NOC website")
                return None

            # Get headers to identify column positions
            headers = []
            header_row = table.find("tr")
            if header_row:
                for th in header_row.find_all(["th", "td"]):
                    headers.append(th.get_text().strip().lower())

            # Find column indices
            date_idx = None
            petrol_idx = None
            diesel_idx = None
            kerosene_idx = None
            lpg_idx = None

            for i, header in enumerate(headers):
                if 'date' in header or 'effective' in header:
                    date_idx = i
                elif 'petrol' in header or 'ms' in header:
                    petrol_idx = i
                elif 'diesel' in header or 'hsd' in header:
                    diesel_idx = i
                elif 'kerosene' in header or 'sko' in header:
                    kerosene_idx = i
                elif 'lpg' in header:
                    lpg_idx = i

            # Get the most recent price row (first data row after header)
            rows = table.find_all("tr")
            data_row = None
            for row in rows[1:]:  # Skip header
                cells = row.find_all("td")
                if len(cells) >= 5:  # Must have enough columns
                    data_row = cells
                    break

            if not data_row:
                logger.warning("Could not find data row in NOC price table")
                return None

            # Extract values
            effective_date_bs = None
            effective_date = None
            petrol = None
            diesel = None
            kerosene = None
            lpg = None

            if date_idx is not None and date_idx < len(data_row):
                effective_date_bs = data_row[date_idx].get_text().strip()
                effective_date = parse_bs_date(effective_date_bs)

            if petrol_idx is not None and petrol_idx < len(data_row):
                petrol = parse_price(data_row[petrol_idx].get_text())

            if diesel_idx is not None and diesel_idx < len(data_row):
                diesel = parse_price(data_row[diesel_idx].get_text())

            if kerosene_idx is not None and kerosene_idx < len(data_row):
                kerosene = parse_price(data_row[kerosene_idx].get_text())

            if lpg_idx is not None and lpg_idx < len(data_row):
                lpg = parse_price(data_row[lpg_idx].get_text())

            # Validate we got prices
            if not petrol or not diesel:
                logger.warning("Could not extract petrol/diesel prices from NOC")
                return None

            return FuelPrices(
                petrol=petrol,
                diesel=diesel,
                kerosene=kerosene or Decimal(0),
                lpg=lpg or Decimal(0),
                effective_date=effective_date or datetime.now(timezone.utc),
                effective_date_bs=effective_date_bs,
            )

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching NOC prices: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching NOC prices: {e}")
        return None


async def fetch_petrol_price() -> Optional[dict]:
    """Fetch petrol price per litre."""
    prices = await fetch_fuel_prices()
    if prices:
        return {
            "value": float(prices.petrol),
            "unit": "NPR/litre",
            "date": prices.effective_date,
            "date_bs": prices.effective_date_bs,
            "source": "Nepal Oil Corporation",
            "source_url": NOC_RETAIL_URL,
        }
    return None


async def fetch_diesel_price() -> Optional[dict]:
    """Fetch diesel price per litre."""
    prices = await fetch_fuel_prices()
    if prices:
        return {
            "value": float(prices.diesel),
            "unit": "NPR/litre",
            "date": prices.effective_date,
            "date_bs": prices.effective_date_bs,
            "source": "Nepal Oil Corporation",
            "source_url": NOC_RETAIL_URL,
        }
    return None
