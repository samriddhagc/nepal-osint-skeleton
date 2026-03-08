"""Add Palantir-grade corroboration and intelligence scoring fields.

This migration adds:
- Corroboration tracking: unique_sources, diversity_score, confirmation_chain, confidence_level
- Intelligence scoring: intelligence_score, actionability
- Cross-lingual tracking: languages, cross_lingual_match

Revision ID: 025
Revises: 024
Create Date: 2026-02-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # Corroboration Tracking Fields
    # ============================================================
    op.add_column(
        "story_clusters",
        sa.Column(
            "unique_sources",
            postgresql.ARRAY(sa.String),
            nullable=True,
            comment="List of unique source IDs backing this story",
        ),
    )
    op.add_column(
        "story_clusters",
        sa.Column(
            "diversity_score",
            sa.Float,
            nullable=True,
            server_default="0.0",
            comment="Simpson Diversity Index (0-1, higher = more diverse sources)",
        ),
    )
    op.add_column(
        "story_clusters",
        sa.Column(
            "confirmation_chain",
            postgresql.JSONB,
            nullable=True,
            comment="Chronological chain of source confirmations [{source, timestamp, snippet}]",
        ),
    )
    op.add_column(
        "story_clusters",
        sa.Column(
            "confidence_level",
            sa.String(30),
            nullable=True,
            server_default="single_source",
            comment="single_source | corroborated | well_corroborated | highly_corroborated",
        ),
    )

    # ============================================================
    # Intelligence Scoring Fields
    # ============================================================
    op.add_column(
        "story_clusters",
        sa.Column(
            "intelligence_score",
            sa.Float,
            nullable=True,
            comment="Weighted intelligence score (0-100)",
        ),
    )
    op.add_column(
        "story_clusters",
        sa.Column(
            "actionability",
            sa.String(20),
            nullable=True,
            comment="immediate | monitor | archive",
        ),
    )

    # ============================================================
    # Cross-Lingual Tracking Fields
    # ============================================================
    op.add_column(
        "story_clusters",
        sa.Column(
            "languages",
            postgresql.ARRAY(sa.String),
            nullable=True,
            comment="Languages present in cluster stories",
        ),
    )
    op.add_column(
        "story_clusters",
        sa.Column(
            "cross_lingual_match",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether cluster contains stories in multiple languages",
        ),
    )

    # Indexes for efficient querying
    op.create_index(
        "idx_clusters_confidence_level",
        "story_clusters",
        ["confidence_level"],
    )
    op.create_index(
        "idx_clusters_actionability",
        "story_clusters",
        ["actionability"],
    )
    op.create_index(
        "idx_clusters_intelligence_score",
        "story_clusters",
        ["intelligence_score"],
    )
    op.create_index(
        "idx_clusters_cross_lingual",
        "story_clusters",
        ["cross_lingual_match"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_clusters_cross_lingual", table_name="story_clusters")
    op.drop_index("idx_clusters_intelligence_score", table_name="story_clusters")
    op.drop_index("idx_clusters_actionability", table_name="story_clusters")
    op.drop_index("idx_clusters_confidence_level", table_name="story_clusters")

    # Drop columns
    op.drop_column("story_clusters", "cross_lingual_match")
    op.drop_column("story_clusters", "languages")
    op.drop_column("story_clusters", "actionability")
    op.drop_column("story_clusters", "intelligence_score")
    op.drop_column("story_clusters", "confidence_level")
    op.drop_column("story_clusters", "confirmation_chain")
    op.drop_column("story_clusters", "diversity_score")
    op.drop_column("story_clusters", "unique_sources")
