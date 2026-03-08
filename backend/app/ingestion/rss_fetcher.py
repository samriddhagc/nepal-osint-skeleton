"""Async RSS feed fetcher with connection pooling."""
import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class FetchedArticle:
    """Normalized article from RSS feed."""
    source_id: str
    source_name: str
    url: str
    title: str
    summary: Optional[str] = None
    content: Optional[str] = None
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    language: str = "en"
    external_id: str = ""  # SHA256 hash for dedup

    def __post_init__(self):
        """Generate external_id if not set."""
        if not self.external_id:
            self.external_id = self._generate_external_id()

    def _generate_external_id(self) -> str:
        """Generate deduplication hash from URL."""
        # Normalize URL: remove tracking params
        url = self.url.split("?")[0].rstrip("/")
        hash_input = f"{url}:{self.title}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:32]


@dataclass
class FetchResult:
    """Result of fetching a single RSS source."""
    source_id: str
    source_name: str
    success: bool
    articles: list[FetchedArticle] = field(default_factory=list)
    error: Optional[str] = None
    fetch_time_ms: float = 0.0


class RSSFetcher:
    """Async RSS feed fetcher with connection pooling and concurrency control."""

    def __init__(
        self,
        max_concurrent: int = 10,
        timeout: int = 30,
        per_host_limit: int = 3,
    ):
        self.max_concurrent = max_concurrent
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.per_host_limit = per_host_limit
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def __aenter__(self) -> "RSSFetcher":
        """Create session and semaphore on context entry."""
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent * 2,
            limit_per_host=self.per_host_limit,
            ttl_dns_cache=300,
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            headers={
                "User-Agent": "NepalOSINT/5.0 (RSS Feed Fetcher)",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self

    async def __aexit__(self, *args) -> None:
        """Close session on context exit."""
        if self._session:
            await self._session.close()
            self._session = None

    async def fetch_source(
        self,
        source_id: str,
        source_name: str,
        url: str,
        language: str = "en",
    ) -> FetchResult:
        """Fetch and parse a single RSS source."""
        start_time = time.monotonic()

        async with self._semaphore:
            try:
                async with self._session.get(url) as response:
                    if response.status != 200:
                        return FetchResult(
                            source_id=source_id,
                            source_name=source_name,
                            success=False,
                            error=f"HTTP {response.status}",
                            fetch_time_ms=(time.monotonic() - start_time) * 1000,
                        )

                    content = await response.text()

                # Parse feed
                feed = feedparser.parse(content)

                if feed.bozo and not feed.entries:
                    return FetchResult(
                        source_id=source_id,
                        source_name=source_name,
                        success=False,
                        error=f"Invalid RSS: {feed.bozo_exception}",
                        fetch_time_ms=(time.monotonic() - start_time) * 1000,
                    )

                # Parse entries
                articles = []
                for entry in feed.entries:
                    article = self._parse_entry(entry, source_id, source_name, language)
                    if article:
                        articles.append(article)

                return FetchResult(
                    source_id=source_id,
                    source_name=source_name,
                    success=True,
                    articles=articles,
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )

            except asyncio.TimeoutError:
                return FetchResult(
                    source_id=source_id,
                    source_name=source_name,
                    success=False,
                    error="Timeout",
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )
            except Exception as e:
                logger.exception(f"Error fetching {source_id}")
                return FetchResult(
                    source_id=source_id,
                    source_name=source_name,
                    success=False,
                    error=str(e),
                    fetch_time_ms=(time.monotonic() - start_time) * 1000,
                )

    async def fetch_many(
        self,
        sources: list[dict],
    ) -> list[FetchResult]:
        """Fetch multiple RSS sources concurrently."""
        tasks = [
            self.fetch_source(
                source_id=s["id"],
                source_name=s["name"],
                url=s["url"],
                language=s.get("language", "en"),
            )
            for s in sources
        ]
        return await asyncio.gather(*tasks)

    def _parse_entry(
        self,
        entry: dict,
        source_id: str,
        source_name: str,
        language: str,
    ) -> Optional[FetchedArticle]:
        """Parse a feedparser entry into FetchedArticle."""
        url = entry.get("link", "")
        title = entry.get("title", "")

        if not url or not title:
            return None

        # Clean title
        title = self._clean_html(title).strip()
        if not title:
            return None

        # Parse published date
        published_at = self._parse_date(entry)

        # CRITICAL: Skip stories older than 7 days to prevent stale content
        if published_at:
            age_days = (datetime.now(timezone.utc) - published_at).days
            if age_days > 7:
                logger.debug(f"Skipping old story ({age_days} days old): {title[:50]}")
                return None

        # Extract summary
        summary = None
        if entry.get("summary"):
            summary = self._clean_html(entry["summary"])[:2000]

        # Extract categories/tags
        categories = []
        for tag in entry.get("tags", []):
            term = tag.get("term", "")
            if term:
                categories.append(term)

        # Detect language from content if Nepali
        detected_lang = language
        if self._has_nepali_chars(title):
            detected_lang = "ne"

        return FetchedArticle(
            source_id=source_id,
            source_name=source_name,
            url=url,
            title=title,
            summary=summary,
            published_at=published_at,
            author=entry.get("author"),
            categories=categories[:10],  # Limit categories
            language=detected_lang,
        )

    def _parse_date(self, entry: dict) -> Optional[datetime]:
        """Parse date from feedparser entry."""
        # Try published_parsed first
        if entry.get("published_parsed"):
            try:
                return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        # Try updated_parsed
        if entry.get("updated_parsed"):
            try:
                return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        # Try parsing string date
        for field in ("published", "updated", "created"):
            date_str = entry.get(field)
            if date_str:
                try:
                    return parsedate_to_datetime(date_str)
                except (ValueError, TypeError):
                    continue

        return None

    def _clean_html(self, html: str) -> str:
        """Strip HTML tags and clean whitespace."""
        if not html:
            return ""
        soup = BeautifulSoup(html, "lxml")
        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
        # Normalize whitespace
        return " ".join(text.split())

    def _has_nepali_chars(self, text: str) -> bool:
        """Check if text contains Nepali (Devanagari) characters."""
        for char in text:
            if "\u0900" <= char <= "\u097F":
                return True
        return False
