"""Pydantic schemas for request/response validation."""
from app.schemas.story import StoryResponse, StoryListResponse, StoryCreate
from app.schemas.disaster import (
    DisasterIncidentResponse,
    DisasterIncidentListResponse,
    DisasterAlertResponse,
    DisasterAlertListResponse,
    DisasterSummaryResponse,
    SignificantIncidentResponse,
    IngestionStatsResponse,
    MapEventsResponse,
)
from app.schemas.weather import (
    WeatherForecastResponse,
    WeatherSummaryResponse,
    WeatherCondition,
    WeatherHistoryResponse,
    BilingualText,
)
from app.schemas.announcement import (
    AnnouncementResponse,
    AnnouncementListResponse,
    AnnouncementSummary,
    IngestionStats as AnnouncementIngestionStats,
    SourceInfo,
    AttachmentSchema,
)

__all__ = [
    # Story
    "StoryResponse",
    "StoryListResponse",
    "StoryCreate",
    # Disasters
    "DisasterIncidentResponse",
    "DisasterIncidentListResponse",
    "DisasterAlertResponse",
    "DisasterAlertListResponse",
    "DisasterSummaryResponse",
    "SignificantIncidentResponse",
    "IngestionStatsResponse",
    "MapEventsResponse",
    # Weather
    "WeatherForecastResponse",
    "WeatherSummaryResponse",
    "WeatherCondition",
    "WeatherHistoryResponse",
    "BilingualText",
    # Government Announcements
    "AnnouncementResponse",
    "AnnouncementListResponse",
    "AnnouncementSummary",
    "AnnouncementIngestionStats",
    "SourceInfo",
    "AttachmentSchema",
]
