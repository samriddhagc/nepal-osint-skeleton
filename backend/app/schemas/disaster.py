"""Disaster Pydantic schemas for API requests and responses."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Coordinates(BaseModel):
    """Geographic coordinates."""
    longitude: float = Field(..., ge=-180, le=180)
    latitude: float = Field(..., ge=-90, le=90)


class LossData(BaseModel):
    """Casualty and damage data."""
    deaths: int = 0
    injured: int = 0
    missing: int = 0
    affected_families: int = 0
    estimated_loss: float = Field(0.0, description="Loss in NPR")


# ============== Incident Schemas ==============

class DisasterIncidentBase(BaseModel):
    """Base schema for disaster incidents."""
    title: str
    title_ne: Optional[str] = None
    hazard_type: str
    district: Optional[str] = None
    province: Optional[int] = None
    deaths: int = 0
    injured: int = 0
    missing: int = 0
    affected_families: int = 0
    estimated_loss: float = 0.0
    verified: bool = False
    severity: Optional[str] = None
    incident_on: Optional[datetime] = None


class DisasterIncidentCreate(DisasterIncidentBase):
    """Schema for creating a disaster incident."""
    bipad_id: int
    hazard_id: Optional[int] = None
    street_address: Optional[str] = None
    ward_ids: Optional[list] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    raw_data: Optional[dict] = None


class DisasterIncidentResponse(BaseModel):
    """Disaster incident response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bipad_id: int
    title: str
    title_ne: Optional[str] = None
    hazard_type: str
    hazard_id: Optional[int] = None
    street_address: Optional[str] = None
    district: Optional[str] = None
    province: Optional[int] = None
    deaths: int
    injured: int
    missing: int
    affected_families: int
    estimated_loss: float
    verified: bool
    severity: Optional[str] = None
    incident_on: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DisasterIncidentWithCoords(DisasterIncidentResponse):
    """Disaster incident with coordinates for map display."""
    coordinates: Optional[Coordinates] = None


class DisasterIncidentListResponse(BaseModel):
    """Paginated list of disaster incidents."""
    items: list[DisasterIncidentResponse]
    total: int
    page: int
    page_size: int


# ============== Alert Schemas ==============

class DisasterAlertBase(BaseModel):
    """Base schema for disaster alerts."""
    title: str
    description: Optional[str] = None
    alert_type: str
    alert_level: str
    location_name: Optional[str] = None
    district: Optional[str] = None
    province: Optional[int] = None
    magnitude: Optional[float] = None
    depth_km: Optional[float] = None
    is_active: bool = True
    expires_at: Optional[datetime] = None
    issued_at: datetime


class DisasterAlertCreate(DisasterAlertBase):
    """Schema for creating a disaster alert."""
    bipad_id: int
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    raw_data: Optional[dict] = None


class DisasterAlertResponse(BaseModel):
    """Disaster alert response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bipad_id: int
    title: str
    description: Optional[str] = None
    alert_type: str
    alert_level: str
    location_name: Optional[str] = None
    district: Optional[str] = None
    province: Optional[int] = None
    magnitude: Optional[float] = None
    depth_km: Optional[float] = None
    is_active: bool
    expires_at: Optional[datetime] = None
    issued_at: datetime
    created_at: datetime
    updated_at: datetime


class DisasterAlertWithCoords(DisasterAlertResponse):
    """Disaster alert with coordinates for map display."""
    coordinates: Optional[Coordinates] = None


class DisasterAlertListResponse(BaseModel):
    """Paginated list of disaster alerts."""
    items: list[DisasterAlertResponse]
    total: int
    page: int
    page_size: int


# ============== Map Event Schemas ==============

class MapEventBase(BaseModel):
    """Base schema for map events (unified format for Leaflet)."""
    id: UUID
    type: str  # "incident" or "alert" or "earthquake"
    title: str
    coordinates: list[float]  # [longitude, latitude] for Leaflet
    severity: str
    timestamp: datetime


class MapIncidentEvent(MapEventBase):
    """Map event for incidents."""
    hazard_type: str
    loss: LossData
    district: Optional[str] = None
    verified: bool = False


class MapAlertEvent(MapEventBase):
    """Map event for alerts."""
    alert_type: str
    alert_level: str
    magnitude: Optional[float] = None
    depth_km: Optional[float] = None
    is_active: bool = True


class MapEventsResponse(BaseModel):
    """Response containing map events for frontend."""
    incidents: list[MapIncidentEvent]
    alerts: list[MapAlertEvent]
    total_incidents: int
    total_alerts: int


# ============== Ingestion Schemas ==============

class IngestionStatsResponse(BaseModel):
    """Statistics from disaster ingestion."""
    incidents_fetched: int = 0
    incidents_new: int = 0
    incidents_duplicate: int = 0
    incidents_filtered: int = 0
    alerts_fetched: int = 0
    alerts_new: int = 0
    alerts_duplicate: int = 0
    alerts_expired: int = 0
    errors: list[str] = []


# ============== Summary Schemas ==============

class DisasterSummaryResponse(BaseModel):
    """Summary statistics for disasters."""
    total_incidents: int
    total_alerts: int
    active_alerts: int
    incidents_by_type: dict[str, int]
    incidents_by_severity: dict[str, int]
    total_deaths: int
    total_injured: int
    total_loss_npr: float
    recent_earthquakes: int  # M >= 4.0 in last 7 days


class SignificantIncidentResponse(BaseModel):
    """Significant incident (deaths > 0 OR loss > 25 lakhs)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bipad_id: int
    title: str
    hazard_type: str
    district: Optional[str]
    deaths: int
    injured: int
    estimated_loss: float
    severity: str
    incident_on: Optional[datetime]
    coordinates: Optional[Coordinates] = None
