"""URL normalization and deduplication utilities."""
import hashlib
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


# Tracking parameters to strip from URLs
TRACKING_PARAMS = {
    # Google Analytics
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_source_platform", "utm_creative_format",
    # Facebook
    "fbclid", "fb_action_ids", "fb_action_types", "fb_source", "fb_ref",
    # Google Ads
    "gclid", "gclsrc", "dclid",
    # Microsoft/Bing
    "msclkid",
    # Twitter
    "twclid",
    # General tracking
    "ref", "source", "mc_cid", "mc_eid", "_ga", "_gl",
    # News-specific
    "share", "shared", "via", "from",
}


def normalize_url(url: str) -> str:
    """
    Normalize URL by removing tracking parameters and standardizing format.

    This helps deduplicate the same article shared with different tracking params.
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url)

        # Parse and filter query params
        params = parse_qs(parsed.query, keep_blank_values=False)
        filtered_params = {
            k: v for k, v in params.items()
            if k.lower() not in TRACKING_PARAMS
        }

        # Rebuild query string
        new_query = urlencode(filtered_params, doseq=True) if filtered_params else ""

        # Normalize path (remove trailing slash)
        path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

        # Rebuild URL
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            new_query,
            "",  # Remove fragment
        ))

        return normalized

    except Exception:
        # If parsing fails, return original
        return url


def generate_external_id(url: str, title: str = "") -> str:
    """
    Generate a unique external ID for deduplication.

    Uses normalized URL as primary key, with title as secondary.
    Returns first 32 chars of SHA256 hash.
    """
    normalized_url = normalize_url(url)

    # Primary: hash of normalized URL
    hash_input = normalized_url

    # Add title if URL alone isn't unique enough (e.g., homepage links)
    if title and len(normalized_url) < 50:
        hash_input = f"{normalized_url}:{title[:100]}"

    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:32]


class Deduplicator:
    """
    In-memory deduplicator for batch operations.

    Tracks seen external IDs to avoid processing duplicates within a batch.
    For persistent dedup, use database external_id constraint.
    """

    def __init__(self):
        self._seen: set[str] = set()

    def is_duplicate(self, external_id: str) -> bool:
        """Check if external_id has been seen."""
        return external_id in self._seen

    def mark_seen(self, external_id: str) -> None:
        """Mark external_id as seen."""
        self._seen.add(external_id)

    def check_and_mark(self, external_id: str) -> bool:
        """
        Check if duplicate and mark as seen.

        Returns True if this is a NEW item (not duplicate).
        Returns False if this is a duplicate.
        """
        if external_id in self._seen:
            return False
        self._seen.add(external_id)
        return True

    def clear(self) -> None:
        """Clear all seen items."""
        self._seen.clear()

    @property
    def count(self) -> int:
        """Number of unique items seen."""
        return len(self._seen)
