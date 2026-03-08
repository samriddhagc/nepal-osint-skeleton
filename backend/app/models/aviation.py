"""Aviation monitoring models — ADS-B aircraft position tracking."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AircraftPosition(Base):
    """A single ADS-B position report for an aircraft in Nepal airspace."""

    __tablename__ = "aircraft_positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hex_code: Mapped[str] = mapped_column(
        String(6), nullable=False, comment="ICAO 24-bit address e.g. 70A001"
    )
    callsign: Mapped[str | None] = mapped_column(String(10))
    registration: Mapped[str | None] = mapped_column(
        String(20), comment="e.g. 9N-AMA"
    )
    aircraft_type: Mapped[str | None] = mapped_column(
        String(10), comment="ICAO type designator e.g. A320, H125"
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    altitude_ft: Mapped[int | None] = mapped_column(
        Integer, comment="Barometric altitude in feet"
    )
    ground_speed_kts: Mapped[float | None] = mapped_column(Float)
    track_deg: Mapped[float | None] = mapped_column(
        Float, comment="Heading in degrees"
    )
    vertical_rate_fpm: Mapped[int | None] = mapped_column(
        Integer, comment="Vertical rate in feet per minute"
    )
    squawk: Mapped[str | None] = mapped_column(String(4))
    is_military: Mapped[bool] = mapped_column(Boolean, default=False)
    is_on_ground: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str | None] = mapped_column(
        String(4), comment="ADS-B emitter category"
    )
    nearest_airport_icao: Mapped[str | None] = mapped_column(
        String(4), comment="Nearest Nepal airport ICAO code"
    )
    airspace_category: Mapped[str | None] = mapped_column(
        String(20), comment="in_nepal, near_nepal, nepal_carrier, overflight"
    )
    source: Mapped[str] = mapped_column(String(20), default="adsb_lol")
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When ADS-B signal was received",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_aircraft_positions_hex_seen", "hex_code", "seen_at"),
        Index("ix_aircraft_positions_seen_at", "seen_at"),
        Index("ix_aircraft_positions_military_seen", "is_military", "seen_at"),
        Index("ix_aircraft_positions_airport_seen", "nearest_airport_icao", "seen_at"),
        Index("ix_aircraft_positions_airspace_cat_seen", "airspace_category", "seen_at"),
    )
