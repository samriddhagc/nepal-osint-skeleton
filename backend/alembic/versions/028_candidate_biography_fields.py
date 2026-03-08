"""Add biography and alias fields to candidates.

Revision ID: 028_candidate_bio
Revises: 027_entity_relationships_network
Create Date: 2026-02-03

Adds fields for:
- name_en_roman: Actual English/romanized transliteration of name
- aliases: JSON array of alternative name spellings for search
- biography: Short biography for notable candidates
- biography_source: Source URL for the biography
- is_notable: Flag for candidates with significant public profile
- previous_positions: JSON for previous elected positions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


revision = "028"
down_revision = "d040fea4e3bf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to candidates table
    op.add_column(
        "candidates",
        sa.Column("name_en_roman", sa.String(255), nullable=True, comment="Romanized English transliteration")
    )
    op.add_column(
        "candidates",
        sa.Column("aliases", JSON, nullable=True, comment="Alternative name spellings for search")
    )
    op.add_column(
        "candidates",
        sa.Column("biography", sa.Text, nullable=True, comment="Short biography")
    )
    op.add_column(
        "candidates",
        sa.Column("biography_source", sa.String(500), nullable=True, comment="Source URL for biography")
    )
    op.add_column(
        "candidates",
        sa.Column("is_notable", sa.Boolean, default=False, nullable=True, comment="Has significant public profile")
    )
    op.add_column(
        "candidates",
        sa.Column("previous_positions", JSON, nullable=True, comment="Previous elected positions")
    )

    # Add index for searching by romanized name
    op.create_index(
        "idx_candidates_name_en_roman",
        "candidates",
        ["name_en_roman"],
        postgresql_ops={"name_en_roman": "varchar_pattern_ops"}
    )

    # Add index for notable candidates
    op.create_index(
        "idx_candidates_is_notable",
        "candidates",
        ["is_notable"],
        postgresql_where=sa.text("is_notable = true")
    )


def downgrade() -> None:
    op.drop_index("idx_candidates_is_notable", "candidates")
    op.drop_index("idx_candidates_name_en_roman", "candidates")
    op.drop_column("candidates", "previous_positions")
    op.drop_column("candidates", "is_notable")
    op.drop_column("candidates", "biography_source")
    op.drop_column("candidates", "biography")
    op.drop_column("candidates", "aliases")
    op.drop_column("candidates", "name_en_roman")
