"""Add categories, severity, and clustering support.

Revision ID: 002
Revises: 001
Create Date: 2026-01-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to stories table
    op.add_column(
        "stories",
        sa.Column("category", sa.String(20), nullable=True),
    )
    op.add_column(
        "stories",
        sa.Column("severity", sa.String(20), nullable=True),
    )
    op.add_column(
        "stories",
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Create story_clusters table
    op.create_table(
        "story_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("headline", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("category", sa.String(20), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("story_count", sa.Integer, default=1),
        sa.Column("source_count", sa.Integer, default=1),
        sa.Column("first_published", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create indexes for stories
    op.create_index("idx_stories_category", "stories", ["category"])
    op.create_index("idx_stories_severity", "stories", ["severity"])
    op.create_index("idx_stories_cluster_id", "stories", ["cluster_id"])

    # Create indexes for story_clusters
    op.create_index("idx_clusters_category", "story_clusters", ["category"])
    op.create_index("idx_clusters_severity", "story_clusters", ["severity"])
    op.create_index("idx_clusters_first_published", "story_clusters", ["first_published"])

    # Add foreign key constraint
    op.create_foreign_key(
        "fk_stories_cluster_id",
        "stories",
        "story_clusters",
        ["cluster_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop foreign key constraint
    op.drop_constraint("fk_stories_cluster_id", "stories", type_="foreignkey")

    # Drop indexes from stories
    op.drop_index("idx_stories_category", table_name="stories")
    op.drop_index("idx_stories_severity", table_name="stories")
    op.drop_index("idx_stories_cluster_id", table_name="stories")

    # Drop story_clusters table (automatically drops its indexes)
    op.drop_table("story_clusters")

    # Drop columns from stories
    op.drop_column("stories", "cluster_id")
    op.drop_column("stories", "severity")
    op.drop_column("stories", "category")
