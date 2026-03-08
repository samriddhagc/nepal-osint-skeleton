"""PoliticalEntity model - canonical knowledge base of political actors."""
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import String, Text, DateTime, Boolean, Integer, Float, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB, ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.story_entity_link import StoryEntityLink
    from app.models.election import Candidate
    from app.models.parliament import MPPerformance
    from app.models.ministerial_position import MinisterialPosition
    from app.models.company import CompanyDirector


class EntityType(str, Enum):
    """Types of political entities."""
    PERSON = "person"
    PARTY = "party"
    ORGANIZATION = "organization"
    INSTITUTION = "institution"


class EntityTrend(str, Enum):
    """Trend direction for entity mentions."""
    RISING = "rising"
    STABLE = "stable"
    FALLING = "falling"


class PoliticalEntity(Base):
    """
    Canonical political entity in the knowledge base.

    Represents politicians, parties, organizations, and institutions
    that appear in news stories. Linked to stories via StoryEntityLink.
    """

    __tablename__ = "political_entities"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Canonical identifier (e.g., 'oli', 'karki', 'uml')
    canonical_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    # Names
    name_en: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    name_ne: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Entity type
    entity_type: Mapped[EntityType] = mapped_column(
        ENUM(
            EntityType,
            name="entity_type",
            create_type=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=EntityType.PERSON,
    )

    # Political affiliation (for persons)
    party: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # Role/position (e.g., "Prime Minister", "Party Chair")
    role: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Alternative names/aliases for matching
    aliases: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Description
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Profile image URL
    image_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    # Mention statistics (computed/cached)
    total_mentions: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    mentions_24h: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    mentions_7d: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )

    # Trend (computed from mention velocity)
    trend: Mapped[EntityTrend] = mapped_column(
        ENUM(
            EntityTrend,
            name="entity_trend",
            create_type=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=EntityTrend.STABLE,
    )

    # Last mention timestamp
    last_mentioned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Status flags
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )
    is_watchable: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )

    # Enrichment fields (absorbed from satellite tables)
    biography: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    biography_source: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    education: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    education_institution: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    age: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    gender: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    former_parties: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
    )
    current_position: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    position_history: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Extra metadata
    extra_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    story_links: Mapped[list["StoryEntityLink"]] = relationship(
        "StoryEntityLink",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    candidates: Mapped[list["Candidate"]] = relationship(
        "Candidate",
        back_populates="political_entity",
        foreign_keys="Candidate.linked_entity_id",
    )
    mp_records: Mapped[list["MPPerformance"]] = relationship(
        "MPPerformance",
        back_populates="political_entity",
        foreign_keys="MPPerformance.linked_entity_id",
    )
    ministerial_positions: Mapped[list["MinisterialPosition"]] = relationship(
        "MinisterialPosition",
        back_populates="political_entity",
        foreign_keys="MinisterialPosition.linked_entity_id",
    )
    company_directorships: Mapped[list["CompanyDirector"]] = relationship(
        "CompanyDirector",
        back_populates="political_entity",
        foreign_keys="CompanyDirector.linked_entity_id",
    )

    def __repr__(self) -> str:
        return f"<PoliticalEntity {self.canonical_id}: {self.name_en}>"

    @property
    def display_name(self) -> str:
        """Get display name (prefer Nepali if available)."""
        return self.name_ne or self.name_en

    @property
    def all_names(self) -> list[str]:
        """Get all name variations including aliases."""
        names = [self.name_en]
        if self.name_ne:
            names.append(self.name_ne)
        if self.aliases:
            names.extend(self.aliases)
        return names
