"""River monitoring models."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Float, Boolean, Integer, BigInteger, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class RiverStation(Base):
    """River monitoring station from BIPAD Portal."""

    __tablename__ = "river_stations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    bipad_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    basin: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    danger_level: Mapped[Optional[float]] = mapped_column(Float)
    warning_level: Mapped[Optional[float]] = mapped_column(Float)
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to readings
    readings: Mapped[list["RiverReading"]] = relationship(back_populates="station", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "bipad_id": self.bipad_id,
            "title": self.title,
            "basin": self.basin,
            "description": self.description,
            "coordinates": [self.longitude, self.latitude] if self.longitude and self.latitude else None,
            "danger_level": self.danger_level,
            "warning_level": self.warning_level,
            "image_url": self.image_url,
            "is_active": self.is_active,
        }


class RiverReading(Base):
    """Water level reading from a river station."""

    __tablename__ = "river_readings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    station_id: Mapped[UUID] = mapped_column(ForeignKey("river_stations.id", ondelete="CASCADE"), nullable=False)
    bipad_reading_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    water_level: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(50))  # BELOW WARNING LEVEL, WARNING, DANGER
    trend: Mapped[Optional[str]] = mapped_column(String(20))   # STEADY, RISING, FALLING
    reading_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationship to station
    station: Mapped["RiverStation"] = relationship(back_populates="readings")

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "station_id": str(self.station_id),
            "water_level": self.water_level,
            "status": self.status,
            "trend": self.trend,
            "reading_at": self.reading_at.isoformat() if self.reading_at else None,
        }


# Status constants
class RiverStatus:
    BELOW_WARNING = "BELOW WARNING LEVEL"
    WARNING = "WARNING"
    DANGER = "DANGER"


class RiverTrend:
    STEADY = "STEADY"
    RISING = "RISING"
    FALLING = "FALLING"
