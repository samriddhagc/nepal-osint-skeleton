"""Curfew alert model for tracking active curfew orders."""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CurfewAlert(Base):
    """
    Curfew alert detected from DAO/Provincial government announcements.

    Automatically created when a government announcement contains curfew-related
    keywords (कर्फ्यु, निषेधाज्ञा, curfew, etc.). Alerts expire after 24 hours
    by default but can be extended.
    """

    __tablename__ = "curfew_alerts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # District affected by curfew
    district: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    province: Mapped[Optional[str]] = mapped_column(String(100))

    # Link to source announcement
    announcement_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("govt_announcements.id", ondelete="SET NULL"),
        nullable=True
    )

    # Curfew details
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)  # DAO domain or provincial govt
    source_name: Mapped[Optional[str]] = mapped_column(String(255))  # Human-readable source name

    # Detection metadata
    matched_keywords: Mapped[Optional[List]] = mapped_column(JSONB, default=list)

    # Time bounds
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)  # Manual confirmation

    # Severity (based on keywords and content analysis)
    severity: Mapped[str] = mapped_column(
        String(20),
        default="high"  # low, medium, high, critical
    )

    # Additional context
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "district": self.district,
            "province": self.province,
            "title": self.title,
            "source": self.source,
            "source_name": self.source_name,
            "matched_keywords": self.matched_keywords or [],
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
            "is_confirmed": self.is_confirmed,
            "severity": self.severity,
            "announcement_id": str(self.announcement_id) if self.announcement_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @property
    def is_expired(self) -> bool:
        """Check if curfew has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def hours_remaining(self) -> float:
        """Get hours remaining until expiration."""
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, delta.total_seconds() / 3600)

    @classmethod
    def create_from_announcement(
        cls,
        district: str,
        title: str,
        source: str,
        matched_keywords: List[str],
        announcement_id: Optional[UUID] = None,
        source_name: Optional[str] = None,
        province: Optional[str] = None,
        duration_hours: int = 24,
    ) -> "CurfewAlert":
        """
        Factory method to create a curfew alert.

        Args:
            district: Name of the affected district
            title: Title of the announcement
            source: Source domain (e.g., daokathmandu.moha.gov.np)
            matched_keywords: List of keywords that triggered detection
            announcement_id: Optional link to source announcement
            source_name: Human-readable source name
            province: Province name
            duration_hours: Hours until alert expires (default 24)
        """
        now = datetime.now(timezone.utc)
        return cls(
            district=district,
            province=province,
            announcement_id=announcement_id,
            title=title,
            source=source,
            source_name=source_name,
            matched_keywords=matched_keywords,
            detected_at=now,
            expires_at=now + timedelta(hours=duration_hours),
            is_active=True,
            severity="critical" if "कर्फ्यु" in " ".join(matched_keywords) else "high",
        )


# District to Province mapping for Nepal
DISTRICT_PROVINCE_MAP = {
    # Koshi Province (Province 1)
    "taplejung": "Koshi", "panchthar": "Koshi", "ilam": "Koshi",
    "jhapa": "Koshi", "morang": "Koshi", "sunsari": "Koshi",
    "dhankuta": "Koshi", "terhathum": "Koshi", "sankhuwasabha": "Koshi",
    "bhojpur": "Koshi", "solukhumbu": "Koshi", "okhaldhunga": "Koshi",
    "khotang": "Koshi", "udayapur": "Koshi",

    # Madhesh Province (Province 2)
    "saptari": "Madhesh", "siraha": "Madhesh", "dhanusa": "Madhesh",
    "mahottari": "Madhesh", "sarlahi": "Madhesh", "rautahat": "Madhesh",
    "bara": "Madhesh", "parsa": "Madhesh",

    # Bagmati Province (Province 3)
    "dolakha": "Bagmati", "sindhupalchok": "Bagmati", "rasuwa": "Bagmati",
    "dhading": "Bagmati", "nuwakot": "Bagmati", "kathmandu": "Bagmati",
    "bhaktapur": "Bagmati", "lalitpur": "Bagmati", "kavrepalanchok": "Bagmati",
    "ramechhap": "Bagmati", "sindhuli": "Bagmati", "makwanpur": "Bagmati",
    "chitwan": "Bagmati",

    # Gandaki Province (Province 4)
    "gorkha": "Gandaki", "lamjung": "Gandaki", "tanahun": "Gandaki",
    "syangja": "Gandaki", "kaski": "Gandaki", "manang": "Gandaki",
    "mustang": "Gandaki", "myagdi": "Gandaki", "parbat": "Gandaki",
    "baglung": "Gandaki", "nawalparasi_east": "Gandaki",

    # Lumbini Province (Province 5)
    "nawalparasi_west": "Lumbini", "rupandehi": "Lumbini",
    "kapilvastu": "Lumbini", "palpa": "Lumbini", "arghakhanchi": "Lumbini",
    "gulmi": "Lumbini", "pyuthan": "Lumbini", "rolpa": "Lumbini",
    "rukum_east": "Lumbini", "dang": "Lumbini", "banke": "Lumbini",
    "bardiya": "Lumbini",

    # Karnali Province (Province 6)
    "dolpa": "Karnali", "mugu": "Karnali", "humla": "Karnali",
    "jumla": "Karnali", "kalikot": "Karnali", "dailekh": "Karnali",
    "jajarkot": "Karnali", "rukum_west": "Karnali", "salyan": "Karnali",
    "surkhet": "Karnali",

    # Sudurpashchim Province (Province 7)
    "bajura": "Sudurpashchim", "bajhang": "Sudurpashchim",
    "achham": "Sudurpashchim", "doti": "Sudurpashchim",
    "kailali": "Sudurpashchim", "kanchanpur": "Sudurpashchim",
    "dadeldhura": "Sudurpashchim", "baitadi": "Sudurpashchim",
    "darchula": "Sudurpashchim",
}


def get_province_for_district(district: str) -> Optional[str]:
    """Get province name for a district."""
    return DISTRICT_PROVINCE_MAP.get(district.lower().replace(" ", "_"))
