"""Add production publishing + peer review tables.

Revision ID: 026
Revises: 025
Create Date: 2026-02-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # Link cases -> story clusters (events)
    # ============================================================
    op.add_column(
        "cases",
        sa.Column(
            "linked_cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("story_clusters.id", ondelete="SET NULL"),
            nullable=True,
            comment="Optional StoryCluster (event) this case supports/publishes to",
        ),
    )
    op.create_index("idx_cases_linked_cluster", "cases", ["linked_cluster_id"])

    # ============================================================
    # Peer review verdict enum
    # ============================================================
    op.execute("CREATE TYPE peer_review_verdict AS ENUM ('agree', 'needs_correction', 'dispute')")

    # ============================================================
    # Versioned publications for public feed
    # ============================================================
    op.create_table(
        "cluster_publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("story_clusters.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("headline", sa.Text, nullable=False),
        sa.Column("category", sa.String(20), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("customer_brief", sa.Text, nullable=True),
        sa.Column("citations", postgresql.JSONB, nullable=True, comment="List of citation objects for this version"),
        sa.Column("policy_check", postgresql.JSONB, nullable=True, comment="Publish policy evaluation and warnings"),
        sa.Column("change_note", sa.Text, nullable=True, comment="What changed in this version (for corrections)"),
        sa.UniqueConstraint("cluster_id", "version", name="uq_cluster_publication_version"),
    )
    op.create_index("idx_cluster_publications_cluster", "cluster_publications", ["cluster_id"])
    op.create_index("idx_cluster_publications_created", "cluster_publications", ["created_at"])

    # ============================================================
    # Peer reviews for published events
    # ============================================================
    op.create_table(
        "cluster_peer_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("story_clusters.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "verdict",
            postgresql.ENUM("agree", "needs_correction", "dispute", name="peer_review_verdict", create_type=False),
            nullable=False,
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("cluster_id", "reviewer_id", name="uq_cluster_peer_review_reviewer"),
    )
    op.create_index("idx_cluster_peer_reviews_cluster", "cluster_peer_reviews", ["cluster_id"])
    op.create_index("idx_cluster_peer_reviews_verdict", "cluster_peer_reviews", ["verdict"])


def downgrade() -> None:
    op.drop_index("idx_cluster_peer_reviews_verdict", table_name="cluster_peer_reviews")
    op.drop_index("idx_cluster_peer_reviews_cluster", table_name="cluster_peer_reviews")
    op.drop_table("cluster_peer_reviews")

    op.drop_index("idx_cluster_publications_created", table_name="cluster_publications")
    op.drop_index("idx_cluster_publications_cluster", table_name="cluster_publications")
    op.drop_table("cluster_publications")

    op.execute("DROP TYPE peer_review_verdict")

    op.drop_index("idx_cases_linked_cluster", table_name="cases")
    op.drop_column("cases", "linked_cluster_id")

