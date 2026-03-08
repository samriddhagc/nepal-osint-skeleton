"""Nitter scraper for Twitter/X data without API keys.

Uses Nitter instances (open-source Twitter frontend) to scrape tweets.
Solves SHA1 proof-of-work challenges automatically (handles both 403 and 503 challenge pages).
"""

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from urllib.parse import quote

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ScrapedTweet:
    """A tweet scraped from Nitter."""

    tweet_id: str
    author_username: str
    author_name: str
    text: str
    tweeted_at: Optional[datetime] = None
    is_retweet: bool = False
    is_reply: bool = False
    is_quote: bool = False
    retweet_count: int = 0
    reply_count: int = 0
    like_count: int = 0
    quote_count: int = 0
    hashtags: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    media_urls: List[str] = field(default_factory=list)
    language: str = "en"


@dataclass
class NitterScrapeResult:
    """Result of a Nitter scrape operation."""

    success: bool
    tweets: List[ScrapedTweet] = field(default_factory=list)
    instance_used: str = ""
    error: Optional[str] = None
    scrape_duration_ms: int = 0


@dataclass
class NitterInstance:
    """A Nitter instance with health tracking."""

    url: str
    priority: int = 1
    consecutive_failures: int = 0
    last_failure_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None

    @property
    def is_healthy(self) -> bool:
        """Check if instance is healthy (not in backoff)."""
        if self.consecutive_failures == 0:
            return True
        if self.last_failure_at is None:
            return True
        # Exponential backoff: 5min, 15min, 1hr, 1hr cap
        backoff_minutes = min(60, 5 * (3 ** (self.consecutive_failures - 1)))
        cooldown_until = self.last_failure_at + timedelta(minutes=backoff_minutes)
        return datetime.now(timezone.utc) > cooldown_until

    def record_success(self):
        self.consecutive_failures = 0
        self.last_success_at = datetime.now(timezone.utc)

    def record_failure(self):
        self.consecutive_failures += 1
        self.last_failure_at = datetime.now(timezone.utc)


class NitterInstanceManager:
    """Manages ordered list of Nitter instances with health tracking."""

    def __init__(self, instances_config: List[dict]):
        self.instances: List[NitterInstance] = []
        for cfg in sorted(instances_config, key=lambda x: x.get("priority", 1)):
            self.instances.append(
                NitterInstance(
                    url=cfg["url"].rstrip("/"),
                    priority=cfg.get("priority", 1),
                )
            )
        if not self.instances:
            raise ValueError("At least one Nitter instance is required")

    def get_healthy_instances(self) -> List[NitterInstance]:
        """Get instances that are not in backoff, ordered by priority."""
        return [i for i in self.instances if i.is_healthy]

    def get_status(self) -> List[dict]:
        """Get status of all instances for API reporting."""
        return [
            {
                "url": i.url,
                "priority": i.priority,
                "healthy": i.is_healthy,
                "consecutive_failures": i.consecutive_failures,
                "last_success": i.last_success_at.isoformat() if i.last_success_at else None,
                "last_failure": i.last_failure_at.isoformat() if i.last_failure_at else None,
            }
            for i in self.instances
        ]


class NitterScraper:
    """Async Nitter scraper with PoW solving and instance failover."""

    # Regex to extract PoW challenge from Nitter's 503 page
    POW_CHALLENGE_RE = re.compile(r"'([A-Fa-f0-9]{40})'")

    # Regex to extract tweet ID from href like /user/status/1234567890#m
    TWEET_ID_RE = re.compile(r"/status/(\d+)")

    # Devanagari Unicode range for language detection
    DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

    def __init__(
        self,
        instance_manager: NitterInstanceManager,
        request_timeout: int = 30,
        delay_between_requests: float = 4.0,
    ):
        self.instance_manager = instance_manager
        self.request_timeout = request_timeout
        self.delay_between_requests = delay_between_requests
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.request_timeout),
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None

    @staticmethod
    def _solve_pow(challenge: str) -> str:
        """Solve Nitter's SHA1 proof-of-work challenge.

        The JS challenge works as:
            n1 = parseInt(challenge[0], 16)  // first hex char as int
            find i where sha1(challenge + str(i)).digest()[n1] == 0xb0
                     and sha1(challenge + str(i)).digest()[n1+1] == 0x0b
        Cookie: res=<challenge><i>
        """
        n1 = int(challenge[0], 16)
        challenge_bytes = challenge.encode("ascii")
        for i in range(10_000_000):
            candidate = challenge_bytes + str(i).encode("ascii")
            digest = hashlib.sha1(candidate).digest()
            if digest[n1] == 0xB0 and digest[n1 + 1] == 0x0B:
                return str(i)
        raise RuntimeError(f"Failed to solve PoW for challenge {challenge}")

    def _extract_pow_challenge(self, html: str) -> Optional[str]:
        """Extract PoW challenge string from Nitter's 503 page."""
        match = self.POW_CHALLENGE_RE.search(html)
        if match:
            return match.group(1)
        return None

    # Sentinel for 404 (account not found) — not an instance failure
    _NOT_FOUND = "__NOT_FOUND__"

    async def _fetch_with_pow(
        self, instance: NitterInstance, path: str
    ) -> Optional[str]:
        """Fetch a page from a Nitter instance, solving PoW if needed.

        Nitter returns 403 (or sometimes 503) with a JS-based SHA1 PoW challenge.
        We extract the challenge, solve it server-side, set the `res` cookie, and retry.

        Returns:
            HTML string on success, self._NOT_FOUND for 404, None on failure.
        """
        url = f"{instance.url}{path}"

        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    instance.record_success()
                    return await resp.text()

                if resp.status == 404:
                    # Account doesn't exist — NOT an instance failure
                    instance.record_success()  # instance is healthy
                    logger.info(f"Account not found (404): {path}")
                    return self._NOT_FOUND

                if resp.status == 429:
                    # Rate limited — wait before next request
                    logger.warning(f"Rate limited (429) from {instance.url}, waiting 30s...")
                    await asyncio.sleep(30)
                    instance.record_failure()
                    return None

                if resp.status == 502:
                    # Temporary server error — short wait, don't penalize heavily
                    logger.warning(f"Server error (502) from {url}, waiting 5s...")
                    await asyncio.sleep(5)
                    return None  # Don't record failure for transient 502s

                if resp.status in (403, 503):
                    # PoW challenge — solve and retry
                    html = await resp.text()
                    challenge = self._extract_pow_challenge(html)
                    if not challenge:
                        logger.warning(
                            f"Got {resp.status} from {instance.url} but no PoW challenge found"
                        )
                        instance.record_failure()
                        return None

                    logger.debug(f"Solving PoW for {instance.url} (status {resp.status})...")
                    t0 = time.monotonic()
                    solution = self._solve_pow(challenge)
                    elapsed = (time.monotonic() - t0) * 1000
                    logger.debug(f"PoW solved in {elapsed:.0f}ms (answer={solution})")

                    # Set the res cookie (format: res=<challenge><solution>)
                    cookie_value = f"{challenge}{solution}"
                    self._session.cookie_jar.update_cookies(
                        {"res": cookie_value}, response_url=resp.url
                    )

                    async with self._session.get(url) as retry_resp:
                        if retry_resp.status == 200:
                            instance.record_success()
                            return await retry_resp.text()
                        else:
                            logger.warning(
                                f"PoW retry failed: {retry_resp.status} from {instance.url}"
                            )
                            instance.record_failure()
                            return None
                else:
                    logger.warning(f"Unexpected status {resp.status} from {url}")
                    instance.record_failure()
                    return None

        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {url}")
            instance.record_failure()
            return None
        except aiohttp.ClientError as e:
            logger.warning(f"HTTP error fetching {url}: {e}")
            # Connection errors are often transient — wait a bit before continuing
            await asyncio.sleep(3)
            instance.record_failure()
            return None

    async def _fetch_with_failover(self, path: str) -> Tuple[Optional[str], Optional[NitterInstance]]:
        """Try healthy instances until one works."""
        healthy = self.instance_manager.get_healthy_instances()

        if not healthy:
            # All instances in backoff — try the one with earliest backoff expiry
            logger.warning("All Nitter instances in backoff, trying least-failed")
            healthy = sorted(
                self.instance_manager.instances,
                key=lambda i: i.consecutive_failures,
            )[:1]

        for instance in healthy:
            html = await self._fetch_with_pow(instance, path)
            if html == self._NOT_FOUND:
                return self._NOT_FOUND, instance
            if html:
                return html, instance
            # Small delay before trying next instance
            await asyncio.sleep(0.5)

        return None, None

    def _detect_language(self, text: str) -> str:
        """Detect language: Devanagari chars → 'ne', else 'en'."""
        devanagari_count = len(self.DEVANAGARI_RE.findall(text))
        if devanagari_count >= 3:
            return "ne"
        return "en"

    def _parse_stat(self, stat_text: str) -> int:
        """Parse a stat like '1.2K' or '500' into an integer."""
        if not stat_text:
            return 0
        stat_text = stat_text.strip().replace(",", "")
        if stat_text.endswith("K"):
            return int(float(stat_text[:-1]) * 1000)
        if stat_text.endswith("M"):
            return int(float(stat_text[:-1]) * 1_000_000)
        try:
            return int(stat_text)
        except ValueError:
            return 0

    def _parse_tweets(self, html: str, instance_url: str = "") -> List[ScrapedTweet]:
        """Parse tweets from Nitter HTML."""
        soup = BeautifulSoup(html, "html.parser")
        tweets = []

        for item in soup.select("div.timeline-item"):
            try:
                tweet = self._parse_single_tweet(item, instance_url=instance_url)
                if tweet:
                    tweets.append(tweet)
            except Exception as e:
                logger.debug(f"Failed to parse tweet item: {e}")
                continue

        return tweets

    def _parse_single_tweet(self, item, instance_url: str = "") -> Optional[ScrapedTweet]:
        """Parse a single tweet from a timeline-item div."""
        body = item.select_one("div.tweet-body")
        if not body:
            return None

        # Author info
        username_el = body.select_one("a.username")
        fullname_el = body.select_one("a.fullname")
        if not username_el:
            return None

        username = username_el.get_text(strip=True).lstrip("@")
        author_name = fullname_el.get_text(strip=True) if fullname_el else username

        # Tweet ID from the date link href: /{user}/status/{tweet_id}#m
        tweet_id = None
        date_link = body.select_one("span.tweet-date a")
        if date_link and date_link.get("href"):
            id_match = self.TWEET_ID_RE.search(date_link["href"])
            if id_match:
                tweet_id = id_match.group(1)

        if not tweet_id:
            return None

        # Tweeted time from the title attribute: "Feb 28, 2026 · 6:46 AM UTC"
        tweeted_at = None
        if date_link and date_link.get("title"):
            try:
                raw_date = date_link["title"].replace(" · ", " ").replace("\u00b7", "")
                # Try parsing common Nitter date formats
                for fmt in [
                    "%b %d, %Y %I:%M %p %Z",
                    "%b %d, %Y %I:%M %p UTC",
                    "%b %d, %Y %H:%M %Z",
                ]:
                    try:
                        tweeted_at = datetime.strptime(raw_date.strip(), fmt).replace(
                            tzinfo=timezone.utc
                        )
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # Tweet text
        content_el = body.select_one("div.tweet-content")
        text = content_el.get_text(strip=True) if content_el else ""
        if not text:
            return None

        # Retweet / reply / quote detection
        is_retweet = bool(item.select_one("div.retweet-header"))
        is_reply = bool(body.select_one("div.replying-to"))
        is_quote = bool(body.select_one("div.quote"))

        # Engagement stats — 4 stat icons in order: replies, retweets, quotes, likes
        stats = body.select("span.tweet-stat")
        stat_values = []
        for stat in stats:
            val_el = stat.select_one("div.icon-container")
            if val_el:
                stat_values.append(self._parse_stat(val_el.get_text(strip=True)))
            else:
                stat_values.append(0)

        reply_count = stat_values[0] if len(stat_values) > 0 else 0
        retweet_count = stat_values[1] if len(stat_values) > 1 else 0
        quote_count = stat_values[2] if len(stat_values) > 2 else 0
        like_count = stat_values[3] if len(stat_values) > 3 else 0

        # Extract hashtags, mentions, URLs from tweet content
        hashtags = []
        mentions = []
        urls = []
        if content_el:
            for link in content_el.select("a"):
                href = link.get("href", "")
                link_text = link.get_text(strip=True)
                if link_text.startswith("#"):
                    hashtags.append(link_text.lstrip("#"))
                elif link_text.startswith("@"):
                    mentions.append(link_text.lstrip("@"))
                elif href.startswith("http"):
                    urls.append(href)

        # Extract media URLs from attachments
        media_urls = []
        attachments = body.select_one("div.attachments")
        if attachments:
            for img_link in attachments.select("a.still-image"):
                href = img_link.get("href", "")
                if href:
                    full_url = f"{instance_url}{href}" if not href.startswith("http") else href
                    media_urls.append(full_url)
            if not media_urls:
                for vid in attachments.select("div.video-container img"):
                    src = vid.get("src", "")
                    if src:
                        full_url = f"{instance_url}{src}" if not src.startswith("http") else src
                        media_urls.append(full_url)

        language = self._detect_language(text)

        return ScrapedTweet(
            tweet_id=tweet_id,
            author_username=username,
            author_name=author_name,
            text=text,
            tweeted_at=tweeted_at,
            is_retweet=is_retweet,
            is_reply=is_reply,
            is_quote=is_quote,
            retweet_count=retweet_count,
            reply_count=reply_count,
            like_count=like_count,
            quote_count=quote_count,
            hashtags=hashtags,
            mentions=mentions,
            urls=urls,
            media_urls=media_urls,
            language=language,
        )

    # Regex to extract cursor from Nitter's "show more" pagination link
    CURSOR_RE = re.compile(r'[?&]cursor=([^"&]+)')

    def _extract_cursor(self, html: str) -> Optional[str]:
        """Extract the next-page cursor from the 'show more' link."""
        soup = BeautifulSoup(html, "html.parser")
        show_more = soup.select_one("div.show-more a")
        if show_more and show_more.get("href"):
            match = self.CURSOR_RE.search(show_more["href"])
            if match:
                return match.group(1)
        return None

    MAX_PAGES = 10  # Safety cap — ~200 tweets max per account

    async def scrape_user_timeline(
        self, username: str, max_pages: int = 0,
    ) -> NitterScrapeResult:
        """Scrape a user's full timeline with pagination.

        Args:
            username: Twitter handle (without @).
            max_pages: Max pages to fetch (0 = use self.MAX_PAGES default).
        """
        t0 = time.monotonic()
        pages_limit = max_pages or self.MAX_PAGES
        all_tweets: List[ScrapedTweet] = []
        seen_ids: set[str] = set()
        instance_used = ""

        path = f"/{username}"
        for page in range(pages_limit):
            html, instance = await self._fetch_with_failover(path)
            if html == self._NOT_FOUND:
                return NitterScrapeResult(
                    success=True,  # Instance worked, account just doesn't exist
                    error=f"Account @{username} not found (404)",
                    scrape_duration_ms=int((time.monotonic() - t0) * 1000),
                )
            if not html:
                if page == 0:
                    return NitterScrapeResult(
                        success=False,
                        error=f"All instances failed for /{username}",
                        scrape_duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                break  # Partial success — return what we have

            if instance:
                instance_used = instance.url

            page_tweets = self._parse_tweets(html, instance_url=instance.url if instance else "")

            # Dedup within this scrape (Nitter can repeat tweets across pages)
            new_on_page = 0
            for t in page_tweets:
                if t.tweet_id not in seen_ids:
                    seen_ids.add(t.tweet_id)
                    all_tweets.append(t)
                    new_on_page += 1

            logger.debug(
                f"@{username} page {page + 1}: {len(page_tweets)} parsed, {new_on_page} new"
            )

            # No new tweets on this page → we've reached the end
            if new_on_page == 0:
                break

            # Extract cursor for next page
            cursor = self._extract_cursor(html)
            if not cursor:
                break  # No more pages

            path = f"/{username}?cursor={cursor}"

            # Polite delay between pages
            await asyncio.sleep(self.delay_between_requests)

        elapsed = int((time.monotonic() - t0) * 1000)
        pages_fetched = min(page + 1, pages_limit) if all_tweets else 0

        logger.info(
            f"Scraped {len(all_tweets)} tweets from @{username} "
            f"({pages_fetched} pages) via {instance_used} ({elapsed}ms)"
        )

        return NitterScrapeResult(
            success=True,
            tweets=all_tweets,
            instance_used=instance_used,
            scrape_duration_ms=elapsed,
        )

    async def scrape_hashtag_search(self, hashtag: str) -> NitterScrapeResult:
        """Scrape tweets for a hashtag search."""
        t0 = time.monotonic()
        tag = hashtag.lstrip("#")
        path = f"/search?f=tweets&q=%23{quote(tag)}"

        html, instance = await self._fetch_with_failover(path)
        if not html:
            return NitterScrapeResult(
                success=False,
                error=f"All instances failed for #{tag}",
                scrape_duration_ms=int((time.monotonic() - t0) * 1000),
            )

        tweets = self._parse_tweets(html, instance_url=instance.url if instance else "")
        elapsed = int((time.monotonic() - t0) * 1000)

        logger.info(
            f"Scraped {len(tweets)} tweets for #{tag} via {instance.url} ({elapsed}ms)"
        )

        return NitterScrapeResult(
            success=True,
            tweets=tweets,
            instance_used=instance.url,
            scrape_duration_ms=elapsed,
        )

    async def scrape_text_search(self, query: str) -> NitterScrapeResult:
        """Scrape tweets for a plain text search query."""
        t0 = time.monotonic()
        path = f"/search?f=tweets&q={quote(query)}"

        html, instance = await self._fetch_with_failover(path)
        if not html:
            return NitterScrapeResult(
                success=False,
                error=f"All instances failed for search '{query}'",
                scrape_duration_ms=int((time.monotonic() - t0) * 1000),
            )

        tweets = self._parse_tweets(html, instance_url=instance.url if instance else "")
        elapsed = int((time.monotonic() - t0) * 1000)

        logger.info(
            f"Scraped {len(tweets)} tweets for '{query}' via {instance.url} ({elapsed}ms)"
        )

        return NitterScrapeResult(
            success=True,
            tweets=tweets,
            instance_used=instance.url,
            scrape_duration_ms=elapsed,
        )
