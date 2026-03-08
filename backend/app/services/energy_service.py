"""Energy data service for fetching and caching NEA power grid data."""
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.energy_data import EnergyData, EnergyDataType
from app.ingestion.nea_scraper import fetch_nea_energy_data

logger = logging.getLogger(__name__)


class EnergyService:
    """Service for energy data operations."""

    # Cache keys
    CACHE_KEY_SUMMARY = "energy:summary"
    CACHE_TTL = 1800  # 30 minutes

    def __init__(self, db: AsyncSession, redis_client=None):
        self.db = db
        self.redis = redis_client

    async def get_latest_by_type(self, data_type: EnergyDataType) -> Optional[EnergyData]:
        """Get the most recent energy data entry for a type."""
        result = await self.db.execute(
            select(EnergyData)
            .where(EnergyData.data_type == data_type)
            .order_by(desc(EnergyData.fetched_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_previous_by_type(self, data_type: EnergyDataType) -> Optional[EnergyData]:
        """Get the previous (second-latest) energy data entry for a type."""
        result = await self.db.execute(
            select(EnergyData)
            .where(EnergyData.data_type == data_type)
            .order_by(desc(EnergyData.fetched_at))
            .offset(1)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_energy_data(
        self,
        data_type: EnergyDataType,
        value: Decimal,
        unit: str = "MWh",
        source_name: str = "Nepal Electricity Authority",
        source_url: str = "https://www.nea.org.np",
        data_date: Optional[datetime] = None,
    ) -> EnergyData:
        """Save energy data and calculate change from previous value."""
        # Get previous value for change calculation
        previous = await self.get_latest_by_type(data_type)

        change_amount = None
        change_percent = None
        previous_value = None

        if previous:
            previous_value = previous.value
            change_amount = value - previous.value
            if previous.value != 0:
                change_percent = (change_amount / previous.value) * 100

        energy_data = EnergyData(
            data_type=data_type,
            value=value,
            unit=unit,
            previous_value=previous_value,
            change_amount=change_amount,
            change_percent=change_percent,
            source_name=source_name,
            source_url=source_url,
            data_date=data_date or datetime.now(timezone.utc),
        )

        self.db.add(energy_data)
        await self.db.commit()
        await self.db.refresh(energy_data)

        return energy_data

    async def ingest_all(self, use_fallback: bool = True) -> dict:
        """Fetch and store all energy data from NEA.

        Args:
            use_fallback: If True, use demo data when NEA website is unavailable

        Returns:
            Stats dict with fetched/saved counts
        """
        stats = {
            "fetched": False,
            "saved": 0,
            "error": None,
            "data_types": [],
            "source": "live",
        }

        try:
            fetched_data = await fetch_nea_energy_data()

            if not fetched_data and use_fallback:
                # NEA website is unavailable - check if we have recent data
                latest = await self.get_latest_by_type(EnergyDataType.TOTAL_DEMAND)
                if latest:
                    hours_ago = (datetime.now(timezone.utc) - latest.fetched_at).total_seconds() / 3600
                    if hours_ago < 24:
                        # We have data from less than 24 hours ago, use it
                        stats["error"] = "NEA unavailable, using cached data"
                        stats["source"] = "cached"
                        return stats

                # No recent data - use demo values based on typical NEA data
                logger.info("NEA website unavailable, using representative fallback data")
                return await self.seed_demo_data()

            if not fetched_data:
                stats["error"] = "Failed to fetch energy data from NEA"
                return stats

            stats["fetched"] = True
            data_date = datetime.now(timezone.utc)

            # Save each data type
            for data_type, value in fetched_data.to_items():
                await self.save_energy_data(
                    data_type=data_type,
                    value=value,
                    unit="MWh",
                    source_name="Nepal Electricity Authority",
                    source_url=fetched_data.source_url,
                    data_date=data_date,
                )
                stats["saved"] += 1
                stats["data_types"].append(data_type.value)
                logger.info(f"Energy data saved: {data_type.value} = {value} MWh")

            # Invalidate cache if we saved data
            if stats["saved"] > 0:
                await self.invalidate_cache()

        except Exception as e:
            logger.error(f"Error ingesting energy data: {e}")
            stats["error"] = str(e)

        return stats

    async def get_energy_summary(self) -> dict:
        """Get summary of all energy data for dashboard widget.

        Returns cached data if available, otherwise fetches fresh.
        """
        # Check cache first
        if self.redis:
            try:
                cached = await self.redis.get(self.CACHE_KEY_SUMMARY)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")

        # Build summary from database
        summary = {
            "nea_subsidiary": None,
            "ipp": None,
            "import": None,
            "interruption": None,
            "total_demand": None,
            "total_supply": None,  # Calculated: NEA + IPP + Import
            "grid_status": "UNKNOWN",
            "updated_at": None,
        }

        latest_time = None

        # Fetch each data type
        for data_type, key in [
            (EnergyDataType.NEA_SUBSIDIARY, "nea_subsidiary"),
            (EnergyDataType.IPP, "ipp"),
            (EnergyDataType.IMPORT, "import"),
            (EnergyDataType.INTERRUPTION, "interruption"),
            (EnergyDataType.TOTAL_DEMAND, "total_demand"),
        ]:
            data = await self.get_latest_by_type(data_type)
            if data:
                summary[key] = {
                    "value": float(data.value),
                    "unit": data.unit,
                    "change": float(data.change_percent) if data.change_percent else 0,
                    "change_amount": float(data.change_amount) if data.change_amount else 0,
                    "source": data.source_name,
                    "data_date": data.data_date.isoformat() if data.data_date else None,
                }
                if not latest_time or data.fetched_at > latest_time:
                    latest_time = data.fetched_at

        # Calculate total supply (NEA + IPP + Import)
        supply_values = []
        for key in ["nea_subsidiary", "ipp", "import"]:
            if summary[key]:
                supply_values.append(summary[key]["value"])

        if supply_values:
            total_supply = sum(supply_values)
            summary["total_supply"] = {
                "value": total_supply,
                "unit": "MWh",
            }

            # Calculate grid status based on supply vs demand
            if summary["total_demand"]:
                demand = summary["total_demand"]["value"]
                if total_supply >= demand:
                    surplus_pct = ((total_supply - demand) / demand) * 100 if demand > 0 else 100
                    if surplus_pct > 10:
                        summary["grid_status"] = "SURPLUS"
                    else:
                        summary["grid_status"] = "STABLE"
                else:
                    deficit_pct = ((demand - total_supply) / demand) * 100 if demand > 0 else 0
                    if deficit_pct > 10:
                        summary["grid_status"] = "CRITICAL"
                    else:
                        summary["grid_status"] = "STRAINED"

        summary["updated_at"] = latest_time.isoformat() if latest_time else None

        # Cache the summary
        if self.redis and any(summary[k] for k in ["nea_subsidiary", "ipp", "import", "total_demand"]):
            try:
                await self.redis.setex(
                    self.CACHE_KEY_SUMMARY,
                    self.CACHE_TTL,
                    json.dumps(summary),
                )
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")

        return summary

    async def invalidate_cache(self):
        """Clear the energy data cache."""
        if self.redis:
            try:
                await self.redis.delete(self.CACHE_KEY_SUMMARY)
            except Exception as e:
                logger.warning(f"Redis cache delete error: {e}")

    async def seed_demo_data(self) -> dict:
        """Seed demo data based on typical NEA values.

        This is used when the NEA website is unreachable.
        Values are based on typical daily energy data from NEA.
        """
        stats = {
            "fetched": True,
            "saved": 0,
            "error": None,
            "data_types": [],
            "source": "demo",
        }

        # Demo data based on current NEA values (Feb 2026)
        # NEA website loads data via JavaScript, so we use representative values
        # Values from: https://www.nea.org.np Energy Details section
        demo_values = [
            (EnergyDataType.NEA_SUBSIDIARY, Decimal("6022")),  # NEA Subsidiary Companies
            (EnergyDataType.IPP, Decimal("17986")),           # IPP - Independent Power Producers
            (EnergyDataType.IMPORT, Decimal("8439")),         # Import from India
            (EnergyDataType.INTERRUPTION, Decimal("400")),    # Interruption/Outages
            (EnergyDataType.TOTAL_DEMAND, Decimal("38716")),  # Total Energy Demand
        ]

        data_date = datetime.now(timezone.utc)

        for data_type, value in demo_values:
            await self.save_energy_data(
                data_type=data_type,
                value=value,
                unit="MWh",
                source_name="Nepal Electricity Authority (Demo)",
                source_url="https://www.nea.org.np",
                data_date=data_date,
            )
            stats["saved"] += 1
            stats["data_types"].append(data_type.value)
            logger.info(f"Demo energy data saved: {data_type.value} = {value} MWh")

        # Invalidate cache
        await self.invalidate_cache()

        return stats
