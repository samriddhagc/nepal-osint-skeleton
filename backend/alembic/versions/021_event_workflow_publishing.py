"""Add analyst workflow + publishing fields to story clusters.

Revision ID: 021
Revises: 020
Create Date: 2026-02-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Workflow / analyst overrides (event-first)
    op.add_column(
        "story_clusters",
        sa.Column(
            "workflow_status",
            sa.String(20),
            nullable=False,
            server_default="unreviewed",
            comment="unreviewed|monitoring|verified|published|rejected",
        ),
    )
    op.add_column("story_clusters", sa.Column("analyst_headline", sa.Text, nullable=True))
    op.add_column("story_clusters", sa.Column("analyst_summary", sa.Text, nullable=True))
    op.add_column("story_clusters", sa.Column("analyst_category", sa.String(20), nullable=True))
    op.add_column("story_clusters", sa.Column("analyst_severity", sa.String(20), nullable=True))
    op.add_column("story_clusters", sa.Column("analyst_notes", sa.Text, nullable=True))

    # Verification / publishing metadata
    op.add_column(
        "story_clusters",
        sa.Column(
            "verified_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("story_clusters", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        "story_clusters",
        sa.Column(
            "is_published",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "story_clusters",
        sa.Column(
            "published_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("story_clusters", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("story_clusters", sa.Column("customer_brief", sa.Text, nullable=True))

    # Helpful indexes for ops queries
    op.create_index("idx_clusters_workflow_status", "story_clusters", ["workflow_status"])
    op.create_index("idx_clusters_is_published", "story_clusters", ["is_published"])
    op.create_index("idx_clusters_published_at", "story_clusters", ["published_at"])


def downgrade() -> None:
    op.drop_index("idx_clusters_published_at", table_name="story_clusters")
    op.drop_index("idx_clusters_is_published", table_name="story_clusters")
    op.drop_index("idx_clusters_workflow_status", table_name="story_clusters")

    op.drop_column("story_clusters", "customer_brief")
    op.drop_column("story_clusters", "published_at")
    op.drop_column("story_clusters", "published_by_id")
    op.drop_column("story_clusters", "is_published")
    op.drop_column("story_clusters", "verified_at")
    op.drop_column("story_clusters", "verified_by_id")

    op.drop_column("story_clusters", "analyst_notes")
    op.drop_column("story_clusters", "analyst_severity")
    op.drop_column("story_clusters", "analyst_category")
    op.drop_column("story_clusters", "analyst_summary")
    op.drop_column("story_clusters", "analyst_headline")
    op.drop_column("story_clusters", "workflow_status")

