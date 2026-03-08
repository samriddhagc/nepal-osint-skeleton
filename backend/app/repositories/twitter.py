"""Twitter repository for database operations."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, update, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from app.models.tweet import Tweet, TwitterAccount, TwitterQuery
from app.models.tweet_cluster import TweetCluster

logger = logging.getLogger(__name__)


class TwitterRepository:
    """Repository for Twitter-related database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Tweet Operations ====================

    async def upsert_tweet(
        self,
        tweet_id: str,
        author_id: str,
        text: str,
        **kwargs,
    ) -> Tuple[Tweet, bool]:
        """
        Insert or update a tweet.

        Returns:
            Tuple of (tweet, created) where created is True if new
        """
        # Check if exists
        existing = await self.get_tweet_by_twitter_id(tweet_id)

        if existing:
            # Update metrics only
            for key in ["retweet_count", "reply_count", "like_count", "quote_count"]:
                if key in kwargs:
                    setattr(existing, key, kwargs[key])
            await self.db.commit()
            return existing, False

        # Create new
        tweet = Tweet(
            tweet_id=tweet_id,
            author_id=author_id,
            text=text,
            **kwargs,
        )
        self.db.add(tweet)
        await self.db.commit()
        await self.db.refresh(tweet)
        return tweet, True

    async def get_tweet_by_twitter_id(self, tweet_id: str) -> Optional[Tweet]:
        """Get tweet by Twitter ID."""
        result = await self.db.execute(
            select(Tweet).where(Tweet.tweet_id == tweet_id)
        )
        return result.scalar_one_or_none()

    async def get_tweet_by_id(self, id: UUID) -> Optional[Tweet]:
        """Get tweet by internal UUID."""
        result = await self.db.execute(select(Tweet).where(Tweet.id == id))
        return result.scalar_one_or_none()

    async def get_recent_tweets(
        self,
        limit: int = 50,
        hours: int = 24,
        nepal_relevance: Optional[str] = None,
        category: Optional[str] = None,
        is_relevant: Optional[bool] = None,
        source: Optional[str] = None,
        author: Optional[str] = None,
        hashtag: Optional[str] = None,
        severity: Optional[str] = None,
        ground_reports: bool = False,
    ) -> List[Tweet]:
        """Get recent tweets with optional filters.

        Args:
            source: 'accounts' for verified account tweets, 'hashtags' for hashtag searches
            author: Filter by specific author username
            hashtag: Filter by specific hashtag name (without #)
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = select(Tweet).options(selectinload(Tweet.cluster)).where(Tweet.fetched_at >= cutoff)

        if nepal_relevance:
            query = query.where(Tweet.nepal_relevance == nepal_relevance)
        if category:
            query = query.where(Tweet.category == category)
        if is_relevant is not None:
            query = query.where(Tweet.is_relevant == is_relevant)
        if source == "accounts":
            query = query.where(
                Tweet.source_query.like("nitter:%"),
                ~Tweet.source_query.like("nitter:#%"),
            )
        elif source == "hashtags":
            query = query.where(Tweet.source_query.like("nitter:#%"))
        if author:
            query = query.where(Tweet.author_username.ilike(author))
        if hashtag:
            query = query.where(Tweet.source_query == f"nitter:#{hashtag}")
        if severity:
            query = query.where(Tweet.severity == severity)
        if ground_reports:
            query = query.where(
                or_(
                    Tweet.districts != [],
                    Tweet.media_urls != [],
                )
            )

        query = query.order_by(desc(Tweet.tweeted_at)).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_in_period(
        self,
        hours: int = 24,
        nepal_relevance: Optional[str] = None,
        category: Optional[str] = None,
        is_relevant: Optional[bool] = None,
        source: Optional[str] = None,
        author: Optional[str] = None,
        hashtag: Optional[str] = None,
        severity: Optional[str] = None,
        ground_reports: bool = False,
    ) -> int:
        """Count total tweets matching filters in time period (ignoring limit)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = select(func.count(Tweet.id)).where(Tweet.fetched_at >= cutoff)

        if nepal_relevance:
            query = query.where(Tweet.nepal_relevance == nepal_relevance)
        if category:
            query = query.where(Tweet.category == category)
        if is_relevant is not None:
            query = query.where(Tweet.is_relevant == is_relevant)
        if source == "accounts":
            query = query.where(
                Tweet.source_query.like("nitter:%"),
                ~Tweet.source_query.like("nitter:#%"),
            )
        elif source == "hashtags":
            query = query.where(Tweet.source_query.like("nitter:#%"))
        if author:
            query = query.where(Tweet.author_username.ilike(author))
        if hashtag:
            query = query.where(Tweet.source_query == f"nitter:#{hashtag}")
        if severity:
            query = query.where(Tweet.severity == severity)
        if ground_reports:
            query = query.where(
                or_(
                    Tweet.districts != [],
                    Tweet.media_urls != [],
                )
            )

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_unprocessed_tweets(self, limit: int = 100) -> List[Tweet]:
        """Get tweets that haven't been classified yet."""
        result = await self.db.execute(
            select(Tweet)
            .where(Tweet.is_processed == False)
            .order_by(Tweet.fetched_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_processed(
        self,
        tweet_id: UUID,
        nepal_relevance: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        is_relevant: Optional[bool] = None,
        relevance_score: Optional[float] = None,
    ) -> None:
        """Mark tweet as processed with classification results."""
        await self.db.execute(
            update(Tweet)
            .where(Tweet.id == tweet_id)
            .values(
                is_processed=True,
                processed_at=datetime.now(timezone.utc),
                nepal_relevance=nepal_relevance,
                category=category,
                severity=severity,
                is_relevant=is_relevant,
                relevance_score=relevance_score,
            )
        )
        await self.db.commit()

    async def get_tweet_stats(self, hours: int = 24) -> dict:
        """Get tweet statistics for the last N hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Total count
        total_result = await self.db.execute(
            select(func.count(Tweet.id)).where(Tweet.fetched_at >= cutoff)
        )
        total = total_result.scalar() or 0

        # By relevance
        relevance_result = await self.db.execute(
            select(Tweet.nepal_relevance, func.count(Tweet.id))
            .where(Tweet.fetched_at >= cutoff)
            .group_by(Tweet.nepal_relevance)
        )
        by_relevance = dict(relevance_result.fetchall())

        # By category
        category_result = await self.db.execute(
            select(Tweet.category, func.count(Tweet.id))
            .where(Tweet.fetched_at >= cutoff)
            .where(Tweet.category.isnot(None))
            .group_by(Tweet.category)
        )
        by_category = dict(category_result.fetchall())

        # Unprocessed count
        unprocessed_result = await self.db.execute(
            select(func.count(Tweet.id))
            .where(Tweet.fetched_at >= cutoff)
            .where(Tweet.is_processed == False)
        )
        unprocessed = unprocessed_result.scalar() or 0

        return {
            "total": total,
            "unprocessed": unprocessed,
            "by_relevance": by_relevance,
            "by_category": by_category,
        }

    async def search_tweets(
        self,
        query: str,
        limit: int = 50,
        hours: Optional[int] = None,
    ) -> List[Tweet]:
        """Search tweets by text content."""
        stmt = select(Tweet).options(selectinload(Tweet.cluster)).where(Tweet.text.ilike(f"%{query}%"))

        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            stmt = stmt.where(Tweet.tweeted_at >= cutoff)

        stmt = stmt.order_by(desc(Tweet.tweeted_at)).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_tweets_by_hashtag(
        self, hashtag: str, limit: int = 50
    ) -> List[Tweet]:
        """Get tweets containing a specific hashtag."""
        result = await self.db.execute(
            select(Tweet)
            .where(Tweet.hashtags.contains([hashtag]))
            .order_by(desc(Tweet.tweeted_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_tweets_by_author(
        self, username: str, limit: int = 50
    ) -> List[Tweet]:
        """Get tweets from a specific author."""
        result = await self.db.execute(
            select(Tweet)
            .where(Tweet.author_username == username)
            .order_by(desc(Tweet.tweeted_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    # ==================== Account Operations ====================

    async def upsert_account(
        self,
        twitter_id: str,
        username: str,
        **kwargs,
    ) -> Tuple[TwitterAccount, bool]:
        """Insert or update a Twitter account."""
        existing = await self.get_account_by_username(username)

        if existing:
            for key, value in kwargs.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            await self.db.commit()
            return existing, False

        account = TwitterAccount(
            twitter_id=twitter_id,
            username=username,
            **kwargs,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account, True

    async def get_account_by_username(self, username: str) -> Optional[TwitterAccount]:
        """Get account by username."""
        result = await self.db.execute(
            select(TwitterAccount).where(TwitterAccount.username == username)
        )
        return result.scalar_one_or_none()

    async def get_active_accounts(
        self, priority_max: int = 5
    ) -> List[TwitterAccount]:
        """Get active accounts for monitoring."""
        result = await self.db.execute(
            select(TwitterAccount)
            .where(TwitterAccount.is_active == True)
            .where(TwitterAccount.priority <= priority_max)
            .order_by(TwitterAccount.priority, TwitterAccount.last_fetched_at.nullsfirst())
        )
        return list(result.scalars().all())

    async def update_account_fetch(
        self,
        account_id: UUID,
        last_tweet_id: Optional[str] = None,
    ) -> None:
        """Update account fetch timestamp."""
        values = {"last_fetched_at": datetime.now(timezone.utc)}
        if last_tweet_id:
            values["last_tweet_id"] = last_tweet_id

        await self.db.execute(
            update(TwitterAccount)
            .where(TwitterAccount.id == account_id)
            .values(**values)
        )
        await self.db.commit()

    # ==================== Query Operations ====================

    async def create_query(
        self,
        name: str,
        query: str,
        **kwargs,
    ) -> TwitterQuery:
        """Create a new search query."""
        twitter_query = TwitterQuery(
            name=name,
            query=query,
            **kwargs,
        )
        self.db.add(twitter_query)
        await self.db.commit()
        await self.db.refresh(twitter_query)
        return twitter_query

    async def get_query_by_id(self, query_id: UUID) -> Optional[TwitterQuery]:
        """Get query by ID."""
        result = await self.db.execute(
            select(TwitterQuery).where(TwitterQuery.id == query_id)
        )
        return result.scalar_one_or_none()

    async def get_active_queries(self) -> List[TwitterQuery]:
        """Get all active queries for monitoring."""
        result = await self.db.execute(
            select(TwitterQuery)
            .where(TwitterQuery.is_active == True)
            .order_by(TwitterQuery.priority, TwitterQuery.last_fetched_at.nullsfirst())
        )
        return list(result.scalars().all())

    async def update_query_fetch(
        self,
        query_id: UUID,
        result_count: int,
    ) -> None:
        """Update query fetch stats."""
        query = await self.get_query_by_id(query_id)
        if query:
            query.last_fetched_at = datetime.now(timezone.utc)
            query.last_result_count = result_count
            query.total_results += result_count
            await self.db.commit()

    async def delete_query(self, query_id: UUID) -> bool:
        """Delete a query."""
        query = await self.get_query_by_id(query_id)
        if query:
            await self.db.delete(query)
            await self.db.commit()
            return True
        return False
