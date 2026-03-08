"""NRB (Nepal Rastra Bank) forex rate fetcher.

Uses the official NRB API which provides exchange rates in JSON format.
API: https://www.nrb.org.np/api/forex/v1/rates
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

NRB_FOREX_API = "https://www.nrb.org.np/api/forex/v1/rates"


@dataclass
class ForexRate:
    """Forex rate data."""
    currency_code: str
    currency_name: str
    buy_rate: Decimal
    sell_rate: Decimal
    unit: int
    date: datetime


async def fetch_nrb_forex(currency: str = "USD") -> Optional[ForexRate]:
    """Fetch forex rates from NRB API.

    Args:
        currency: Currency code (default: USD)

    Returns:
        ForexRate object or None if fetch fails
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # NRB API requires from and to date parameters
            today = datetime.now(timezone.utc).date()
            # Try last 7 days to ensure we get data (weekends/holidays)
            from_date = today - timedelta(days=7)

            response = await client.get(
                NRB_FOREX_API,
                params={
                    "from": from_date.strftime("%Y-%m-%d"),
                    "to": today.strftime("%Y-%m-%d"),
                    "per_page": 50,
                    "page": 1,
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Nepal-OSINT-Monitor/1.0",
                },
            )
            response.raise_for_status()

            data = response.json()

            # API response structure:
            # {"status": {"code": 200}, "data": {"payload": [...]}}
            if data.get("status", {}).get("code") != 200:
                logger.error(f"NRB API returned error status: {data.get('status')}")
                return None

            payload = data.get("data", {}).get("payload", [])

            # Find the requested currency
            for rate_data in payload:
                rates = rate_data.get("rates", [])
                for rate in rates:
                    if rate.get("currency", {}).get("iso3") == currency:
                        # Parse date from rate_data
                        date_str = rate_data.get("date")
                        rate_date = datetime.now(timezone.utc)
                        if date_str:
                            try:
                                rate_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            except ValueError:
                                pass

                        return ForexRate(
                            currency_code=currency,
                            currency_name=rate.get("currency", {}).get("name", "US Dollar"),
                            buy_rate=Decimal(str(rate.get("buy", 0))),
                            sell_rate=Decimal(str(rate.get("sell", 0))),
                            unit=rate.get("currency", {}).get("unit", 1),
                            date=rate_date,
                        )

            logger.warning(f"Currency {currency} not found in NRB response")
            return None

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching NRB forex: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching NRB forex: {e}")
        return None


async def fetch_usd_npr_rate() -> Optional[dict]:
    """Convenience function to fetch USD/NPR rate.

    Returns:
        Dict with 'value' (sell rate), 'buy', 'sell', 'date' or None
    """
    rate = await fetch_nrb_forex("USD")
    if rate:
        return {
            "value": float(rate.sell_rate),
            "buy": float(rate.buy_rate),
            "sell": float(rate.sell_rate),
            "unit": rate.unit,
            "date": rate.date,
            "source": "Nepal Rastra Bank",
            "source_url": NRB_FOREX_API,
        }
    return None
