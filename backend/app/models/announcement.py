"""Government announcement models."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GovtAnnouncement(Base):
    """Government announcement from various ministries."""

    __tablename__ = "govt_announcements"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # External ID (hash of URL for deduplication)
    external_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Source ministry/department
    source: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "moha.gov.np"
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "Ministry of Home Affairs"

    # Content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # press-release, notice, circular

    # Dates
    date_bs: Mapped[Optional[str]] = mapped_column(String(20))  # Bikram Sambat date
    date_ad: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # Gregorian date

    # Attachments (stored as JSON array)
    # Format: [{"name": "file.pdf", "url": "https://..."}]
    attachments: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)

    # Full content (fetched from detail page)
    content: Mapped[Optional[str]] = mapped_column(Text)
    content_fetched: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metadata
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_important: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "external_id": self.external_id,
            "source": self.source,
            "source_name": self.source_name,
            "title": self.title,
            "url": self.url,
            "category": self.category,
            "date_bs": self.date_bs,
            "date_ad": self.date_ad.isoformat() if self.date_ad else None,
            "attachments": self.attachments or [],
            "has_attachments": self.has_attachments,
            "content": self.content,
            "is_read": self.is_read,
            "is_important": self.is_important,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Source registry for different government websites
GOVT_SOURCES = {
    "moha.gov.np": {
        "name": "Ministry of Home Affairs",
        "name_ne": "गृह मन्त्रालय",
        "categories": ["press-release-en", "press-release-ne", "notice-en", "notice-ne"],
    },
    "opmcm.gov.np": {
        "name": "Prime Minister's Office",
        "name_ne": "प्रधानमन्त्री तथा मन्त्रिपरिषद्को कार्यालय",
        "categories": ["press-release", "cabinet-decision", "cabinet-committee-decision"],
    },
    "mofa.gov.np": {
        "name": "Ministry of Foreign Affairs",
        "name_ne": "परराष्ट्र मन्त्रालय",
        "categories": ["press-release"],
    },
    "election.gov.np": {
        "name": "Election Commission Nepal",
        "name_ne": "निर्वाचन आयोग नेपाल",
        "categories": ["press-release", "press-release-ne", "notice", "notice-ne"],
    },
}
