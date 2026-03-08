"""
Twitter Ingestion Service

Orchestrates Twitter/X data fetching, processing, and storage with:
- Budget-aware API usage
- Nepal relevance classification
- Integration with existing story pipeline
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.twitter_fetcher import TwitterFetcher, Tweet as FetchedTweet, TwitterFetchResult
from app.models.tweet import Tweet, TwitterAccount, TwitterQuery
from app.repositories.twitter import TwitterRepository
# RelevanceService excluded from skeleton
RelevanceService = None
from app.services.tweet_dedup_service import TweetDedupService

logger = logging.getLogger(__name__)


class TwitterService:
    """
    Service for Twitter/X data ingestion and processing.

    Handles:
    - Fetching tweets from X API
    - Storing in database
    - Classification for Nepal relevance
    - Budget tracking
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TwitterRepository(db)
        self._fetcher: Optional[TwitterFetcher] = None

    async def _get_fetcher(self) -> TwitterFetcher:
        """Get or create Twitter fetcher."""
        if self._fetcher is None:
            self._fetcher = TwitterFetcher()
        return self._fetcher

    @property
    def is_configured(self) -> bool:
        """Check if Twitter API is configured."""
        from app.config import get_settings
        settings = get_settings()
        return bool(settings.twitter_bearer_token)

    async def fetch_and_store_tweets(
        self,
        query: str,
        max_results: int = 10,
        classify: bool = True,
    ) -> Dict[str, Any]:
        """
        Fetch tweets for a query and store in database.

        Args:
            query: X API search query
            max_results: Maximum tweets to fetch
            classify: Whether to run Nepal relevance classification

        Returns:
            Stats dict with counts
        """
        stats = {
            "query": query,
            "fetched": 0,
            "new": 0,
            "updated": 0,
            "errors": [],
        }

        async with TwitterFetcher() as fetcher:
            if not fetcher.is_configured:
                stats["errors"].append("Twitter API not configured")
                return stats

            result = await fetcher.search_tweets(query, max_results=max_results)

            if not result.success:
                stats["errors"].append(result.error or "Unknown error")
                return stats

            stats["fetched"] = len(result.tweets)

            # Store tweets
            for tweet in result.tweets:
                try:
                    db_tweet, created = await self._store_tweet(tweet, query)

                    if created:
                        stats["new"] += 1

                        # Classify new tweets
                        if classify:
                            await self._classify_tweet(db_tweet)

                        # Run dedup on_ingest
                        await self._run_dedup(db_tweet)
                    else:
                        stats["updated"] += 1

                except Exception as e:
                    logger.error(f"Error storing tweet {tweet.id}: {e}")
                    stats["errors"].append(f"Tweet {tweet.id}: {str(e)}")

        logger.info(
            f"Twitter fetch complete for '{query[:30]}...': "
            f"{stats['fetched']} fetched, {stats['new']} new"
        )

        return stats

    async def _store_tweet(
        self,
        tweet: FetchedTweet,
        source_query: str,
    ) -> tuple[Tweet, bool]:
        """Store a fetched tweet in the database."""
        # Get importance score if available (from free tier filtering)
        importance_score = getattr(tweet, 'importance_score', None)

        return await self.repo.upsert_tweet(
            tweet_id=tweet.id,
            author_id=tweet.author_id,
            text=tweet.text,
            author_username=tweet.author_username,
            author_name=tweet.author_name,
            language=tweet.language,
            is_retweet=tweet.is_retweet,
            is_reply=tweet.is_reply,
            is_quote=tweet.is_quote,
            retweet_count=tweet.retweet_count,
            reply_count=tweet.reply_count,
            like_count=tweet.like_count,
            quote_count=tweet.quote_count,
            impression_count=tweet.impression_count,
            hashtags=tweet.hashtags,
            mentions=tweet.mentions,
            urls=tweet.urls,
            geo=tweet.geo,
            conversation_id=tweet.conversation_id,
            in_reply_to_user_id=tweet.in_reply_to_user_id,
            source_query=source_query,
            tweeted_at=tweet.created_at,
            fetched_at=datetime.now(timezone.utc),
            relevance_score=importance_score,  # Store importance as relevance score
        )

    async def _classify_tweet(self, tweet: Tweet) -> None:
        """Classify tweet for Nepal relevance (stub - RelevanceService excluded)."""
        try:
            # Stub: mark all tweets as relevant
            await self.repo.mark_processed(
                tweet_id=tweet.id,
                nepal_relevance="RELEVANT",
                is_relevant=True,
                relevance_score=0.5,
            )
        except Exception as e:
            logger.error(f"Error classifying tweet {tweet.id}: {e}")
            await self.repo.mark_processed(tweet_id=tweet.id)

    async def _run_dedup(self, tweet: Tweet) -> None:
        """Run dedup on_ingest for content hash + keyword location extraction."""
        try:
            dedup_service = TweetDedupService(self.db)
            await dedup_service.on_ingest(tweet)
        except Exception as e:
            logger.warning(f"Dedup on_ingest failed for tweet {tweet.id}: {e}")

    async def fetch_nepal_news(
        self,
        max_per_query: int = 10,
        classify: bool = True,
    ) -> Dict[str, Any]:
        """
        Fetch Nepal-related news using tier-appropriate strategy.

        FREE TIER: Single query for @ECNOfficial, @NepaliArmyHQ, @BIPADPortal
        BASIC/PRO: Multiple queries for broader coverage

        Returns aggregated stats.
        """
        stats = {
            "total_fetched": 0,
            "total_new": 0,
            "queries_run": 0,
            "errors": [],
            "tier": "unknown",
            "budget_remaining": 0,
        }

        async with TwitterFetcher() as fetcher:
            if not fetcher.is_configured:
                stats["errors"].append("Twitter API not configured")
                return stats

            stats["tier"] = fetcher.tier
            stats["budget_remaining"] = fetcher.budget_remaining

            result = await fetcher.fetch_nepal_news(max_per_query=max_per_query)

            if not result.success:
                stats["errors"].append(result.error or "Unknown error")
                return stats

            stats["total_fetched"] = len(result.tweets)

            # Extract meta information
            if result.meta:
                stats["queries_run"] = result.meta.get("queries_used", 1)
                stats["budget_remaining"] = result.meta.get("budget_remaining", fetcher.budget_remaining)
                stats["passed_filter"] = result.meta.get("passed_filter", len(result.tweets))

            # Store tweets
            for tweet in result.tweets:
                try:
                    db_tweet, created = await self._store_tweet(tweet, tweet.source_query or "nepal_news")

                    if created:
                        stats["total_new"] += 1
                        if classify:
                            await self._classify_tweet(db_tweet)
                        await self._run_dedup(db_tweet)

                except Exception as e:
                    logger.error(f"Error storing tweet {tweet.id}: {e}")

            logger.info(
                f"Twitter fetch [{fetcher.tier}]: {stats['total_fetched']} fetched, "
                f"{stats['total_new']} new, budget: {stats['budget_remaining']}"
            )

        return stats

    async def run_saved_queries(self, classify: bool = True) -> Dict[str, Any]:
        """
        Run all active saved queries.

        Returns aggregated stats.
        """
        stats = {
            "queries_run": 0,
            "total_fetched": 0,
            "total_new": 0,
            "errors": [],
        }

        queries = await self.repo.get_active_queries()

        for query in queries:
            try:
                result = await self.fetch_and_store_tweets(
                    query=query.query,
                    max_results=query.max_results,
                    classify=classify,
                )

                stats["queries_run"] += 1
                stats["total_fetched"] += result["fetched"]
                stats["total_new"] += result["new"]
                stats["errors"].extend(result["errors"])

                # Update query stats
                await self.repo.update_query_fetch(
                    query_id=query.id,
                    result_count=result["new"],
                )

            except Exception as e:
                logger.error(f"Error running query {query.name}: {e}")
                stats["errors"].append(f"Query '{query.name}': {str(e)}")

        return stats

    async def process_unclassified_tweets(self, limit: int = 100) -> int:
        """
        Process tweets that haven't been classified yet.

        Returns count of processed tweets.
        """
        tweets = await self.repo.get_unprocessed_tweets(limit=limit)
        processed = 0

        for tweet in tweets:
            try:
                await self._classify_tweet(tweet)
                processed += 1
            except Exception as e:
                logger.error(f"Error classifying tweet {tweet.id}: {e}")

        return processed

    async def get_usage_stats(self) -> Dict[str, Any]:
        """Get Twitter API usage statistics."""
        async with TwitterFetcher() as fetcher:
            return fetcher.get_usage_stats()

    async def get_tweet_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get tweet statistics from database."""
        return await self.repo.get_tweet_stats(hours=hours)

    async def get_recent_tweets(
        self,
        limit: int = 50,
        hours: int = 24,
        nepal_relevance: Optional[str] = None,
        category: Optional[str] = None,
        relevant_only: bool = False,
        source: Optional[str] = None,
        author: Optional[str] = None,
        hashtag: Optional[str] = None,
        severity: Optional[str] = None,
        ground_reports: bool = False,
    ) -> List[Tweet]:
        """Get recent tweets with filters."""
        return await self.repo.get_recent_tweets(
            limit=limit,
            hours=hours,
            nepal_relevance=nepal_relevance,
            category=category,
            is_relevant=True if relevant_only else None,
            source=source,
            author=author,
            hashtag=hashtag,
            severity=severity,
            ground_reports=ground_reports,
        )

    async def count_tweets_in_period(
        self,
        hours: int = 24,
        nepal_relevance: Optional[str] = None,
        category: Optional[str] = None,
        relevant_only: bool = False,
        source: Optional[str] = None,
        author: Optional[str] = None,
        hashtag: Optional[str] = None,
        severity: Optional[str] = None,
        ground_reports: bool = False,
    ) -> int:
        """Count total tweets in period matching filters."""
        return await self.repo.count_in_period(
            hours=hours,
            nepal_relevance=nepal_relevance,
            category=category,
            is_relevant=True if relevant_only else None,
            source=source,
            author=author,
            hashtag=hashtag,
            severity=severity,
            ground_reports=ground_reports,
        )

    async def search_tweets(
        self,
        query: str,
        limit: int = 50,
        hours: Optional[int] = None,
    ) -> List[Tweet]:
        """Search stored tweets."""
        return await self.repo.search_tweets(query, limit=limit, hours=hours)

    # ==================== Query Management ====================

    async def create_query(
        self,
        name: str,
        query: str,
        description: Optional[str] = None,
        priority: int = 3,
        max_results: int = 10,
        poll_interval_mins: int = 60,
        category: Optional[str] = None,
    ) -> TwitterQuery:
        """Create a new saved query."""
        return await self.repo.create_query(
            name=name,
            query=query,
            description=description,
            priority=priority,
            max_results=max_results,
            poll_interval_mins=poll_interval_mins,
            category=category,
        )

    async def get_queries(self) -> List[TwitterQuery]:
        """Get all active queries."""
        return await self.repo.get_active_queries()

    async def delete_query(self, query_id) -> bool:
        """Delete a query."""
        return await self.repo.delete_query(query_id)

    # ==================== Account Management ====================

    async def add_account(
        self,
        username: str,
        twitter_id: Optional[str] = None,
        name: Optional[str] = None,
        priority: int = 3,
        category: Optional[str] = None,
    ) -> TwitterAccount:
        """Add an account to monitor."""
        account, _ = await self.repo.upsert_account(
            twitter_id=twitter_id or username,  # Use username as ID if not provided
            username=username,
            name=name,
            priority=priority,
            category=category,
        )
        return account

    async def get_accounts(self) -> List[TwitterAccount]:
        """Get all active accounts."""
        return await self.repo.get_active_accounts()
