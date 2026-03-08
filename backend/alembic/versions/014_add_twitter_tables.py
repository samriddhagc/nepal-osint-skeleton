"""Add Twitter/X social media tables.

Revision ID: 014
Revises: 013
Create Date: 2026-01-28

Creates tables for:
- tweets: Individual tweet storage
- twitter_accounts: Monitored accounts
- twitter_queries: Saved search queries
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tweets table
    op.create_table(
        "tweets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tweet_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("author_id", sa.String(64), nullable=False, index=True),
        sa.Column("conversation_id", sa.String(64)),
        sa.Column("author_username", sa.String(100), index=True),
        sa.Column("author_name", sa.String(200)),
        sa.Column("author_verified", sa.Boolean, default=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("language", sa.String(10), default="en"),
        sa.Column("is_retweet", sa.Boolean, default=False),
        sa.Column("is_reply", sa.Boolean, default=False),
        sa.Column("is_quote", sa.Boolean, default=False),
        sa.Column("retweet_count", sa.Integer, default=0),
        sa.Column("reply_count", sa.Integer, default=0),
        sa.Column("like_count", sa.Integer, default=0),
        sa.Column("quote_count", sa.Integer, default=0),
        sa.Column("impression_count", sa.Integer, default=0),
        sa.Column("hashtags", postgresql.ARRAY(sa.String)),
        sa.Column("mentions", postgresql.ARRAY(sa.String)),
        sa.Column("urls", postgresql.ARRAY(sa.String)),
        sa.Column("geo", postgresql.JSONB),
        sa.Column("in_reply_to_user_id", sa.String(64)),
        sa.Column("in_reply_to_tweet_id", sa.String(64)),
        sa.Column("quoted_tweet_id", sa.String(64)),
        sa.Column("retweeted_tweet_id", sa.String(64)),
        sa.Column("source_query", sa.String(500)),
        sa.Column("nepal_relevance", sa.String(50), index=True),
        sa.Column("category", sa.String(50), index=True),
        sa.Column("severity", sa.String(20)),
        sa.Column("is_processed", sa.Boolean, default=False, index=True),
        sa.Column("is_relevant", sa.Boolean),
        sa.Column("relevance_score", sa.Float),
        sa.Column(
            "story_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stories.id", ondelete="SET NULL"),
        ),
        sa.Column("tweeted_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # Create composite indexes for common queries
    op.create_index(
        "idx_tweets_author_time", "tweets", ["author_username", "tweeted_at"]
    )
    op.create_index(
        "idx_tweets_relevance_time", "tweets", ["nepal_relevance", "tweeted_at"]
    )
    op.create_index("idx_tweets_category_time", "tweets", ["category", "tweeted_at"])
    op.create_index("idx_tweets_unprocessed", "tweets", ["is_processed", "fetched_at"])

    # Create twitter_accounts table
    op.create_table(
        "twitter_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("twitter_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(200)),
        sa.Column("description", sa.Text),
        sa.Column("verified", sa.Boolean, default=False),
        sa.Column("followers_count", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, default=True, index=True),
        sa.Column("priority", sa.Integer, default=3),
        sa.Column("category", sa.String(50)),
        sa.Column("last_tweet_id", sa.String(64)),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True)),
        sa.Column("tweet_count", sa.Integer, default=0),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Create twitter_queries table
    op.create_table(
        "twitter_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("is_active", sa.Boolean, default=True, index=True),
        sa.Column("priority", sa.Integer, default=3),
        sa.Column("max_results", sa.Integer, default=10),
        sa.Column("poll_interval_mins", sa.Integer, default=60),
        sa.Column("category", sa.String(50)),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True)),
        sa.Column("last_result_count", sa.Integer, default=0),
        sa.Column("total_results", sa.Integer, default=0),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("twitter_queries")
    op.drop_table("twitter_accounts")
    op.drop_index("idx_tweets_unprocessed", "tweets")
    op.drop_index("idx_tweets_category_time", "tweets")
    op.drop_index("idx_tweets_relevance_time", "tweets")
    op.drop_index("idx_tweets_author_time", "tweets")
    op.drop_table("tweets")
