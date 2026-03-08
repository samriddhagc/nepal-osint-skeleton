"""Initial schema with stories and sources tables.

Revision ID: 001
Revises:
Create Date: 2026-01-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create stories table
    op.create_table(
        "stories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String(64), unique=True, nullable=False),
        sa.Column("source_id", sa.String(50), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("url", sa.Text, unique=True, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("language", sa.String(10), default="en"),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("categories", postgresql.JSONB, nullable=True),
        sa.Column("nepal_relevance", sa.String(30), nullable=True),
        sa.Column("relevance_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("relevance_triggers", postgresql.JSONB, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw_data", postgresql.JSONB, nullable=True),
    )

    # Create indexes
    op.create_index("idx_stories_external_id", "stories", ["external_id"])
    op.create_index("idx_stories_source_id", "stories", ["source_id"])
    op.create_index("idx_stories_published_at", "stories", ["published_at"])
    op.create_index("idx_stories_nepal_relevance", "stories", ["nepal_relevance"])
    op.create_index("idx_stories_source_published", "stories", ["source_id", "published_at"])
    op.create_index("idx_stories_relevance_published", "stories", ["nepal_relevance", "published_at"])
    op.create_index("idx_stories_created", "stories", ["created_at"])

    # Create sources table
    op.create_table(
        "sources",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("category", sa.String(30), nullable=False, default="news"),
        sa.Column("language", sa.String(10), default="en"),
        sa.Column("priority", sa.Integer, default=5),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("poll_interval_mins", sa.Integer, default=15),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer, default=0),
        sa.Column("total_stories", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("sources")
    op.drop_table("stories")
