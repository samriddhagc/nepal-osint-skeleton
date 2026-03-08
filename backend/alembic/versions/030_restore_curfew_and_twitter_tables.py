"""Restore curfew_alerts + Twitter tables that were incorrectly dropped.

Revision ID: 030
Revises: 029
Create Date: 2026-02-04

The d040fea4e3bf migration was auto-generated while some models were missing
from Alembic metadata, and it dropped `curfew_alerts` and Twitter tables
(`tweets`, `twitter_accounts`, `twitter_queries`) in upgrade().

This revision restores those tables if they are missing so the analyst
dashboard and ingestion services don't 500 at runtime.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Curfew alerts
    # NOTE: asyncpg disallows multiple SQL statements per prepared statement,
    # so keep each op.execute to a single statement.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS curfew_alerts (
          id uuid PRIMARY KEY,
          district varchar(100) NOT NULL,
          province varchar(100),
          announcement_id uuid REFERENCES govt_announcements(id) ON DELETE SET NULL,
          title text NOT NULL,
          source varchar(255) NOT NULL,
          source_name varchar(255),
          matched_keywords jsonb,
          detected_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          is_active boolean NOT NULL DEFAULT true,
          is_confirmed boolean NOT NULL DEFAULT false,
          severity varchar(20) NOT NULL DEFAULT 'high',
          notes text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_curfew_alerts_district ON curfew_alerts (district)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_curfew_alerts_is_active ON curfew_alerts (is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_curfew_alerts_expires_at ON curfew_alerts (expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_curfew_alerts_severity ON curfew_alerts (severity)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_curfew_alerts_active_district ON curfew_alerts (is_active, district) WHERE is_active = true"
    )

    # Tweets
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tweets (
          id uuid PRIMARY KEY,
          tweet_id varchar(64) NOT NULL UNIQUE,
          author_id varchar(64) NOT NULL,
          conversation_id varchar(64),
          author_username varchar(100),
          author_name varchar(200),
          author_verified boolean DEFAULT false,
          text text NOT NULL,
          language varchar(10) DEFAULT 'en',
          is_retweet boolean DEFAULT false,
          is_reply boolean DEFAULT false,
          is_quote boolean DEFAULT false,
          retweet_count integer DEFAULT 0,
          reply_count integer DEFAULT 0,
          like_count integer DEFAULT 0,
          quote_count integer DEFAULT 0,
          impression_count integer DEFAULT 0,
          hashtags varchar[],
          mentions varchar[],
          urls varchar[],
          geo jsonb,
          in_reply_to_user_id varchar(64),
          in_reply_to_tweet_id varchar(64),
          quoted_tweet_id varchar(64),
          retweeted_tweet_id varchar(64),
          source_query varchar(500),
          nepal_relevance varchar(50),
          category varchar(50),
          severity varchar(20),
          is_processed boolean DEFAULT false,
          is_relevant boolean,
          relevance_score double precision,
          story_id uuid REFERENCES stories(id) ON DELETE SET NULL,
          tweeted_at timestamptz,
          fetched_at timestamptz,
          processed_at timestamptz,
          created_at timestamptz DEFAULT now()
        )
        """
    )
    # Indexes matching earlier migrations / ORM expectations
    op.execute("CREATE INDEX IF NOT EXISTS ix_tweets_tweet_id ON tweets (tweet_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tweets_author_id ON tweets (author_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tweets_author_username ON tweets (author_username)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tweets_category ON tweets (category)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tweets_nepal_relevance ON tweets (nepal_relevance)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tweets_is_processed ON tweets (is_processed)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tweets_author_time ON tweets (author_username, tweeted_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tweets_relevance_time ON tweets (nepal_relevance, tweeted_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tweets_category_time ON tweets (category, tweeted_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tweets_unprocessed ON tweets (is_processed, fetched_at)")

    # Twitter accounts
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS twitter_accounts (
          id uuid PRIMARY KEY,
          twitter_id varchar(64) NOT NULL UNIQUE,
          username varchar(100) NOT NULL UNIQUE,
          name varchar(200),
          description text,
          verified boolean DEFAULT false,
          followers_count integer DEFAULT 0,
          is_active boolean DEFAULT true,
          priority integer DEFAULT 3,
          category varchar(50),
          last_tweet_id varchar(64),
          last_fetched_at timestamptz,
          tweet_count integer DEFAULT 0,
          created_at timestamptz DEFAULT now(),
          updated_at timestamptz DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_twitter_accounts_twitter_id ON twitter_accounts (twitter_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_twitter_accounts_username ON twitter_accounts (username)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_twitter_accounts_is_active ON twitter_accounts (is_active)")

    # Twitter queries
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS twitter_queries (
          id uuid PRIMARY KEY,
          name varchar(200) NOT NULL,
          query text NOT NULL,
          description text,
          is_active boolean DEFAULT true,
          priority integer DEFAULT 3,
          max_results integer DEFAULT 10,
          poll_interval_mins integer DEFAULT 60,
          category varchar(50),
          last_fetched_at timestamptz,
          last_result_count integer DEFAULT 0,
          total_results integer DEFAULT 0,
          created_at timestamptz DEFAULT now(),
          updated_at timestamptz DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_twitter_queries_is_active ON twitter_queries (is_active)")


def downgrade() -> None:
    # Best-effort cleanup (safe even if tables don't exist).
    # NOTE: asyncpg disallows multiple SQL statements per prepared statement.
    op.execute("DROP INDEX IF EXISTS ix_twitter_queries_is_active")
    op.execute("DROP TABLE IF EXISTS twitter_queries")

    op.execute("DROP INDEX IF EXISTS ix_twitter_accounts_is_active")
    op.execute("DROP INDEX IF EXISTS ix_twitter_accounts_username")
    op.execute("DROP INDEX IF EXISTS ix_twitter_accounts_twitter_id")
    op.execute("DROP TABLE IF EXISTS twitter_accounts")

    op.execute("DROP INDEX IF EXISTS idx_tweets_unprocessed")
    op.execute("DROP INDEX IF EXISTS idx_tweets_category_time")
    op.execute("DROP INDEX IF EXISTS idx_tweets_relevance_time")
    op.execute("DROP INDEX IF EXISTS idx_tweets_author_time")
    op.execute("DROP INDEX IF EXISTS ix_tweets_is_processed")
    op.execute("DROP INDEX IF EXISTS ix_tweets_nepal_relevance")
    op.execute("DROP INDEX IF EXISTS ix_tweets_category")
    op.execute("DROP INDEX IF EXISTS ix_tweets_author_username")
    op.execute("DROP INDEX IF EXISTS ix_tweets_author_id")
    op.execute("DROP INDEX IF EXISTS ix_tweets_tweet_id")
    op.execute("DROP TABLE IF EXISTS tweets")

    op.execute("DROP INDEX IF EXISTS idx_curfew_alerts_active_district")
    op.execute("DROP INDEX IF EXISTS idx_curfew_alerts_severity")
    op.execute("DROP INDEX IF EXISTS idx_curfew_alerts_expires_at")
    op.execute("DROP INDEX IF EXISTS idx_curfew_alerts_is_active")
    op.execute("DROP INDEX IF EXISTS idx_curfew_alerts_district")
    op.execute("DROP TABLE IF EXISTS curfew_alerts")
