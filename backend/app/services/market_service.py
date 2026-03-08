"""Market data service for fetching and caching financial data."""
import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data import MarketData, MarketDataType
from app.ingestion.market_scrapers.nrb_forex import fetch_usd_npr_rate
from app.ingestion.market_scrapers.gold_silver import fetch_gold_silver_prices as get_gold_silver
from app.ingestion.market_scrapers.fuel_prices import fetch_fuel_prices as get_fuel
from app.ingestion.market_scrapers.nepse import fetch_nepse_summary

logger = logging.getLogger(__name__)


class MarketService:
    """Service for market data operations."""

    # Cache keys
    CACHE_KEY_SUMMARY = "market:summary"
    CACHE_TTL = 3600  # 1 hour

    def __init__(self, db: AsyncSession, redis_client=None):
        self.db = db
        self.redis = redis_client

    async def get_latest_by_type(self, data_type: MarketDataType) -> Optional[MarketData]:
        """Get the most recent market data entry for a type."""
        result = await self.db.execute(
            select(MarketData)
            .where(MarketData.data_type == data_type)
            .order_by(desc(MarketData.fetched_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_previous_by_type(self, data_type: MarketDataType) -> Optional[MarketData]:
        """Get the previous (second-latest) market data entry for a type."""
        result = await self.db.execute(
            select(MarketData)
            .where(MarketData.data_type == data_type)
            .order_by(desc(MarketData.fetched_at))
            .offset(1)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_previous_distinct_by_type(
        self,
        data_type: MarketDataType,
        current_value: Decimal,
    ) -> Optional[MarketData]:
        """Get most recent row with a different value for stable delta calculations."""
        result = await self.db.execute(
            select(MarketData)
            .where(
                MarketData.data_type == data_type,
                MarketData.value != current_value,
            )
            .order_by(desc(MarketData.fetched_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_market_data(
        self,
        data_type: MarketDataType,
        value: Decimal,
        unit: str,
        source_name: str,
        source_url: Optional[str] = None,
        data_date: Optional[datetime] = None,
    ) -> MarketData:
        """Save market data and calculate change from previous value."""
        now = datetime.now(timezone.utc)
        resolved_data_date = data_date or now

        # Get previous value for change calculation
        previous = await self.get_latest_by_type(data_type)

        # If value is unchanged, update freshness/metadata instead of inserting a duplicate row.
        if previous and previous.value == value:
            previous.unit = unit
            previous.source_name = source_name
            previous.source_url = source_url
            previous.data_date = resolved_data_date
            previous.fetched_at = now
            await self.db.commit()
            await self.db.refresh(previous)
            return previous

        change_amount = None
        change_percent = None
        previous_value = None

        if previous:
            previous_value = previous.value
            change_amount = value - previous.value
            if previous.value != 0:
                change_percent = (change_amount / previous.value) * 100

        market_data = MarketData(
            data_type=data_type,
            value=value,
            unit=unit,
            previous_value=previous_value,
            change_amount=change_amount,
            change_percent=change_percent,
            source_name=source_name,
            source_url=source_url,
            data_date=resolved_data_date,
        )

        self.db.add(market_data)
        await self.db.commit()
        await self.db.refresh(market_data)

        return market_data

    async def ingest_forex(self) -> dict:
        """Fetch and store USD/NPR exchange rate."""
        stats = {"fetched": False, "saved": False, "error": None}

        try:
            rate_data = await fetch_usd_npr_rate()
            if not rate_data:
                stats["error"] = "Failed to fetch forex data"
                return stats

            stats["fetched"] = True

            await self.save_market_data(
                data_type=MarketDataType.FOREX_USD,
                value=Decimal(str(rate_data["value"])),
                unit="NPR",
                source_name=rate_data["source"],
                source_url=rate_data["source_url"],
                data_date=rate_data.get("date"),
            )

            stats["saved"] = True
            logger.info(f"Forex rate saved: {rate_data['value']} NPR/USD")

        except Exception as e:
            logger.error(f"Error ingesting forex: {e}")
            stats["error"] = str(e)

        return stats

    async def ingest_gold_silver(self) -> dict:
        """Fetch and store gold/silver prices."""
        stats = {"fetched": False, "gold_saved": False, "silver_saved": False, "error": None}

        try:
            prices = await get_gold_silver()
            if not prices:
                stats["error"] = "Failed to fetch gold/silver data"
                return stats

            stats["fetched"] = True

            if prices.gold_per_tola:
                await self.save_market_data(
                    data_type=MarketDataType.GOLD,
                    value=prices.gold_per_tola,
                    unit="NPR/tola",
                    source_name="FENEGOSIDA",
                    source_url="https://fenegosida.org/",
                    data_date=prices.date,
                )
                stats["gold_saved"] = True
                logger.info(f"Gold price saved: {prices.gold_per_tola} NPR/tola")

            if prices.silver_per_tola:
                await self.save_market_data(
                    data_type=MarketDataType.SILVER,
                    value=prices.silver_per_tola,
                    unit="NPR/tola",
                    source_name="FENEGOSIDA",
                    source_url="https://fenegosida.org/",
                    data_date=prices.date,
                )
                stats["silver_saved"] = True
                logger.info(f"Silver price saved: {prices.silver_per_tola} NPR/tola")

        except Exception as e:
            logger.error(f"Error ingesting gold/silver: {e}")
            stats["error"] = str(e)

        return stats

    async def ingest_fuel(self) -> dict:
        """Fetch and store fuel prices."""
        stats = {"fetched": False, "petrol_saved": False, "diesel_saved": False, "error": None}

        try:
            prices = await get_fuel()
            if not prices:
                stats["error"] = "Failed to fetch fuel data"
                return stats

            stats["fetched"] = True

            if prices.petrol:
                await self.save_market_data(
                    data_type=MarketDataType.PETROL,
                    value=prices.petrol,
                    unit="NPR/litre",
                    source_name="Nepal Oil Corporation",
                    source_url="https://noc.org.np/retailprice",
                    data_date=prices.effective_date,
                )
                stats["petrol_saved"] = True
                logger.info(f"Petrol price saved: {prices.petrol} NPR/litre")

            if prices.diesel:
                await self.save_market_data(
                    data_type=MarketDataType.DIESEL,
                    value=prices.diesel,
                    unit="NPR/litre",
                    source_name="Nepal Oil Corporation",
                    source_url="https://noc.org.np/retailprice",
                    data_date=prices.effective_date,
                )
                stats["diesel_saved"] = True
                logger.info(f"Diesel price saved: {prices.diesel} NPR/litre")

        except Exception as e:
            logger.error(f"Error ingesting fuel: {e}")
            stats["error"] = str(e)

        return stats

    async def ingest_nepse(self) -> dict:
        """Fetch and store NEPSE index."""
        stats = {"fetched": False, "saved": False, "error": None}

        try:
            index_data = await fetch_nepse_summary()
            if not index_data:
                stats["error"] = "Failed to fetch NEPSE data"
                return stats

            stats["fetched"] = True

            await self.save_market_data(
                data_type=MarketDataType.NEPSE,
                value=Decimal(str(index_data["value"])),
                unit="points",
                source_name=index_data["source"],
                source_url=index_data["source_url"],
                data_date=index_data.get("date"),
            )

            stats["saved"] = True
            logger.info(f"NEPSE index saved: {index_data['value']}")

        except Exception as e:
            logger.error(f"Error ingesting NEPSE: {e}")
            stats["error"] = str(e)

        return stats

    async def ingest_all(self) -> dict:
        """Ingest all market data sources."""
        results = await asyncio.gather(
            self.ingest_forex(),
            self.ingest_gold_silver(),
            self.ingest_fuel(),
            self.ingest_nepse(),
            return_exceptions=True,
        )

        return {
            "forex": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
            "gold_silver": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
            "fuel": results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])},
            "nepse": results[3] if not isinstance(results[3], Exception) else {"error": str(results[3])},
        }

    async def get_market_summary(self) -> dict:
        """Get summary of all market data for dashboard widget.

        Returns cached data if available, otherwise fetches fresh.
        """
        # Check cache first
        if self.redis:
            cached = await self.redis.get(self.CACHE_KEY_SUMMARY)
            if cached:
                return json.loads(cached)

        # Build summary from database
        summary = {
            "nepse": None,
            "usd_npr": None,
            "gold": None,
            "silver": None,
            "petrol": None,
            "diesel": None,
            "updated_at": None,
        }

        latest_time = None

        # Fetch each data type
        for data_type, key in [
            (MarketDataType.NEPSE, "nepse"),
            (MarketDataType.FOREX_USD, "usd_npr"),
            (MarketDataType.GOLD, "gold"),
            (MarketDataType.SILVER, "silver"),
            (MarketDataType.PETROL, "petrol"),
            (MarketDataType.DIESEL, "diesel"),
        ]:
            data = await self.get_latest_by_type(data_type)
            if data:
                previous_distinct = await self.get_previous_distinct_by_type(data_type, data.value)
                if previous_distinct:
                    change_amount = data.value - previous_distinct.value
                    change_percent = (
                        (change_amount / previous_distinct.value) * 100
                        if previous_distinct.value != 0
                        else Decimal("0")
                    )
                else:
                    change_amount = Decimal("0")
                    change_percent = Decimal("0")

                summary[key] = {
                    "value": float(data.value),
                    "unit": data.unit,
                    "change": float(change_percent),
                    "change_amount": float(change_amount),
                    "source": data.source_name,
                    "data_date": data.data_date.isoformat() if data.data_date else None,
                }
                if not latest_time or data.fetched_at > latest_time:
                    latest_time = data.fetched_at

        summary["updated_at"] = latest_time.isoformat() if latest_time else None

        # Cache the summary
        if self.redis and any(summary[k] for k in ["nepse", "usd_npr", "gold", "silver", "petrol", "diesel"]):
            await self.redis.setex(
                self.CACHE_KEY_SUMMARY,
                self.CACHE_TTL,
                json.dumps(summary),
            )

        return summary

    async def invalidate_cache(self):
        """Clear the market data cache."""
        if self.redis:
            await self.redis.delete(self.CACHE_KEY_SUMMARY)
