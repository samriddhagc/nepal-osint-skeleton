"""Political entities schema - canonical entity KB and story-entity linking.

This migration enables Palantir-grade entity tracking:
- political_entities: Canonical KB of politicians, parties, organizations
- story_entity_links: Many-to-many linking stories to entities

Revision ID: 019
Revises: 018
Create Date: 2026-01-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create entity_type ENUM
    op.execute("CREATE TYPE entity_type AS ENUM ('person', 'party', 'organization', 'institution')")

    # Create entity_trend ENUM
    op.execute("CREATE TYPE entity_trend AS ENUM ('rising', 'stable', 'falling')")

    # Create political_entities table - canonical entity KB
    op.create_table(
        "political_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_id", sa.String(50), unique=True, nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("name_ne", sa.String(255), nullable=True),
        sa.Column(
            "entity_type",
            postgresql.ENUM("person", "party", "organization", "institution", name="entity_type", create_type=False),
            nullable=False,
            server_default="person",
        ),
        sa.Column("party", sa.String(100), nullable=True),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("aliases", postgresql.JSONB, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        # Computed mention stats
        sa.Column("total_mentions", sa.Integer, server_default="0"),
        sa.Column("mentions_24h", sa.Integer, server_default="0"),
        sa.Column("mentions_7d", sa.Integer, server_default="0"),
        sa.Column(
            "trend",
            postgresql.ENUM("rising", "stable", "falling", name="entity_trend", create_type=False),
            nullable=False,
            server_default="stable",
        ),
        sa.Column("last_mentioned_at", sa.DateTime(timezone=True), nullable=True),
        # Metadata
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("is_watchable", sa.Boolean, server_default="true"),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_pe_canonical_id", "political_entities", ["canonical_id"])
    op.create_index("idx_pe_name_en", "political_entities", ["name_en"])
    op.create_index("idx_pe_type", "political_entities", ["entity_type"])
    op.create_index("idx_pe_party", "political_entities", ["party"])
    op.create_index("idx_pe_mentions_24h", "political_entities", ["mentions_24h", "total_mentions"])
    op.create_index("idx_pe_trend", "political_entities", ["trend"])
    op.create_index("idx_pe_active", "political_entities", ["is_active"])

    # Create story_entity_links table - many-to-many between stories and entities
    op.create_table(
        "story_entity_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "story_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("political_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_title_mention", sa.Boolean, server_default="true"),
        sa.Column("mention_count", sa.Integer, server_default="1"),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("story_id", "entity_id", name="uq_story_entity"),
    )
    op.create_index("idx_sel_story", "story_entity_links", ["story_id"])
    op.create_index("idx_sel_entity", "story_entity_links", ["entity_id"])
    op.create_index("idx_sel_entity_created", "story_entity_links", ["entity_id", "created_at"])
    op.create_index("idx_sel_created", "story_entity_links", ["created_at"])


def downgrade() -> None:
    # Drop tables
    op.drop_table("story_entity_links")
    op.drop_table("political_entities")

    # Drop ENUM types
    op.execute("DROP TYPE IF EXISTS entity_trend")
    op.execute("DROP TYPE IF EXISTS entity_type")
