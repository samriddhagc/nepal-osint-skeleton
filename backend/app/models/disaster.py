"""Disaster models - incidents and alerts from BIPAD Portal."""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, DateTime, Boolean, Integer, Float, Index, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HazardType(str, Enum):
    """Hazard type classification from BIPAD."""
    FLOOD = "flood"
    LANDSLIDE = "landslide"
    EARTHQUAKE = "earthquake"
    FIRE = "fire"
    LIGHTNING = "lightning"
    DROUGHT = "drought"
    AVALANCHE = "avalanche"
    WINDSTORM = "windstorm"
    COLD_WAVE = "cold_wave"
    EPIDEMIC = "epidemic"
    OTHER = "other"


class AlertType(str, Enum):
    """Alert type classification."""
    EARTHQUAKE = "earthquake"
    RIVER_ALERT = "river_alert"
    EARLY_WARNING = "early_warning"
    WEATHER_WARNING = "weather_warning"


class DisasterSeverity(str, Enum):
    """Severity level for disasters."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# BIPAD hazard ID to type mapping (from https://bipadportal.gov.np/api/v1/hazard/)
BIPAD_HAZARD_MAP: dict[int, HazardType] = {
    10: HazardType.FIRE,
    11: HazardType.FLOOD,
    12: HazardType.EARTHQUAKE,
    17: HazardType.LANDSLIDE,
    23: HazardType.LIGHTNING,  # Thunderbolt
    18: HazardType.DROUGHT,
    3: HazardType.AVALANCHE,
    22: HazardType.WINDSTORM,  # Storm
    5: HazardType.COLD_WAVE,
    9: HazardType.EPIDEMIC,
}


class DisasterIncident(Base):
    """Disaster incident from BIPAD Portal."""

    __tablename__ = "disaster_incidents"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # BIPAD identifier for deduplication
    bipad_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
    )

    # Content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_ne: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Hazard classification
    hazard_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="flood|landslide|earthquake|fire|lightning|drought|avalanche|windstorm|cold_wave|epidemic|other",
    )
    hazard_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Location coordinates (simple floats for Leaflet compatibility)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    street_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ward_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    province: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Casualties and damage
    deaths: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    injured: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    affected_families: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_loss: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Loss in NPR",
    )

    # Status
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    severity: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="critical|high|medium|low",
    )

    # Timestamps
    incident_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )

    # Raw BIPAD response
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_incidents_hazard_date", "hazard_type", "incident_on"),
        Index("idx_incidents_deaths", "deaths"),
        Index("idx_incidents_coords", "longitude", "latitude"),
    )

    def __repr__(self) -> str:
        return f"<DisasterIncident {self.id}: {self.hazard_type} - {self.title[:50]}>"

    @classmethod
    def calculate_severity(
        cls,
        deaths: int = 0,
        injured: int = 0,
        estimated_loss: float = 0.0,
    ) -> str:
        """
        Calculate severity based on casualties and economic loss.

        Thresholds:
        - CRITICAL: 10+ deaths OR 1 crore+ (10M NPR) loss
        - HIGH: 3+ deaths OR 50 lakhs+ (5M NPR) loss
        - MEDIUM: 1+ deaths OR 25 lakhs+ (2.5M NPR) loss
        - LOW: Everything else
        """
        # Critical: major disaster
        if deaths >= 10 or estimated_loss >= 10_000_000:
            return DisasterSeverity.CRITICAL.value

        # High: significant incident
        if deaths >= 3 or injured >= 10 or estimated_loss >= 5_000_000:
            return DisasterSeverity.HIGH.value

        # Medium: notable incident
        if deaths >= 1 or injured >= 3 or estimated_loss >= 2_500_000:
            return DisasterSeverity.MEDIUM.value

        # Low: minor incident
        return DisasterSeverity.LOW.value


class DisasterAlert(Base):
    """Disaster alert (earthquake, river alert, early warning) from BIPAD Portal."""

    __tablename__ = "disaster_alerts"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # BIPAD identifier for deduplication
    bipad_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
    )

    # Content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Alert classification
    alert_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="earthquake|river_alert|early_warning|weather_warning",
    )
    alert_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="critical|high|medium|low",
    )

    # Location coordinates (simple floats for Leaflet compatibility)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    province: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Earthquake-specific fields
    magnitude: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="For earthquakes",
    )
    depth_km: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Earthquake depth in km",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamps
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )

    # Raw BIPAD response
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_alerts_active_issued", "is_active", "issued_at"),
        Index("idx_alerts_type_level", "alert_type", "alert_level"),
        Index("idx_alerts_coords", "longitude", "latitude"),
    )

    def __repr__(self) -> str:
        return f"<DisasterAlert {self.id}: {self.alert_type} - {self.title[:50]}>"

    @classmethod
    def calculate_alert_level(cls, magnitude: Optional[float] = None) -> str:
        """
        Calculate alert level for earthquakes based on magnitude.

        Levels:
        - CRITICAL: M >= 6.0
        - HIGH: M >= 5.0
        - MEDIUM: M >= 4.0
        - LOW: M < 4.0
        """
        if magnitude is None:
            return DisasterSeverity.MEDIUM.value

        if magnitude >= 6.0:
            return DisasterSeverity.CRITICAL.value
        elif magnitude >= 5.0:
            return DisasterSeverity.HIGH.value
        elif magnitude >= 4.0:
            return DisasterSeverity.MEDIUM.value
        else:
            return DisasterSeverity.LOW.value
