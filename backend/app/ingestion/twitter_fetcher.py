"""
X/Twitter API Fetcher - FREE TIER OPTIMIZED

Fetches tweets from X (Twitter) API v2 with:
- Aggressive budget management for free tier (100 tweets/month)
- Focus on PRIORITY ACCOUNTS (official Nepal government/news)
- Importance filtering to only fetch critical announcements
- Long cache TTL (6 hours) to minimize API calls

API Tiers:
- Free: 100 tweets/month read, 1 app environment
- Basic ($100/mo): 10,000 tweets/month read
- Pro ($5000/mo): 1M tweets/month read

FREE TIER STRATEGY:
- Poll every 12 hours (not hourly)
- Single combined query for all priority accounts
- Only fetch tweets with importance keywords
- ~3 tweets/day budget = ~90 tweets/month (leaves buffer)
"""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

import aiohttp

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# =============================================================================
# PRIORITY ACCOUNTS - High-value official sources
# =============================================================================

# Organizations (5 tweets/day limit)
ORGANIZATION_ACCOUNTS = {
    "ECNOfficial": "Election Commission Nepal",
    "NepaliArmyHQ": "Nepal Army HQ",
    "BIPADPortal": "BIPAD Disaster Portal",
}

# Individuals (2 tweets/day limit)
INDIVIDUAL_ACCOUNTS = {
    "thapagk": "GK Thapa (Journalist)",
    "hamrorabi": "Hamro Rabi",
}

# Combined list for importance scoring
PRIORITY_ACCOUNTS = list(ORGANIZATION_ACCOUNTS.keys()) + list(INDIVIDUAL_ACCOUNTS.keys())

# Daily limits per account type
DAILY_LIMIT_ORGANIZATION = 5
DAILY_LIMIT_INDIVIDUAL = 2

# =============================================================================
# IMPORTANCE KEYWORDS - Only fetch tweets containing these
# =============================================================================
IMPORTANCE_KEYWORDS_EN = [
    "breaking", "urgent", "alert", "emergency", "announcement",
    "official", "notice", "warning", "declared", "imposed",
    "election", "vote", "polling", "result", "candidate",
    "earthquake", "flood", "landslide", "disaster", "rescue",
    "curfew", "prohibitory", "bandh", "strike", "protest",
    "army", "security", "deployed", "operation",
]

IMPORTANCE_KEYWORDS_NE = [
    "आपतकालीन", "चेतावनी", "सूचना", "घोषणा", "निर्णय",
    "निर्वाचन", "मतदान", "उम्मेदवार", "परिणाम",
    "भूकम्प", "बाढी", "पहिरो", "विपद्", "उद्धार",
    "कर्फ्यु", "निषेधाज्ञा", "बन्द", "हड्ताल", "प्रदर्शन",
    "सेना", "सुरक्षा", "तैनाथ", "अभियान",
]


@dataclass
class Tweet:
    """Structured tweet data."""
    id: str
    text: str
    author_id: str
    author_username: Optional[str] = None
    author_name: Optional[str] = None
    created_at: Optional[datetime] = None
    language: str = "en"

    # Engagement metrics
    retweet_count: int = 0
    reply_count: int = 0
    like_count: int = 0
    quote_count: int = 0
    impression_count: int = 0

    # Content flags
    is_retweet: bool = False
    is_reply: bool = False
    is_quote: bool = False

    # References
    conversation_id: Optional[str] = None
    in_reply_to_user_id: Optional[str] = None
    referenced_tweets: List[Dict] = field(default_factory=list)

    # Entities
    hashtags: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)

    # Location
    geo: Optional[Dict] = None

    # Source tracking
    source_query: Optional[str] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Importance scoring (0.0 - 1.0)
    importance_score: float = 0.0

    # Deduplication
    external_id: str = ""

    def __post_init__(self):
        if not self.external_id:
            self.external_id = f"twitter_{self.id}"


@dataclass
class TwitterFetchResult:
    """Result from Twitter API fetch."""
    success: bool
    tweets: List[Tweet] = field(default_factory=list)
    error: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None
    meta: Optional[Dict] = None


@dataclass
class APIUsageStats:
    """Track API usage for budget management."""
    month: str  # YYYY-MM format
    tweet_reads: int = 0
    api_calls: int = 0
    cached_calls: int = 0
    errors: int = 0
    last_call: Optional[datetime] = None


class TwitterFetcher:
    """
    Async Twitter/X API v2 fetcher - FREE TIER OPTIMIZED.

    Strategy for 100 tweets/month:
    - Single combined query for priority accounts
    - Only fetch tweets with importance keywords
    - 6-hour cache TTL to avoid duplicate fetches
    - Poll every 12 hours (~60 polls/month, ~2 tweets/poll)
    """

    # X API v2 endpoints
    BASE_URL = "https://api.twitter.com/2"
    SEARCH_ENDPOINT = "/tweets/search/recent"
    USER_TWEETS_ENDPOINT = "/users/{user_id}/tweets"
    USERS_BY_USERNAME_ENDPOINT = "/users/by/username/{username}"

    # Tier limits (tweets per month)
    TIER_LIMITS = {
        "free": 100,
        "basic": 10_000,
        "pro": 1_000_000,
    }

    # FREE TIER: Single optimized query for all priority accounts
    # Organizations: ECNOfficial, NepaliArmyHQ, BIPADPortal
    # Individuals: thapagk, hamrorabi
    FREE_TIER_QUERY = (
        "(from:ECNOfficial OR from:NepaliArmyHQ OR from:BIPADPortal "
        "OR from:thapagk OR from:hamrorabi) "
        "-is:retweet -is:reply"
    )

    # BASIC/PRO TIER: Multiple queries for broader coverage
    STANDARD_QUERIES = [
        # Priority accounts (all)
        "(from:ECNOfficial OR from:NepaliArmyHQ OR from:BIPADPortal OR from:thapagk OR from:hamrorabi) -is:retweet",
        # Breaking news from major outlets
        "(from:kathmandupost OR from:myrepublica) (breaking OR urgent OR alert) -is:retweet",
        # Nepal disasters
        "(Nepal OR Kathmandu) (earthquake OR flood OR landslide) -is:retweet",
        # Security incidents
        "(Nepal) (curfew OR bandh OR protest) -is:retweet",
    ]

    def __init__(
        self,
        bearer_token: Optional[str] = None,
        tier: str = "free",
        cache_dir: Optional[Path] = None,
        cache_ttl_hours: int = 6,  # 6 hours for free tier (was 1)
    ):
        """
        Initialize Twitter fetcher.

        Args:
            bearer_token: X API Bearer token (from env if not provided)
            tier: API tier (free, basic, pro)
            cache_dir: Directory for query cache
            cache_ttl_hours: How long to cache query results (default 6h for free tier)
        """
        self.bearer_token = bearer_token or getattr(settings, 'twitter_bearer_token', None)
        self.tier = tier.lower()
        self.monthly_limit = self.TIER_LIMITS.get(self.tier, 100)

        # Adjust cache TTL based on tier
        if self.tier == "free":
            self.cache_ttl = timedelta(hours=6)  # Long cache for free tier
        elif self.tier == "basic":
            self.cache_ttl = timedelta(hours=1)
        else:
            self.cache_ttl = timedelta(minutes=30)

        # Cache setup
        self.cache_dir = cache_dir or Path("/tmp/nepal_osint_twitter_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Usage tracking
        self._usage_file = self.cache_dir / "usage_stats.json"
        self._usage = self._load_usage()

        # Daily per-account limit tracking
        self._daily_limits_file = self.cache_dir / "daily_limits.json"
        self._daily_limits = self._load_daily_limits()

        # Query cache
        self._query_cache: Dict[str, Dict] = {}

        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def is_configured(self) -> bool:
        """Check if Twitter API is configured."""
        return bool(self.bearer_token)

    @property
    def budget_remaining(self) -> int:
        """Get remaining tweet budget for this month."""
        current_month = datetime.now().strftime("%Y-%m")
        if self._usage.month != current_month:
            # New month, reset usage
            self._usage = APIUsageStats(month=current_month)
            self._save_usage()
        return max(0, self.monthly_limit - self._usage.tweet_reads)

    async def __aenter__(self) -> "TwitterFetcher":
        """Create session on context entry."""
        if not self.bearer_token:
            logger.warning("Twitter API not configured - bearer token missing")
            return self

        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "User-Agent": "NepalOSINT/5.0",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        )
        return self

    async def __aexit__(self, *args) -> None:
        """Close session on context exit."""
        if self._session:
            await self._session.close()
            self._session = None

    def _load_usage(self) -> APIUsageStats:
        """Load usage stats from file."""
        if self._usage_file.exists():
            try:
                data = json.loads(self._usage_file.read_text())
                return APIUsageStats(**data)
            except Exception:
                pass
        return APIUsageStats(month=datetime.now().strftime("%Y-%m"))

    def _save_usage(self) -> None:
        """Save usage stats to file."""
        data = {
            "month": self._usage.month,
            "tweet_reads": self._usage.tweet_reads,
            "api_calls": self._usage.api_calls,
            "cached_calls": self._usage.cached_calls,
            "errors": self._usage.errors,
            "last_call": self._usage.last_call.isoformat() if self._usage.last_call else None,
        }
        self._usage_file.write_text(json.dumps(data, indent=2))

    # =========================================================================
    # Daily Per-Account Limits
    # Organizations: 5 tweets/day, Individuals: 2 tweets/day
    # =========================================================================

    def _load_daily_limits(self) -> Dict[str, Dict[str, int]]:
        """Load daily per-account limits from file."""
        today = datetime.now().strftime("%Y-%m-%d")

        if self._daily_limits_file.exists():
            try:
                data = json.loads(self._daily_limits_file.read_text())
                # Reset if it's a new day
                if data.get("date") != today:
                    return {"date": today, "accounts": {}}
                return data
            except Exception:
                pass
        return {"date": today, "accounts": {}}

    def _save_daily_limits(self) -> None:
        """Save daily per-account limits to file."""
        self._daily_limits_file.write_text(json.dumps(self._daily_limits, indent=2))

    def _get_account_daily_count(self, username: str) -> int:
        """Get how many tweets we've stored from this account today."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Reset if new day
        if self._daily_limits.get("date") != today:
            self._daily_limits = {"date": today, "accounts": {}}
            self._save_daily_limits()

        return self._daily_limits.get("accounts", {}).get(username.lower(), 0)

    def _get_account_daily_limit(self, username: str) -> int:
        """Get the daily limit for an account (5 for orgs, 2 for individuals)."""
        username_lower = username.lower()
        if username_lower in [k.lower() for k in ORGANIZATION_ACCOUNTS.keys()]:
            return DAILY_LIMIT_ORGANIZATION
        elif username_lower in [k.lower() for k in INDIVIDUAL_ACCOUNTS.keys()]:
            return DAILY_LIMIT_INDIVIDUAL
        return DAILY_LIMIT_INDIVIDUAL  # Default to individual limit

    def _can_store_tweet(self, username: str) -> bool:
        """Check if we can store another tweet from this account today."""
        current = self._get_account_daily_count(username)
        limit = self._get_account_daily_limit(username)
        return current < limit

    def _increment_account_count(self, username: str) -> None:
        """Increment the daily count for an account."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Reset if new day
        if self._daily_limits.get("date") != today:
            self._daily_limits = {"date": today, "accounts": {}}

        username_lower = username.lower()
        current = self._daily_limits.get("accounts", {}).get(username_lower, 0)
        self._daily_limits.setdefault("accounts", {})[username_lower] = current + 1
        self._save_daily_limits()

    def get_daily_limits_status(self) -> Dict[str, Any]:
        """Get current daily limits status for all accounts."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Reset if new day
        if self._daily_limits.get("date") != today:
            self._daily_limits = {"date": today, "accounts": {}}

        status = {
            "date": today,
            "organizations": {},
            "individuals": {},
        }

        for username in ORGANIZATION_ACCOUNTS.keys():
            count = self._get_account_daily_count(username)
            status["organizations"][username] = {
                "count": count,
                "limit": DAILY_LIMIT_ORGANIZATION,
                "remaining": max(0, DAILY_LIMIT_ORGANIZATION - count),
            }

        for username in INDIVIDUAL_ACCOUNTS.keys():
            count = self._get_account_daily_count(username)
            status["individuals"][username] = {
                "count": count,
                "limit": DAILY_LIMIT_INDIVIDUAL,
                "remaining": max(0, DAILY_LIMIT_INDIVIDUAL - count),
            }

        return status

    def _get_cache_key(self, query: str, params: Dict) -> str:
        """Generate cache key for a query."""
        cache_input = f"{query}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(cache_input.encode()).hexdigest()

    def _get_cached_result(self, cache_key: str) -> Optional[TwitterFetchResult]:
        """Get cached result if still valid."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text())
            cached_at = datetime.fromisoformat(data["cached_at"])

            if datetime.now(timezone.utc) - cached_at > self.cache_ttl:
                cache_file.unlink()
                return None

            tweets = [Tweet(**t) for t in data["tweets"]]
            self._usage.cached_calls += 1

            return TwitterFetchResult(
                success=True,
                tweets=tweets,
                meta={"from_cache": True, "cached_at": cached_at.isoformat()},
            )
        except Exception:
            return None

    def _cache_result(self, cache_key: str, tweets: List[Tweet]) -> None:
        """Cache query result."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        data = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "tweets": [
                {
                    "id": t.id,
                    "text": t.text,
                    "author_id": t.author_id,
                    "author_username": t.author_username,
                    "author_name": t.author_name,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "language": t.language,
                    "retweet_count": t.retweet_count,
                    "reply_count": t.reply_count,
                    "like_count": t.like_count,
                    "quote_count": t.quote_count,
                    "hashtags": t.hashtags,
                    "mentions": t.mentions,
                    "urls": t.urls,
                    "source_query": t.source_query,
                    "external_id": t.external_id,
                }
                for t in tweets
            ],
        }
        cache_file.write_text(json.dumps(data, indent=2))

    async def search_tweets(
        self,
        query: str,
        max_results: int = 10,
        use_cache: bool = True,
    ) -> TwitterFetchResult:
        """
        Search recent tweets (last 7 days).

        Args:
            query: Search query (X API v2 query syntax)
            max_results: Maximum tweets to return (10-100)
            use_cache: Whether to use cached results

        Returns:
            TwitterFetchResult with tweets or error
        """
        if not self.is_configured:
            return TwitterFetchResult(
                success=False,
                error="Twitter API not configured - missing bearer token",
            )

        # Check budget
        if self.budget_remaining < max_results:
            return TwitterFetchResult(
                success=False,
                error=f"Monthly tweet budget exhausted ({self._usage.tweet_reads}/{self.monthly_limit})",
            )

        # Check cache
        params = {"max_results": max_results}
        cache_key = self._get_cache_key(query, params)

        if use_cache:
            cached = self._get_cached_result(cache_key)
            if cached:
                logger.debug(f"Using cached result for query: {query[:50]}...")
                return cached

        # Make API request
        url = f"{self.BASE_URL}{self.SEARCH_ENDPOINT}"
        request_params = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,author_id,public_metrics,entities,geo,conversation_id,in_reply_to_user_id,referenced_tweets,lang",
            "expansions": "author_id,referenced_tweets.id",
            "user.fields": "username,name,verified",
        }

        try:
            async with self._session.get(url, params=request_params) as response:
                # Track rate limits
                rate_limit_remaining = int(response.headers.get("x-rate-limit-remaining", 0))
                rate_limit_reset = response.headers.get("x-rate-limit-reset")
                reset_time = None
                if rate_limit_reset:
                    reset_time = datetime.fromtimestamp(int(rate_limit_reset), tz=timezone.utc)

                if response.status == 429:
                    return TwitterFetchResult(
                        success=False,
                        error="Rate limit exceeded",
                        rate_limit_remaining=0,
                        rate_limit_reset=reset_time,
                    )

                if response.status != 200:
                    error_text = await response.text()
                    self._usage.errors += 1
                    self._save_usage()
                    return TwitterFetchResult(
                        success=False,
                        error=f"HTTP {response.status}: {error_text[:200]}",
                        rate_limit_remaining=rate_limit_remaining,
                    )

                data = await response.json()

                # Parse tweets
                tweets = self._parse_tweets(data, query)

                # Update usage
                self._usage.api_calls += 1
                self._usage.tweet_reads += len(tweets)
                self._usage.last_call = datetime.now(timezone.utc)
                self._save_usage()

                # Cache result
                if use_cache and tweets:
                    self._cache_result(cache_key, tweets)

                logger.info(f"Fetched {len(tweets)} tweets for query: {query[:50]}...")

                return TwitterFetchResult(
                    success=True,
                    tweets=tweets,
                    rate_limit_remaining=rate_limit_remaining,
                    rate_limit_reset=reset_time,
                    meta=data.get("meta"),
                )

        except asyncio.TimeoutError:
            self._usage.errors += 1
            self._save_usage()
            return TwitterFetchResult(success=False, error="Request timeout")
        except Exception as e:
            self._usage.errors += 1
            self._save_usage()
            logger.exception("Twitter API error")
            return TwitterFetchResult(success=False, error=str(e))

    def _parse_tweets(self, data: Dict, source_query: str) -> List[Tweet]:
        """Parse API response into Tweet objects."""
        tweets = []

        raw_tweets = data.get("data", [])
        if not raw_tweets:
            return tweets

        # Build user lookup from includes
        users = {}
        for user in data.get("includes", {}).get("users", []):
            users[user["id"]] = user

        for raw in raw_tweets:
            try:
                # Get author info
                author_id = raw.get("author_id", "")
                author = users.get(author_id, {})

                # Parse created_at
                created_at = None
                if raw.get("created_at"):
                    created_at = datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00"))

                # Parse metrics
                metrics = raw.get("public_metrics", {})

                # Parse entities
                entities = raw.get("entities", {})
                hashtags = [h["tag"] for h in entities.get("hashtags", [])]
                mentions = [m["username"] for m in entities.get("mentions", [])]
                urls = [u["expanded_url"] for u in entities.get("urls", []) if u.get("expanded_url")]

                # Detect tweet type
                referenced = raw.get("referenced_tweets", [])
                is_retweet = any(r["type"] == "retweeted" for r in referenced)
                is_reply = any(r["type"] == "replied_to" for r in referenced)
                is_quote = any(r["type"] == "quoted" for r in referenced)

                # Detect language
                lang = raw.get("lang", "en")
                if lang == "ne" or self._has_nepali_chars(raw.get("text", "")):
                    lang = "ne"

                tweet = Tweet(
                    id=raw["id"],
                    text=raw.get("text", ""),
                    author_id=author_id,
                    author_username=author.get("username"),
                    author_name=author.get("name"),
                    created_at=created_at,
                    language=lang,
                    retweet_count=metrics.get("retweet_count", 0),
                    reply_count=metrics.get("reply_count", 0),
                    like_count=metrics.get("like_count", 0),
                    quote_count=metrics.get("quote_count", 0),
                    impression_count=metrics.get("impression_count", 0),
                    is_retweet=is_retweet,
                    is_reply=is_reply,
                    is_quote=is_quote,
                    conversation_id=raw.get("conversation_id"),
                    in_reply_to_user_id=raw.get("in_reply_to_user_id"),
                    referenced_tweets=referenced,
                    hashtags=hashtags,
                    mentions=mentions,
                    urls=urls,
                    geo=raw.get("geo"),
                    source_query=source_query,
                )
                tweets.append(tweet)

            except Exception as e:
                logger.warning(f"Failed to parse tweet: {e}")
                continue

        return tweets

    def _has_nepali_chars(self, text: str) -> bool:
        """Check for Nepali (Devanagari) characters."""
        for char in text:
            if "\u0900" <= char <= "\u097F":
                return True
        return False

    async def fetch_nepal_news(
        self,
        max_per_query: int = 10,
        queries: Optional[List[str]] = None,
    ) -> TwitterFetchResult:
        """
        Fetch Nepal-related tweets using tier-appropriate strategy.

        FREE TIER (100/month):
        - Single query for priority accounts only
        - Max 10 tweets per fetch
        - 6-hour cache to avoid repeats

        BASIC/PRO TIER:
        - Multiple queries for broader coverage
        - Standard caching

        Args:
            max_per_query: Max tweets per query
            queries: Custom queries (uses tier defaults if None)

        Returns:
            Combined TwitterFetchResult
        """
        all_tweets = []
        seen_ids: Set[str] = set()
        skipped_by_limit: Dict[str, int] = {}  # Track skipped tweets per account

        # FREE TIER: Single optimized query
        if self.tier == "free":
            if self.budget_remaining < 3:
                logger.warning(f"Budget critically low ({self.budget_remaining} remaining), skipping fetch")
                return TwitterFetchResult(
                    success=False,
                    error=f"Budget too low: {self.budget_remaining} tweets remaining this month",
                    meta={"budget_remaining": self.budget_remaining},
                )

            # Use single combined query for max efficiency
            result = await self.search_tweets(
                self.FREE_TIER_QUERY,
                max_results=min(max_per_query, 10),  # Cap at 10 for free tier
            )

            if result.success:
                # Filter for importance AND daily per-account limits
                for tweet in result.tweets:
                    username = tweet.author_username or ""

                    # Check daily per-account limit
                    if username and not self._can_store_tweet(username):
                        skipped_by_limit[username] = skipped_by_limit.get(username, 0) + 1
                        logger.debug(f"Skipping tweet from {username}: daily limit reached")
                        continue

                    # Check importance score
                    importance = self._calculate_importance(tweet)
                    tweet.importance_score = importance

                    if importance >= 0.3:  # Only keep moderately important tweets
                        all_tweets.append(tweet)
                        # Increment daily count for this account
                        if username:
                            self._increment_account_count(username)

                logger.info(
                    f"FREE TIER: Fetched {len(result.tweets)} tweets, "
                    f"{len(all_tweets)} passed filters (importance + daily limits), "
                    f"skipped by limit: {sum(skipped_by_limit.values())}, "
                    f"budget remaining: {self.budget_remaining}"
                )

            return TwitterFetchResult(
                success=True,
                tweets=all_tweets,
                meta={
                    "tier": "free",
                    "query_used": self.FREE_TIER_QUERY,
                    "fetched": len(result.tweets) if result.success else 0,
                    "passed_filter": len(all_tweets),
                    "skipped_by_daily_limit": skipped_by_limit,
                    "budget_remaining": self.budget_remaining,
                    "daily_limits": self.get_daily_limits_status(),
                },
            )

        # BASIC/PRO TIER: Multiple queries
        queries = queries or self.STANDARD_QUERIES

        for query in queries:
            if self.budget_remaining < max_per_query:
                logger.warning("Budget exhausted, stopping early")
                break

            result = await self.search_tweets(query, max_results=max_per_query)

            if result.success:
                for tweet in result.tweets:
                    if tweet.id not in seen_ids:
                        seen_ids.add(tweet.id)
                        tweet.importance_score = self._calculate_importance(tweet)
                        all_tweets.append(tweet)

        return TwitterFetchResult(
            success=True,
            tweets=all_tweets,
            meta={
                "tier": self.tier,
                "queries_used": len(queries),
                "unique_tweets": len(all_tweets),
                "budget_remaining": self.budget_remaining,
            },
        )

    def _calculate_importance(self, tweet: "Tweet") -> float:
        """
        Calculate importance score for a tweet (0.0 - 1.0).

        Higher scores for:
        - Official/verified accounts
        - Contains importance keywords
        - High engagement relative to typical
        - Breaking news indicators
        """
        score = 0.0
        text_lower = tweet.text.lower()

        # Priority account bonus (+0.3)
        if tweet.author_username and tweet.author_username.lower() in [
            a.lower() for a in PRIORITY_ACCOUNTS
        ]:
            score += 0.3

        # English importance keywords (+0.1 each, max 0.3)
        en_matches = sum(1 for kw in IMPORTANCE_KEYWORDS_EN if kw in text_lower)
        score += min(en_matches * 0.1, 0.3)

        # Nepali importance keywords (+0.1 each, max 0.3)
        ne_matches = sum(1 for kw in IMPORTANCE_KEYWORDS_NE if kw in tweet.text)
        score += min(ne_matches * 0.1, 0.3)

        # High engagement bonus (+0.1)
        total_engagement = tweet.retweet_count + tweet.like_count + tweet.reply_count
        if total_engagement > 100:
            score += 0.1
        elif total_engagement > 50:
            score += 0.05

        # Breaking news indicators (+0.1)
        breaking_indicators = ["breaking", "urgent", "just in", "developing", "आपतकालीन"]
        if any(ind in text_lower or ind in tweet.text for ind in breaking_indicators):
            score += 0.1

        return min(score, 1.0)

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current API usage statistics."""
        return {
            "month": self._usage.month,
            "tier": self.tier,
            "monthly_limit": self.monthly_limit,
            "tweets_read": self._usage.tweet_reads,
            "budget_remaining": self.budget_remaining,
            "api_calls": self._usage.api_calls,
            "cached_calls": self._usage.cached_calls,
            "errors": self._usage.errors,
            "last_call": self._usage.last_call.isoformat() if self._usage.last_call else None,
            "budget_percentage_used": round(
                (self._usage.tweet_reads / self.monthly_limit) * 100, 1
            ) if self.monthly_limit > 0 else 0,
        }


# Convenience function for quick access
async def fetch_nepal_tweets(
    bearer_token: Optional[str] = None,
    max_tweets: int = 50,
) -> TwitterFetchResult:
    """
    Quick helper to fetch Nepal-related tweets.

    Usage:
        result = await fetch_nepal_tweets()
        for tweet in result.tweets:
            print(tweet.text)
    """
    async with TwitterFetcher(bearer_token=bearer_token) as fetcher:
        return await fetcher.fetch_nepal_news(max_per_query=max_tweets // 4)
