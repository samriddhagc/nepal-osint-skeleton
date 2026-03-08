"""Gold and Silver price scraper from FENEGOSIDA.

FENEGOSIDA (Federation of Nepal Gold and Silver Dealers' Association)
URL: https://www.fenegosida.org/
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FENEGOSIDA_URL = "https://fenegosida.org/"


@dataclass
class GoldSilverPrices:
    """Gold and silver price data."""
    gold_per_tola: Decimal
    silver_per_tola: Decimal
    gold_per_10g: Optional[Decimal] = None
    silver_per_10g: Optional[Decimal] = None
    date: Optional[datetime] = None
    date_bs: Optional[str] = None  # Bikram Sambat date string


def extract_price(text: str) -> Optional[Decimal]:
    """Extract numeric price from text like 'रु 318800' or '318,800'."""
    # Remove commas and non-numeric characters except digits
    cleaned = re.sub(r'[^\d]', '', text)
    if cleaned:
        try:
            return Decimal(cleaned)
        except Exception:
            pass
    return None


async def fetch_gold_silver_prices() -> Optional[GoldSilverPrices]:
    """Fetch gold and silver prices from FENEGOSIDA.

    Returns:
        GoldSilverPrices object or None if fetch fails
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                FENEGOSIDA_URL,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "Nepal-OSINT-Monitor/1.0",
                },
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            text = soup.get_text()

            # Extract prices using regex patterns
            # Looking for patterns like "रु 318800" or "318,800" near "Gold" or "Fine Gold"
            gold_tola = None
            silver_tola = None
            gold_10g = None
            silver_10g = None
            date_bs = None

            # Try to find date (Nepali format like "14 Magh 2082")
            date_pattern = r'(\d{1,2}\s+(?:Baishakh|Jestha|Ashadh|Shrawan|Bhadra|Ashwin|Kartik|Mangsir|Poush|Magh|Falgun|Chaitra)\s+\d{4})'
            date_match = re.search(date_pattern, text, re.IGNORECASE)
            if date_match:
                date_bs = date_match.group(1)

            # Find price patterns - typically formatted as tables or price lists
            # Pattern: Look for "Fine Gold 9999" followed by prices
            # Or simply large numbers near gold/silver keywords

            lines = text.split('\n')
            current_section = None

            for i, line in enumerate(lines):
                line_lower = line.lower().strip()

                # Track what section we're in
                if 'gold' in line_lower and 'silver' not in line_lower:
                    current_section = 'gold'
                elif 'silver' in line_lower:
                    current_section = 'silver'

                # Look for prices in NPR format
                price_matches = re.findall(r'रु\s*([\d,]+)', line)
                if not price_matches:
                    price_matches = re.findall(r'([\d,]{5,})', line)  # At least 5 digits

                for price_str in price_matches:
                    price = extract_price(price_str)
                    if price and price > 1000:  # Sanity check
                        # Determine if this is per tola or per 10g based on context
                        context = lines[max(0, i-2):i+3]
                        context_text = ' '.join(context).lower()

                        if 'tola' in context_text or 'तोला' in context_text:
                            if current_section == 'gold' and not gold_tola:
                                gold_tola = price
                            elif current_section == 'silver' and not silver_tola:
                                silver_tola = price
                        elif '10' in context_text and ('gm' in context_text or 'gram' in context_text):
                            if current_section == 'gold' and not gold_10g:
                                gold_10g = price
                            elif current_section == 'silver' and not silver_10g:
                                silver_10g = price

            # Alternative: Try to find structured price tables
            # Look for table cells or divs with price data
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    row_text = ' '.join(cell.get_text() for cell in cells).lower()

                    if 'gold' in row_text or 'सुन' in row_text:
                        for cell in cells:
                            price = extract_price(cell.get_text())
                            if price and price > 100000:  # Gold price range
                                if 'tola' in row_text or 'तोला' in row_text:
                                    gold_tola = price
                                elif not gold_10g:
                                    gold_10g = price

                    if 'silver' in row_text or 'चाँदी' in row_text:
                        for cell in cells:
                            price = extract_price(cell.get_text())
                            if price and price > 1000:  # Silver price range
                                if 'tola' in row_text or 'तोला' in row_text:
                                    silver_tola = price
                                elif not silver_10g:
                                    silver_10g = price

            # Validate we got at least some prices
            if not gold_tola and not silver_tola:
                logger.warning("Could not extract gold/silver prices from FENEGOSIDA")
                return None

            return GoldSilverPrices(
                gold_per_tola=gold_tola or Decimal(0),
                silver_per_tola=silver_tola or Decimal(0),
                gold_per_10g=gold_10g,
                silver_per_10g=silver_10g,
                date=datetime.now(timezone.utc),
                date_bs=date_bs,
            )

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching FENEGOSIDA prices: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching FENEGOSIDA prices: {e}")
        return None


async def fetch_gold_price() -> Optional[dict]:
    """Fetch gold price per tola.

    Returns:
        Dict with 'value', 'unit', 'date' or None
    """
    prices = await fetch_gold_silver_prices()
    if prices and prices.gold_per_tola:
        return {
            "value": float(prices.gold_per_tola),
            "unit": "NPR/tola",
            "date": prices.date,
            "date_bs": prices.date_bs,
            "source": "FENEGOSIDA",
            "source_url": FENEGOSIDA_URL,
        }
    return None


async def fetch_silver_price() -> Optional[dict]:
    """Fetch silver price per tola.

    Returns:
        Dict with 'value', 'unit', 'date' or None
    """
    prices = await fetch_gold_silver_prices()
    if prices and prices.silver_per_tola:
        return {
            "value": float(prices.silver_per_tola),
            "unit": "NPR/tola",
            "date": prices.date,
            "date_bs": prices.date_bs,
            "source": "FENEGOSIDA",
            "source_url": FENEGOSIDA_URL,
        }
    return None
