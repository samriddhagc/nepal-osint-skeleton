"""Source model - RSS feed configuration."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Source(Base):
    """RSS feed source configuration."""

    __tablename__ = "sources"

    # Primary key is the source ID (e.g., "tkp", "setopati")
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Classification
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="news",
        comment="news | government | disaster | economic",
    )
    language: Mapped[str] = mapped_column(String(10), default="en")
    priority: Mapped[int] = mapped_column(Integer, default=5, comment="1=highest, 10=lowest")

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    poll_interval_mins: Mapped[int] = mapped_column(Integer, default=15)

    # Health tracking
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_success_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    total_stories: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Source {self.id}: {self.name}>"
