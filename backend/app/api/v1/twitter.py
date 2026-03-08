"""Twitter/X API endpoints."""

import logging
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_dev
from app.core.database import get_db
from app.services.twitter_service import TwitterService
from app.services.nitter_service import NitterService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twitter", tags=["Twitter/X"])


# ==================== Schemas ====================

class TweetResponse(BaseModel):
    """Tweet response schema."""
    id: str
    tweet_id: str
    author_id: str
    author_username: Optional[str]
    author_name: Optional[str]
    text: str
    language: str
    is_retweet: bool
    is_reply: bool
    is_quote: bool
    retweet_count: int
    reply_count: int
    like_count: int
    hashtags: List[str]
    mentions: List[str]
    urls: List[str]
    nepal_relevance: Optional[str]
    category: Optional[str]
    severity: Optional[str]
    is_relevant: Optional[bool]
    source_query: Optional[str] = None
    tweet_cluster_id: Optional[str] = None
    cluster_size: Optional[int] = None
    districts: List[str] = []
    provinces: List[str] = []
    media_urls: List[str] = []
    tweeted_at: Optional[str]
    fetched_at: Optional[str]


class TweetListResponse(BaseModel):
    """Response for tweet list endpoints."""
    tweets: List[TweetResponse]
    count: int
    total_in_period: Optional[int] = None


class FetchStatsResponse(BaseModel):
    """Response for fetch operations."""
    query: Optional[str] = None
    fetched: int
    new: int
    updated: int = 0
    errors: List[str] = []


class UsageStatsResponse(BaseModel):
    """Twitter API usage statistics."""
    month: str
    tier: str
    monthly_limit: int
    tweets_read: int
    budget_remaining: int
    api_calls: int
    cached_calls: int
    errors: int
    budget_percentage_used: float
    last_call: Optional[str]


class AccountDailyLimit(BaseModel):
    """Daily limit for a single account."""
    count: int
    limit: int
    remaining: int


class DailyLimitsResponse(BaseModel):
    """Daily per-account limits status."""
    date: str
    organizations: dict  # username -> AccountDailyLimit
    individuals: dict    # username -> AccountDailyLimit


class TweetStatsResponse(BaseModel):
    """Tweet database statistics."""
    total: int
    unprocessed: int
    by_relevance: dict
    by_category: dict


class QueryCreate(BaseModel):
    """Schema for creating a saved query."""
    name: str = Field(..., min_length=1, max_length=200)
    query: str = Field(..., min_length=1)
    description: Optional[str] = None
    priority: int = Field(default=3, ge=1, le=5)
    max_results: int = Field(default=10, ge=1, le=100)
    poll_interval_mins: int = Field(default=60, ge=5, le=1440)
    category: Optional[str] = None


class QueryResponse(BaseModel):
    """Saved query response."""
    id: str
    name: str
    query: str
    description: Optional[str]
    is_active: bool
    priority: int
    max_results: int
    poll_interval_mins: int
    category: Optional[str]
    last_fetched_at: Optional[str]
    total_results: int


class AccountCreate(BaseModel):
    """Schema for adding a monitored account."""
    username: str = Field(..., min_length=1, max_length=100)
    twitter_id: Optional[str] = None
    name: Optional[str] = None
    priority: int = Field(default=3, ge=1, le=5)
    category: Optional[str] = None


class AccountResponse(BaseModel):
    """Monitored account response."""
    id: str
    twitter_id: str
    username: str
    name: Optional[str]
    verified: bool
    followers_count: int
    is_active: bool
    priority: int
    category: Optional[str]
    last_fetched_at: Optional[str]
    tweet_count: int


# ==================== Endpoints ====================


@router.get("/export")
async def export_tweets_for_agent(
    hours: int = Query(6, ge=1, le=48, description="Time window in hours"),
    limit: int = Query(500, ge=1, le=1000, description="Max tweets"),
    db: AsyncSession = Depends(get_db),
):
    """Export recent tweets for the local province anomaly agent.

    Returns tweets with text, author, timestamps — everything
    needed for province keyword classification without direct DB access.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, desc
    from app.models.tweet import Tweet

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(Tweet)
        .where(Tweet.tweeted_at >= since)
        .order_by(desc(Tweet.tweeted_at))
        .limit(limit)
    )
    tweets = result.scalars().all()

    items = []
    for t in tweets:
        items.append({
            "id": str(t.id),
            "text": t.text,
            "author_username": t.author_username,
            "author_name": t.author_name,
            "tweeted_at": t.tweeted_at.isoformat() if t.tweeted_at else None,
            "nepal_relevance": t.nepal_relevance,
            "category": t.category,
            "severity": t.severity,
        })

    return {"tweets": items, "total": len(items), "since": since.isoformat()}


@router.get("/status")
async def get_twitter_status(
    db: AsyncSession = Depends(get_db),
):
    """
    Get Twitter integration status.

    Returns whether Twitter API is configured and ready.
    """
    service = TwitterService(db)
    return {
        "configured": service.is_configured,
        "message": "Twitter API is configured" if service.is_configured else "Twitter API not configured - set TWITTER_BEARER_TOKEN",
    }


@router.get("/usage", response_model=UsageStatsResponse)
async def get_usage_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Get Twitter API usage statistics.

    Shows monthly budget consumption and rate limits.
    """
    service = TwitterService(db)
    stats = await service.get_usage_stats()
    return UsageStatsResponse(**stats)


@router.get("/daily-limits", response_model=DailyLimitsResponse)
async def get_daily_limits(
    db: AsyncSession = Depends(get_db),
):
    """
    Get daily per-account tweet limits.

    Shows how many tweets have been fetched from each account today
    and remaining capacity.

    Limits:
    - Organizations (ECNOfficial, NepaliArmyHQ, BIPADPortal): 5 tweets/day
    - Individuals (thapagk, hamrorabi): 2 tweets/day
    """
    from app.ingestion.twitter_fetcher import TwitterFetcher

    async with TwitterFetcher() as fetcher:
        status = fetcher.get_daily_limits_status()
        return DailyLimitsResponse(**status)


@router.get("/stats", response_model=TweetStatsResponse)
async def get_tweet_stats(
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """
    Get tweet statistics from database.

    Returns counts by relevance and category.
    """
    service = TwitterService(db)
    stats = await service.get_tweet_stats(hours=hours)
    return TweetStatsResponse(**stats)


@router.get("/tweets", response_model=TweetListResponse)
async def get_tweets(
    limit: int = Query(default=50, ge=1, le=500),
    hours: int = Query(default=24, ge=1, le=168),
    nepal_relevance: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    relevant_only: bool = Query(default=False),
    source: Optional[str] = Query(default=None, pattern="^(accounts|hashtags)$"),
    author: Optional[str] = Query(default=None),
    hashtag: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None, pattern="^(critical|high|medium|low)$"),
    ground_reports: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """
    Get recent tweets from database.

    Supports filtering by relevance, category, severity, time range, source type, author, or hashtag.
    Use ground_reports=true to show only tweets with verified locations or visual evidence.
    """
    service = TwitterService(db)
    filter_kwargs = dict(
        hours=hours,
        nepal_relevance=nepal_relevance,
        category=category,
        relevant_only=relevant_only,
        source=source,
        author=author,
        hashtag=hashtag,
        severity=severity,
        ground_reports=ground_reports,
    )
    tweets = await service.get_recent_tweets(limit=limit, **filter_kwargs)
    total = await service.count_tweets_in_period(**filter_kwargs)

    return TweetListResponse(
        tweets=[TweetResponse(**t.to_dict()) for t in tweets],
        count=len(tweets),
        total_in_period=total,
    )


@router.get("/search", response_model=TweetListResponse)
async def search_tweets(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=50, ge=1, le=500),
    hours: Optional[int] = Query(default=None, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """
    Search stored tweets by text content.
    """
    service = TwitterService(db)
    tweets = await service.search_tweets(query=q, limit=limit, hours=hours)

    return TweetListResponse(
        tweets=[TweetResponse(**t.to_dict()) for t in tweets],
        count=len(tweets),
    )


@router.post("/fetch", response_model=FetchStatsResponse, dependencies=[Depends(require_dev)])
async def fetch_tweets(
    query: str = Query(..., min_length=1, description="X API search query"),
    max_results: int = Query(default=10, ge=1, le=100),
    classify: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch tweets from X API for a custom query.

    This uses your API budget. Check /usage before fetching.
    """
    service = TwitterService(db)

    if not service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Twitter API not configured - set TWITTER_BEARER_TOKEN",
        )

    result = await service.fetch_and_store_tweets(
        query=query,
        max_results=max_results,
        classify=classify,
    )

    return FetchStatsResponse(**result)


@router.post("/fetch-nepal", response_model=FetchStatsResponse, dependencies=[Depends(require_dev)])
async def fetch_nepal_news(
    max_per_query: int = Query(default=10, ge=1, le=50),
    classify: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch Nepal-related tweets using predefined queries.

    Runs multiple Nepal-focused queries to get relevant news.
    """
    service = TwitterService(db)

    if not service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Twitter API not configured - set TWITTER_BEARER_TOKEN",
        )

    result = await service.fetch_nepal_news(
        max_per_query=max_per_query,
        classify=classify,
    )

    return FetchStatsResponse(
        fetched=result.get("total_fetched", 0),
        new=result.get("total_new", 0),
        errors=result.get("errors", []),
    )


@router.post("/run-queries", response_model=FetchStatsResponse, dependencies=[Depends(require_dev)])
async def run_saved_queries(
    classify: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    """
    Run all active saved queries.

    Executes saved queries and stores results.
    """
    service = TwitterService(db)

    if not service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Twitter API not configured - set TWITTER_BEARER_TOKEN",
        )

    result = await service.run_saved_queries(classify=classify)

    return FetchStatsResponse(
        fetched=result.get("total_fetched", 0),
        new=result.get("total_new", 0),
        errors=result.get("errors", []),
    )


@router.post("/process-unclassified", dependencies=[Depends(require_dev)])
async def process_unclassified_tweets(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    Process tweets that haven't been classified yet.

    Runs Nepal relevance classification on unprocessed tweets.
    """
    service = TwitterService(db)
    processed = await service.process_unclassified_tweets(limit=limit)

    return {"processed": processed}


# ==================== Query Management ====================

@router.get("/queries", response_model=List[QueryResponse])
async def get_queries(
    db: AsyncSession = Depends(get_db),
):
    """Get all active saved queries."""
    service = TwitterService(db)
    queries = await service.get_queries()
    return [QueryResponse(**q.to_dict()) for q in queries]


@router.post("/queries", response_model=QueryResponse, dependencies=[Depends(require_dev)])
async def create_query(
    data: QueryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new saved query for periodic monitoring."""
    service = TwitterService(db)
    query = await service.create_query(
        name=data.name,
        query=data.query,
        description=data.description,
        priority=data.priority,
        max_results=data.max_results,
        poll_interval_mins=data.poll_interval_mins,
        category=data.category,
    )
    return QueryResponse(**query.to_dict())


@router.delete("/queries/{query_id}", dependencies=[Depends(require_dev)])
async def delete_query(
    query_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a saved query."""
    service = TwitterService(db)
    success = await service.delete_query(query_id)

    if not success:
        raise HTTPException(status_code=404, detail="Query not found")

    return {"status": "ok", "message": "Query deleted"}


# ==================== Account Management ====================

@router.get("/accounts", response_model=List[AccountResponse])
async def get_accounts(
    db: AsyncSession = Depends(get_db),
):
    """Get all monitored accounts."""
    service = TwitterService(db)
    accounts = await service.get_accounts()
    return [AccountResponse(**a.to_dict()) for a in accounts]


@router.post("/accounts", response_model=AccountResponse, dependencies=[Depends(require_dev)])
async def add_account(
    data: AccountCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add an account to monitor."""
    service = TwitterService(db)
    account = await service.add_account(
        username=data.username,
        twitter_id=data.twitter_id,
        name=data.name,
        priority=data.priority,
        category=data.category,
    )
    return AccountResponse(**account.to_dict())


# ==================== Nitter Scraping ====================

@router.get("/nitter/status")
async def get_nitter_status(
    db: AsyncSession = Depends(get_db),
):
    """
    Get Nitter scraping instance health status.

    Shows which Nitter instances are healthy, in backoff, or failing.
    No authentication required.
    """
    service = NitterService(db)
    return {
        "instances": service.get_instance_status(),
    }


@router.post("/nitter/scrape-accounts", dependencies=[Depends(require_dev)])
async def scrape_nitter_accounts(
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger Nitter account timeline scraping.

    Scrapes all configured verified accounts via Nitter.
    """
    service = NitterService(db)
    result = await service.scrape_all_accounts()
    return result


@router.post("/nitter/scrape-hashtags", dependencies=[Depends(require_dev)])
async def scrape_nitter_hashtags(
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger Nitter hashtag search scraping.

    Scrapes all configured hashtags via Nitter.
    """
    service = NitterService(db)
    result = await service.scrape_all_hashtags()
    return result


@router.post("/nitter/scrape-searches", dependencies=[Depends(require_dev)])
async def scrape_nitter_searches(
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger Nitter text search scraping.

    Scrapes all configured text search queries via Nitter.
    """
    service = NitterService(db)
    result = await service.scrape_all_searches()
    return result


# ==================== Ingest (local scraper → API) ====================

class IngestTweet(BaseModel):
    """Single tweet for ingestion."""
    tweet_id: str
    author_username: str
    author_name: Optional[str] = None
    text: str
    language: str = "en"
    tweeted_at: Optional[str] = None
    is_retweet: bool = False
    is_reply: bool = False
    is_quote: bool = False
    retweet_count: int = 0
    reply_count: int = 0
    like_count: int = 0
    quote_count: int = 0
    hashtags: List[str] = []
    mentions: List[str] = []
    urls: List[str] = []
    media_urls: List[str] = []
    source_query: Optional[str] = None


class IngestRequest(BaseModel):
    """Batch tweet ingestion request."""
    tweets: List[IngestTweet]


class IngestResponse(BaseModel):
    """Ingestion result."""
    received: int
    created: int
    skipped: int
    classified: int
    errors: int


@router.post("/ingest", response_model=IngestResponse, dependencies=[Depends(require_dev)])
async def ingest_tweets(
    payload: IngestRequest,
    classify: bool = Query(True, description="Run relevance classification"),
    broadcast: bool = Query(True, description="Broadcast new tweets via WebSocket"),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest pre-scraped tweets via API.

    Used by local nitter scraper to post tweets without direct DB access.
    Performs upsert, classification, dedup, and WebSocket broadcast.
    """
    from app.repositories.twitter import TwitterRepository
    from app.services.tweet_dedup_service import TweetDedupService
    from app.core.realtime_bus import publish_news

    repo = TwitterRepository(db)
    # RelevanceService excluded from skeleton
    created = 0
    skipped = 0
    classified = 0
    errors = 0

    for t in payload.tweets:
        try:
            tweeted_at = None
            if t.tweeted_at:
                try:
                    tweeted_at = datetime.fromisoformat(t.tweeted_at.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            db_tweet, is_new = await repo.upsert_tweet(
                tweet_id=t.tweet_id,
                author_id=t.author_username,
                text=t.text,
                author_username=t.author_username,
                author_name=t.author_name,
                language=t.language,
                is_retweet=t.is_retweet,
                is_reply=t.is_reply,
                is_quote=t.is_quote,
                retweet_count=t.retweet_count,
                reply_count=t.reply_count,
                like_count=t.like_count,
                quote_count=t.quote_count,
                hashtags=t.hashtags,
                mentions=t.mentions,
                urls=t.urls,
                media_urls=t.media_urls,
                tweeted_at=tweeted_at,
                fetched_at=datetime.now(timezone.utc),
                source_query=t.source_query,
            )

            if not is_new:
                skipped += 1
                continue

            created += 1

            # Classify (stub - RelevanceService excluded)
            if classify:
                try:
                    nepal_relevance = "RELEVANT"
                    is_relevant = True
                    cat = None

                    await repo.mark_processed(
                        tweet_id=db_tweet.id,
                        nepal_relevance=nepal_relevance,
                        category=cat,
                        is_relevant=is_relevant,
                        relevance_score=0.5,
                    )
                    classified += 1

                    if broadcast and is_relevant:
                        await publish_news({
                            "type": "new_tweet",
                            "source": "ingest",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "data": {
                                "tweet_id": t.tweet_id,
                                "author": t.author_username,
                                "text": t.text[:280],
                                "category": cat,
                                "relevance": nepal_relevance,
                            },
                        })
                except Exception as e:
                    logger.warning(f"Classification failed for {t.tweet_id}: {e}")

            # Dedup
            try:
                dedup = TweetDedupService(db)
                await dedup.on_ingest(db_tweet)
            except Exception as e:
                logger.warning(f"Dedup failed for {t.tweet_id}: {e}")

        except Exception as e:
            logger.warning(f"Ingest failed for {t.tweet_id}: {e}")
            errors += 1

    logger.info(f"Ingest complete: {created} created, {skipped} skipped, {classified} classified, {errors} errors")

    return IngestResponse(
        received=len(payload.tweets),
        created=created,
        skipped=skipped,
        classified=classified,
        errors=errors,
    )
