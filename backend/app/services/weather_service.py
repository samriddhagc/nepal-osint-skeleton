"""Weather service for fetching data from DHM Nepal API."""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.weather import WeatherForecast
from app.repositories.weather import WeatherForecastRepository
from app.schemas.weather import (
    WeatherForecastResponse,
    WeatherSummaryResponse,
    WeatherCondition,
    BilingualText,
)

logger = logging.getLogger(__name__)

# DHM API endpoint
DHM_API_URL = "https://dhm.gov.np/mfd/api/country-forecast"

# Weather condition keywords and their icons
CONDITION_PATTERNS = {
    "snow": {"condition": "Snow", "icon": "snowflake"},
    "snowfall": {"condition": "Snow", "icon": "snowflake"},
    "rain": {"condition": "Rain", "icon": "cloud-rain"},
    "rainfall": {"condition": "Rain", "icon": "cloud-rain"},
    "rainy": {"condition": "Rain", "icon": "cloud-rain"},
    "drizzle": {"condition": "Drizzle", "icon": "cloud-drizzle"},
    "thunderstorm": {"condition": "Thunderstorm", "icon": "cloud-lightning"},
    "storm": {"condition": "Storm", "icon": "cloud-lightning"},
    "fog": {"condition": "Fog", "icon": "cloud-fog"},
    "mist": {"condition": "Mist", "icon": "cloud-fog"},
    "haze": {"condition": "Haze", "icon": "cloud-fog"},
    "cloudy": {"condition": "Cloudy", "icon": "cloud"},
    "partly cloudy": {"condition": "Partly Cloudy", "icon": "cloud-sun"},
    "overcast": {"condition": "Overcast", "icon": "cloud"},
    "clear": {"condition": "Clear", "icon": "sun"},
    "fair": {"condition": "Fair", "icon": "sun"},
    "sunny": {"condition": "Sunny", "icon": "sun"},
}

# Nepal provinces for region detection
NEPAL_PROVINCES = [
    "Koshi", "Madhesh", "Bagmati", "Gandaki", "Lumbini", "Karnali", "Sudurpashchim"
]


def extract_weather_condition(forecast_text: str) -> WeatherCondition:
    """Extract weather condition from forecast text."""
    if not forecast_text:
        return WeatherCondition(
            condition="Unknown",
            icon="cloud",
            description="Weather data unavailable",
            regions_affected=[],
        )

    text_lower = forecast_text.lower()

    # Find matching condition (order matters - more specific first)
    detected_condition = "Clear"
    detected_icon = "sun"

    # Check for precipitation/weather events (prioritize these)
    for keyword, info in CONDITION_PATTERNS.items():
        if keyword in text_lower:
            detected_condition = info["condition"]
            detected_icon = info["icon"]
            break

    # Extract affected regions/provinces
    regions = []
    for province in NEPAL_PROVINCES:
        if province.lower() in text_lower:
            regions.append(province)

    # Check for regional descriptions
    if "terai" in text_lower:
        regions.append("Terai")
    if "hilly" in text_lower or "hill" in text_lower:
        regions.append("Hilly Region")
    if "mountainous" in text_lower or "mountain" in text_lower:
        regions.append("Mountainous Region")

    return WeatherCondition(
        condition=detected_condition,
        icon=detected_icon,
        description=forecast_text[:200] + "..." if len(forecast_text) > 200 else forecast_text,
        regions_affected=regions,
    )


class WeatherService:
    """Service for weather operations with DHM Nepal API."""

    CACHE_KEY = "weather:nepal:forecast"
    CACHE_TTL = 3600  # 1 hour

    def __init__(self, db: AsyncSession, redis_client=None):
        self.db = db
        self.redis = redis_client
        self.repo = WeatherForecastRepository(db)

    async def fetch_from_dhm(self) -> Optional[dict]:
        """Fetch weather data from DHM API."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(DHM_API_URL)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"DHM API HTTP error: {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"DHM API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"DHM API unexpected error: {e}")
            return None

    async def ingest_forecast(self) -> dict:
        """Fetch and store weather forecast from DHM."""
        stats = {
            "fetched": False,
            "created": False,
            "updated": False,
            "error": None,
        }

        data = await self.fetch_from_dhm()
        if not data:
            stats["error"] = "Failed to fetch from DHM API"
            return stats

        stats["fetched"] = True

        try:
            # Parse issue date
            issue_date_str = data.get("issue_date")
            if issue_date_str:
                issue_date = datetime.fromisoformat(issue_date_str.replace("Z", "+00:00"))
            else:
                issue_date = datetime.now(timezone.utc)

            # Get meteorologist names
            issued_by = data.get("user", {}).get("name") if data.get("user") else None
            updated_by = data.get("update_by", {}).get("name") if data.get("update_by") else None

            # Upsert forecast
            forecast, created = await self.repo.upsert(
                dhm_id=str(data.get("id")),
                issue_date=issue_date,
                analysis_en=data.get("analysis_en", "").strip(),
                analysis_np=data.get("analysis_np", "").strip(),
                forecast_en_1=data.get("en_text_1", "").strip(),
                forecast_np_1=data.get("np_text_1", "").strip(),
                forecast_en_2=data.get("en_text_2", "").strip(),
                forecast_np_2=data.get("np_text_2", "").strip(),
                special_notice=data.get("special", "").strip() or None,
                issued_by=issued_by,
                updated_by=updated_by,
            )

            stats["created"] = created
            stats["updated"] = not created

            # Invalidate cache
            if self.redis:
                await self.redis.delete(self.CACHE_KEY)

            logger.info(f"Weather forecast {'created' if created else 'updated'}: {forecast.dhm_id}")

        except Exception as e:
            logger.error(f"Error storing weather forecast: {e}")
            stats["error"] = str(e)

        return stats

    async def get_current_forecast(self) -> Optional[WeatherForecastResponse]:
        """Get the current weather forecast."""
        # Check cache first
        if self.redis:
            cached = await self.redis.get(self.CACHE_KEY)
            if cached:
                import json
                data = json.loads(cached)
                return WeatherForecastResponse(**data)

        # Get from database
        forecast = await self.repo.get_latest()
        if not forecast:
            # Try fetching fresh data
            await self.ingest_forecast()
            forecast = await self.repo.get_latest()

        if not forecast:
            return None

        response = WeatherForecastResponse(
            id=str(forecast.id),
            dhm_id=forecast.dhm_id,
            issue_date=forecast.issue_date,
            analysis=BilingualText(en=forecast.analysis_en, np=forecast.analysis_np),
            forecast_today=BilingualText(en=forecast.forecast_en_1, np=forecast.forecast_np_1),
            forecast_tomorrow=BilingualText(en=forecast.forecast_en_2, np=forecast.forecast_np_2),
            special_notice=forecast.special_notice,
            issued_by=forecast.issued_by,
            updated_by=forecast.updated_by,
            fetched_at=forecast.fetched_at,
        )

        # Cache the response
        if self.redis:
            import json
            await self.redis.setex(
                self.CACHE_KEY,
                self.CACHE_TTL,
                json.dumps(response.model_dump(mode="json")),
            )

        return response

    async def get_weather_summary(self) -> Optional[WeatherSummaryResponse]:
        """Get summarized weather for dashboard widget."""
        forecast = await self.repo.get_latest()
        if not forecast:
            # Try fetching fresh data
            await self.ingest_forecast()
            forecast = await self.repo.get_latest()

        if not forecast:
            return None

        # Extract weather condition from forecast text
        condition = extract_weather_condition(forecast.forecast_en_1 or "")

        return WeatherSummaryResponse(
            issue_date=forecast.issue_date,
            condition=condition,
            forecast_today_en=forecast.forecast_en_1 or "",
            forecast_tomorrow_en=forecast.forecast_en_2 or "",
            special_notice=forecast.special_notice,
            issued_by=forecast.issued_by,
            last_updated=forecast.fetched_at,
        )

    async def get_forecast_history(self, days: int = 7) -> list[WeatherForecastResponse]:
        """Get historical forecasts."""
        forecasts = await self.repo.get_history(days=days)
        return [
            WeatherForecastResponse(
                id=str(f.id),
                dhm_id=f.dhm_id,
                issue_date=f.issue_date,
                analysis=BilingualText(en=f.analysis_en, np=f.analysis_np),
                forecast_today=BilingualText(en=f.forecast_en_1, np=f.forecast_np_1),
                forecast_tomorrow=BilingualText(en=f.forecast_en_2, np=f.forecast_np_2),
                special_notice=f.special_notice,
                issued_by=f.issued_by,
                updated_by=f.updated_by,
                fetched_at=f.fetched_at,
            )
            for f in forecasts
        ]
