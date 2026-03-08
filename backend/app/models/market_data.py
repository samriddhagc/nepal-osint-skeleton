"""Market data models for NEPSE, forex, gold/silver, and fuel prices."""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Numeric, DateTime, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarketDataType(str, Enum):
    """Types of market data."""
    NEPSE = "nepse"
    FOREX_USD = "forex_usd"
    GOLD = "gold"
    SILVER = "silver"
    PETROL = "petrol"
    DIESEL = "diesel"
    KEROSENE = "kerosene"
    LPG = "lpg"


class MarketData(Base):
    """Market data record for various financial indicators."""

    __tablename__ = "market_data"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Data type identifier
    data_type: Mapped[MarketDataType] = mapped_column(
        SQLEnum(MarketDataType, native_enum=False),
        nullable=False,
    )

    # Value and unit
    value: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=4), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)  # NPR, NPR/tola, NPR/litre, points

    # Change from previous value
    previous_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=12, scale=4))
    change_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=12, scale=4))
    change_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=8, scale=4))

    # Source info
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Timestamps
    data_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )  # The date this data is for
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_market_data_type_date", "data_type", "data_date"),
        Index("ix_market_data_fetched", "fetched_at"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "data_type": self.data_type.value,
            "value": float(self.value),
            "unit": self.unit,
            "previous_value": float(self.previous_value) if self.previous_value else None,
            "change_amount": float(self.change_amount) if self.change_amount else None,
            "change_percent": float(self.change_percent) if self.change_percent else None,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "data_date": self.data_date.isoformat() if self.data_date else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


# Source registry for market data
MARKET_SOURCES = {
    "nrb": {
        "name": "Nepal Rastra Bank",
        "url": "https://www.nrb.org.np/api/forex/v1/rates",
        "data_types": [MarketDataType.FOREX_USD],
    },
    "fenegosida": {
        "name": "FENEGOSIDA",
        "url": "https://www.fenegosida.org/",
        "data_types": [MarketDataType.GOLD, MarketDataType.SILVER],
    },
    "noc": {
        "name": "Nepal Oil Corporation",
        "url": "https://noc.org.np/retailprice",
        "data_types": [MarketDataType.PETROL, MarketDataType.DIESEL, MarketDataType.KEROSENE, MarketDataType.LPG],
    },
    "nepse": {
        "name": "Nepal Stock Exchange",
        "url": "https://www.nepalstock.com/",
        "data_types": [MarketDataType.NEPSE],
    },
}
