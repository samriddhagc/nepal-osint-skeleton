"""Pydantic schemas for weather data."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BilingualText(BaseModel):
    """Bilingual text (English and Nepali)."""
    en: Optional[str] = None
    np: Optional[str] = None


class WeatherForecastResponse(BaseModel):
    """Weather forecast response from DHM Nepal."""
    id: str
    dhm_id: str
    issue_date: datetime
    analysis: BilingualText
    forecast_today: BilingualText
    forecast_tomorrow: BilingualText
    special_notice: Optional[str] = None
    issued_by: Optional[str] = None
    updated_by: Optional[str] = None
    fetched_at: datetime
    data_source: str = "DHM Nepal (dhm.gov.np)"


class WeatherCondition(BaseModel):
    """Derived weather condition from forecast text."""
    condition: str  # Clear, Cloudy, Rainy, Foggy, Snowy, etc.
    icon: str  # Icon code for frontend
    description: str  # Human-readable description
    regions_affected: list[str] = Field(default_factory=list)


class WeatherSummaryResponse(BaseModel):
    """Summarized weather data for dashboard widget."""
    issue_date: datetime
    condition: WeatherCondition
    forecast_today_en: str
    forecast_tomorrow_en: str
    special_notice: Optional[str] = None
    issued_by: Optional[str] = None
    data_source: str = "DHM Nepal (dhm.gov.np)"
    last_updated: datetime


class WeatherHistoryResponse(BaseModel):
    """Historical weather forecasts."""
    forecasts: list[WeatherForecastResponse]
    total: int
