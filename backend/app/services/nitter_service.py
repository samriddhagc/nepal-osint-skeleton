"""Nitter scraping service — orchestrates scraper → repository → classifier → WebSocket."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.nitter_scraper import (
    NitterInstanceManager,
    NitterScraper,
    ScrapedTweet,
)
from app.repositories.twitter import TwitterRepository
# RelevanceService excluded from skeleton
RelevanceService = None
from app.services.tweet_dedup_service import TweetDedupService
from app.core.realtime_bus import publish_news

logger = logging.getLogger(__name__)

# Load sources config once at module level
_SOURCES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml"


def _load_nitter_config() -> dict:
    """Load nitter config sections from sources.yaml."""
    try:
        with open(_SOURCES_PATH) as f:
            cfg = yaml.safe_load(f)
        return {
            "nitter_config": cfg.get("nitter_config", {}),
            "nitter_accounts": cfg.get("nitter_accounts", []),
            "nitter_hashtags": cfg.get("nitter_hashtags", []),
            "nitter_searches": cfg.get("nitter_searches", []),
        }
    except Exception as e:
        logger.error(f"Failed to load nitter config: {e}")
        return {"nitter_config": {}, "nitter_accounts": [], "nitter_hashtags": [], "nitter_searches": []}


class NitterService:
    """Orchestrates Nitter scraping, storage, classification, and broadcasting."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TwitterRepository(db)
        self.relevance_service = None  # RelevanceService excluded

        config = _load_nitter_config()
        self._nitter_config = config["nitter_config"]
        self._accounts = config["nitter_accounts"]
        self._hashtags = config["nitter_hashtags"]
        self._searches = config["nitter_searches"]

        instances = self._nitter_config.get("instances", [])
        if not instances:
            instances = [{"url": "https://nitter.poast.org", "priority": 1}]

        self._instance_manager = NitterInstanceManager(instances)

    def _create_scraper(self) -> NitterScraper:
        """Create a configured NitterScraper instance."""
        return NitterScraper(
            instance_manager=self._instance_manager,
            request_timeout=self._nitter_config.get("request_timeout", 30),
            delay_between_requests=self._nitter_config.get("delay_between_requests", 2.0),
        )

    async def scrape_all_accounts(self) -> dict:
        """Scrape all configured Nitter accounts.

        Returns:
            Stats dict with accounts_scraped, tweets_fetched, new_tweets, errors.
        """
        if not self._accounts:
            logger.debug("No nitter accounts configured, skipping")
            return {"accounts_scraped": 0, "tweets_fetched": 0, "new_tweets": 0, "errors": []}

        stats = {
            "accounts_scraped": 0,
            "tweets_fetched": 0,
            "new_tweets": 0,
            "errors": [],
        }

        async with self._create_scraper() as scraper:
            for account in self._accounts:
                username = account["username"]
                category = account.get("category", "news")

                try:
                    result = await scraper.scrape_user_timeline(username)

                    if not result.success:
                        stats["errors"].append(f"@{username}: {result.error}")
                        continue

                    stats["accounts_scraped"] += 1
                    stats["tweets_fetched"] += len(result.tweets)

                    new_count = await self._store_and_classify(
                        result.tweets,
                        source_query=f"nitter:{username}",
                        category=category,
                    )
                    stats["new_tweets"] += new_count

                    # Polite delay between accounts
                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception(f"Error scraping @{username}: {e}")
                    stats["errors"].append(f"@{username}: {e}")

        return stats

    async def scrape_all_hashtags(self) -> dict:
        """Scrape all configured Nitter hashtags.

        Returns:
            Stats dict with hashtags_scraped, tweets_fetched, new_tweets, errors.
        """
        if not self._hashtags:
            logger.debug("No nitter hashtags configured, skipping")
            return {"hashtags_scraped": 0, "tweets_fetched": 0, "new_tweets": 0, "errors": []}

        stats = {
            "hashtags_scraped": 0,
            "tweets_fetched": 0,
            "new_tweets": 0,
            "errors": [],
        }

        async with self._create_scraper() as scraper:
            for hashtag_cfg in self._hashtags:
                tag = hashtag_cfg["tag"]
                category = hashtag_cfg.get("category", "political")

                try:
                    result = await scraper.scrape_hashtag_search(tag)

                    if not result.success:
                        stats["errors"].append(f"#{tag}: {result.error}")
                        continue

                    stats["hashtags_scraped"] += 1
                    stats["tweets_fetched"] += len(result.tweets)

                    new_count = await self._store_and_classify(
                        result.tweets,
                        source_query=f"nitter:#{tag}",
                        category=category,
                    )
                    stats["new_tweets"] += new_count

                    # Polite delay between hashtags
                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception(f"Error scraping #{tag}: {e}")
                    stats["errors"].append(f"#{tag}: {e}")

        return stats

    async def scrape_all_searches(self) -> dict:
        """Scrape all configured Nitter text search queries.

        Returns:
            Stats dict with searches_scraped, tweets_fetched, new_tweets, errors.
        """
        if not self._searches:
            logger.debug("No nitter text searches configured, skipping")
            return {"searches_scraped": 0, "tweets_fetched": 0, "new_tweets": 0, "errors": []}

        stats = {
            "searches_scraped": 0,
            "tweets_fetched": 0,
            "new_tweets": 0,
            "errors": [],
        }

        async with self._create_scraper() as scraper:
            for search_cfg in self._searches:
                query = search_cfg["query"]
                category = search_cfg.get("category", "political")

                try:
                    result = await scraper.scrape_text_search(query)

                    if not result.success:
                        stats["errors"].append(f"search '{query}': {result.error}")
                        continue

                    stats["searches_scraped"] += 1
                    stats["tweets_fetched"] += len(result.tweets)

                    new_count = await self._store_and_classify(
                        result.tweets,
                        source_query=f"nitter:search:{query}",
                        category=category,
                    )
                    stats["new_tweets"] += new_count

                    # Polite delay between searches
                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception(f"Error searching '{query}': {e}")
                    stats["errors"].append(f"search '{query}': {e}")

        return stats

    async def _store_and_classify(
        self,
        tweets: List[ScrapedTweet],
        source_query: str,
        category: str,
    ) -> int:
        """Store tweets and run relevance classification.

        Returns:
            Number of newly inserted tweets.
        """
        new_count = 0

        for scraped in tweets:
            try:
                # 1. Upsert into tweets table (dedup by tweet_id)
                db_tweet, created = await self.repo.upsert_tweet(
                    tweet_id=scraped.tweet_id,
                    author_id=scraped.author_username,  # Nitter doesn't give numeric IDs
                    text=scraped.text,
                    author_username=scraped.author_username,
                    author_name=scraped.author_name,
                    language=scraped.language,
                    is_retweet=scraped.is_retweet,
                    is_reply=scraped.is_reply,
                    is_quote=scraped.is_quote,
                    retweet_count=scraped.retweet_count,
                    reply_count=scraped.reply_count,
                    like_count=scraped.like_count,
                    quote_count=scraped.quote_count,
                    hashtags=scraped.hashtags,
                    mentions=scraped.mentions,
                    urls=scraped.urls,
                    media_urls=scraped.media_urls,
                    tweeted_at=scraped.tweeted_at,
                    fetched_at=datetime.now(timezone.utc),
                    source_query=source_query,
                )

                if not created:
                    continue

                new_count += 1

                # 2. Classify relevance (stub — RelevanceService excluded)
                try:
                    nepal_relevance = "RELEVANT"
                    relevance_score = 0.5
                    is_relevant = True
                    classified_category = category

                    # 3. Mark as processed
                    await self.repo.mark_processed(
                        tweet_id=db_tweet.id,
                        nepal_relevance=nepal_relevance,
                        category=classified_category,
                        is_relevant=is_relevant,
                        relevance_score=relevance_score,
                    )

                    # 4. Broadcast via WebSocket
                    if is_relevant:
                        await publish_news(
                            {
                                "type": "new_tweet",
                                "source": "nitter",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "data": {
                                    "tweet_id": scraped.tweet_id,
                                    "author": scraped.author_username,
                                    "text": scraped.text[:280],
                                    "category": classified_category,
                                    "relevance": nepal_relevance,
                                },
                            }
                        )

                except Exception as e:
                    logger.warning(
                        f"Classification failed for tweet {scraped.tweet_id}: {e}"
                    )

                # 5. Run dedup on_ingest (content hash + keyword location)
                try:
                    dedup_service = TweetDedupService(self.db)
                    await dedup_service.on_ingest(db_tweet)
                except Exception as e:
                    logger.warning(f"Dedup on_ingest failed for tweet {scraped.tweet_id}: {e}")

            except Exception as e:
                logger.warning(f"Failed to store tweet {scraped.tweet_id}: {e}")

        return new_count

    def get_instance_status(self) -> List[dict]:
        """Get health status of all Nitter instances."""
        return self._instance_manager.get_status()
