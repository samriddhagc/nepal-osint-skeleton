"""
Tweet model for storing Twitter/X social media data.

Tracks tweets fetched from X API with:
- Full tweet metadata
- Author information
- Engagement metrics
- Nepal relevance classification
- Processing status
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.tweet_cluster import TweetCluster

from app.models.base import Base


class Tweet(Base):
    """
    Tweet from X/Twitter API.

    Stores individual tweets with full metadata for analysis.
    """

    __tablename__ = "tweets"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Twitter-specific IDs
    tweet_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    author_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Author info (denormalized for quick access)
    author_username: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(200))
    author_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Content
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en")

    # Tweet type
    is_retweet: Mapped[bool] = mapped_column(Boolean, default=False)
    is_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    is_quote: Mapped[bool] = mapped_column(Boolean, default=False)

    # Engagement metrics
    retweet_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    quote_count: Mapped[int] = mapped_column(Integer, default=0)
    impression_count: Mapped[int] = mapped_column(Integer, default=0)

    # Entities (stored as JSON arrays)
    hashtags: Mapped[Optional[List]] = mapped_column(ARRAY(String), default=list)
    mentions: Mapped[Optional[List]] = mapped_column(ARRAY(String), default=list)
    urls: Mapped[Optional[List]] = mapped_column(ARRAY(String), default=list)

    # Location
    geo: Mapped[Optional[dict]] = mapped_column(JSONB)

    # References to other tweets
    in_reply_to_user_id: Mapped[Optional[str]] = mapped_column(String(64))
    in_reply_to_tweet_id: Mapped[Optional[str]] = mapped_column(String(64))
    quoted_tweet_id: Mapped[Optional[str]] = mapped_column(String(64))
    retweeted_tweet_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Source tracking
    source_query: Mapped[Optional[str]] = mapped_column(String(500))

    # Classification (Nepal relevance)
    nepal_relevance: Mapped[Optional[str]] = mapped_column(
        String(50), index=True
    )  # NEPAL_DOMESTIC, NEPAL_NEIGHBOR, INTERNATIONAL, NOT_RELEVANT
    category: Mapped[Optional[str]] = mapped_column(
        String(50), index=True
    )  # political, economic, security, disaster, social
    severity: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # CRITICAL, HIGH, MEDIUM, LOW

    # Processing status
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_relevant: Mapped[Optional[bool]] = mapped_column(Boolean)
    relevance_score: Mapped[Optional[float]] = mapped_column(Float)

    # Deduplication & clustering
    content_hash: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    tweet_cluster_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tweet_clusters.id", ondelete="SET NULL"),
        index=True,
    )
    districts: Mapped[list] = mapped_column(JSONB, default=list)
    provinces: Mapped[list] = mapped_column(JSONB, default=list)
    media_urls: Mapped[list] = mapped_column(JSONB, default=list)

    # Cluster relationship
    cluster = relationship("TweetCluster", back_populates="tweets", foreign_keys=[tweet_cluster_id])

    # Linked story (if converted to story)
    story_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="SET NULL")
    )

    # Timestamps
    tweeted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Indexes for common queries
    __table_args__ = (
        Index("idx_tweets_author_time", "author_username", "tweeted_at"),
        Index("idx_tweets_relevance_time", "nepal_relevance", "tweeted_at"),
        Index("idx_tweets_category_time", "category", "tweeted_at"),
        Index("idx_tweets_unprocessed", "is_processed", "fetched_at"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "tweet_id": self.tweet_id,
            "author_id": self.author_id,
            "author_username": self.author_username,
            "author_name": self.author_name,
            "author_verified": self.author_verified,
            "text": self.text,
            "language": self.language,
            "is_retweet": self.is_retweet,
            "is_reply": self.is_reply,
            "is_quote": self.is_quote,
            "retweet_count": self.retweet_count,
            "reply_count": self.reply_count,
            "like_count": self.like_count,
            "quote_count": self.quote_count,
            "impression_count": self.impression_count,
            "hashtags": self.hashtags or [],
            "mentions": self.mentions or [],
            "urls": self.urls or [],
            "nepal_relevance": self.nepal_relevance,
            "category": self.category,
            "severity": self.severity,
            "is_relevant": self.is_relevant,
            "relevance_score": self.relevance_score,
            "source_query": self.source_query,
            "tweet_cluster_id": str(self.tweet_cluster_id) if self.tweet_cluster_id else None,
            "cluster_size": self.cluster.tweet_count if self.cluster else None,
            "districts": self.districts or [],
            "provinces": self.provinces or [],
            "media_urls": self.media_urls or [],
            "tweeted_at": self.tweeted_at.isoformat() if self.tweeted_at else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class TwitterAccount(Base):
    """
    Twitter accounts to monitor.

    Tracks specific accounts for timeline monitoring.
    """

    __tablename__ = "twitter_accounts"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Twitter account info
    twitter_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    followers_count: Mapped[int] = mapped_column(Integer, default=0)

    # Monitoring config
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1-5, lower = higher priority
    category: Mapped[Optional[str]] = mapped_column(String(50))  # news, govt, ngo, journalist

    # Tracking
    last_tweet_id: Mapped[Optional[str]] = mapped_column(String(64))
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tweet_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "twitter_id": self.twitter_id,
            "username": self.username,
            "name": self.name,
            "verified": self.verified,
            "followers_count": self.followers_count,
            "is_active": self.is_active,
            "priority": self.priority,
            "category": self.category,
            "last_fetched_at": self.last_fetched_at.isoformat() if self.last_fetched_at else None,
            "tweet_count": self.tweet_count,
        }


class TwitterQuery(Base):
    """
    Saved Twitter search queries.

    Stores queries for scheduled monitoring.
    """

    __tablename__ = "twitter_queries"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Query config
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Monitoring config
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    max_results: Mapped[int] = mapped_column(Integer, default=10)
    poll_interval_mins: Mapped[int] = mapped_column(Integer, default=60)

    # Category for results
    category: Mapped[Optional[str]] = mapped_column(String(50))

    # Tracking
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_result_count: Mapped[int] = mapped_column(Integer, default=0)
    total_results: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "query": self.query,
            "description": self.description,
            "is_active": self.is_active,
            "priority": self.priority,
            "max_results": self.max_results,
            "poll_interval_mins": self.poll_interval_mins,
            "category": self.category,
            "last_fetched_at": self.last_fetched_at.isoformat() if self.last_fetched_at else None,
            "total_results": self.total_results,
        }
