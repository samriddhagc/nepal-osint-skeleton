"""Add tweet_clusters table and dedup/location columns to tweets.

Revision ID: 055
Revises: 054
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tweet_clusters table
    op.create_table(
        "tweet_clusters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "representative_tweet_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tweets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tweet_count", sa.Integer, server_default="1", nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("districts", JSONB, server_default="[]", nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Add columns to tweets table
    op.add_column("tweets", sa.Column("content_hash", sa.String(32), nullable=True))
    op.add_column(
        "tweets",
        sa.Column(
            "tweet_cluster_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tweet_clusters.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "tweets",
        sa.Column("districts", JSONB, server_default="[]", nullable=False),
    )
    op.add_column(
        "tweets",
        sa.Column("provinces", JSONB, server_default="[]", nullable=False),
    )

    # Indexes
    op.create_index("idx_tweets_content_hash", "tweets", ["content_hash"])
    op.create_index("idx_tweets_cluster", "tweets", ["tweet_cluster_id"])


def downgrade() -> None:
    op.drop_index("idx_tweets_cluster", table_name="tweets")
    op.drop_index("idx_tweets_content_hash", table_name="tweets")
    op.drop_column("tweets", "provinces")
    op.drop_column("tweets", "districts")
    op.drop_column("tweets", "tweet_cluster_id")
    op.drop_column("tweets", "content_hash")
    op.drop_table("tweet_clusters")
