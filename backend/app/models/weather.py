"""Weather forecast models for DHM Nepal data."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WeatherForecast(Base):
    """Daily weather forecast from DHM/MFD Nepal API."""

    __tablename__ = "weather_forecasts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dhm_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    issue_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Bilingual analysis (weather situation)
    analysis_en: Mapped[Optional[str]] = mapped_column(Text)
    analysis_np: Mapped[Optional[str]] = mapped_column(Text)

    # Bilingual forecast text (today)
    forecast_en_1: Mapped[Optional[str]] = mapped_column(Text)
    forecast_np_1: Mapped[Optional[str]] = mapped_column(Text)

    # Bilingual forecast text (tomorrow)
    forecast_en_2: Mapped[Optional[str]] = mapped_column(Text)
    forecast_np_2: Mapped[Optional[str]] = mapped_column(Text)

    # Special weather notice
    special_notice: Mapped[Optional[str]] = mapped_column(Text)

    # Meteorologist info
    issued_by: Mapped[Optional[str]] = mapped_column(String(255))
    updated_by: Mapped[Optional[str]] = mapped_column(String(255))

    # Timestamps
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "dhm_id": self.dhm_id,
            "issue_date": self.issue_date.isoformat() if self.issue_date else None,
            "analysis": {
                "en": self.analysis_en,
                "np": self.analysis_np,
            },
            "forecast_today": {
                "en": self.forecast_en_1,
                "np": self.forecast_np_1,
            },
            "forecast_tomorrow": {
                "en": self.forecast_en_2,
                "np": self.forecast_np_2,
            },
            "special_notice": self.special_notice,
            "issued_by": self.issued_by,
            "updated_by": self.updated_by,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }
