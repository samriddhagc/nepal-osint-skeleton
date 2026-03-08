"""Add situation_briefs, province_sitreps, and fake_news_flags tables.

Tables for the Narada Analyst Agent automated intelligence pipeline.

Revision ID: 052
Revises: 051
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "052"
down_revision: Union[str, None] = "051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── situation_briefs ──
    op.create_table(
        "situation_briefs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_number", sa.Integer, nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("national_summary", sa.Text, nullable=True),
        sa.Column("national_analysis", JSONB, nullable=True),
        sa.Column("hotspots", JSONB, nullable=True),
        sa.Column("trend_vs_previous", sa.String(20), nullable=True),
        sa.Column("key_judgment", sa.Text, nullable=True),
        sa.Column("stories_analyzed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clusters_analyzed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("claude_calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_briefs_status_created",
        "situation_briefs",
        ["status", "created_at"],
    )

    # ── province_sitreps ──
    op.create_table(
        "province_sitreps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brief_id",
            UUID(as_uuid=True),
            sa.ForeignKey("situation_briefs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("province_id", sa.Integer, nullable=False),
        sa.Column("province_name", sa.String(50), nullable=False),
        sa.Column("bluf", sa.Text, nullable=True),
        sa.Column("security", sa.Text, nullable=True),
        sa.Column("political", sa.Text, nullable=True),
        sa.Column("economic", sa.Text, nullable=True),
        sa.Column("disaster", sa.Text, nullable=True),
        sa.Column("election", sa.Text, nullable=True),
        sa.Column("threat_level", sa.String(20), nullable=True),
        sa.Column("threat_trajectory", sa.String(20), nullable=True),
        sa.Column("hotspots", JSONB, nullable=True),
        sa.Column("flagged_stories", JSONB, nullable=True),
        sa.Column("story_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_sitreps_brief_province",
        "province_sitreps",
        ["brief_id", "province_id"],
    )

    # ── fake_news_flags ──
    op.create_table(
        "fake_news_flags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brief_id",
            UUID(as_uuid=True),
            sa.ForeignKey("situation_briefs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "story_id",
            UUID(as_uuid=True),
            sa.ForeignKey("stories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "cluster_id",
            UUID(as_uuid=True),
            sa.ForeignKey("story_clusters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("headline", sa.Text, nullable=False),
        sa.Column("source_name", sa.String(100), nullable=True),
        sa.Column("flag_reason", sa.Text, nullable=False),
        sa.Column("evidence", JSONB, nullable=True),
        sa.Column("verdict", sa.String(20), nullable=True),
        sa.Column("verdict_reasoning", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_flags_verdict", "fake_news_flags", ["verdict"])
    op.create_index("idx_flags_created", "fake_news_flags", ["created_at"])
    op.create_index("idx_flags_brief_id", "fake_news_flags", ["brief_id"])
    op.create_index("idx_flags_story_id", "fake_news_flags", ["story_id"])


def downgrade() -> None:
    op.drop_table("fake_news_flags")
    op.drop_table("province_sitreps")
    op.drop_table("situation_briefs")
