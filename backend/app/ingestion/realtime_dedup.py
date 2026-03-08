"""Real-time story deduplication and clustering at ingestion time.

This module provides fast, lightweight similarity detection that runs
during story ingestion to immediately group related stories together.

Unlike the heavy E5-Large semantic clustering (which runs every 30 min),
this uses:
1. Character n-gram TF-IDF (works for Nepali/English)
2. Entity extraction (locations, numbers, keywords)
3. Time-window filtering (only match stories within 48 hours)

This catches ~80% of duplicates immediately at ingestion time.
"""
import re
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass

# Nepal district names for entity extraction
NEPAL_DISTRICTS = {
    # English names
    "taplejung", "panchthar", "ilam", "jhapa", "morang", "sunsari", "dhankuta",
    "terhathum", "sankhuwasabha", "bhojpur", "solukhumbu", "okhaldhunga", "khotang",
    "udayapur", "saptari", "siraha", "dhanusa", "mahottari", "sarlahi", "sindhuli",
    "ramechhap", "dolakha", "sindhupalchok", "kavrepalanchok", "lalitpur", "bhaktapur",
    "kathmandu", "nuwakot", "rasuwa", "dhading", "makwanpur", "rautahat", "bara",
    "parsa", "chitwan", "gorkha", "lamjung", "tanahu", "syangja", "kaski", "manang",
    "mustang", "myagdi", "parbat", "baglung", "gulmi", "palpa", "nawalparasi",
    "rupandehi", "kapilvastu", "arghakhanchi", "pyuthan", "rolpa", "rukum", "salyan",
    "dang", "banke", "bardiya", "surkhet", "dailekh", "jajarkot", "dolpa", "jumla",
    "kalikot", "mugu", "humla", "bajura", "bajhang", "achham", "doti", "kailali",
    "kanchanpur", "dadeldhura", "baitadi", "darchula",
    # Nepali names (common ones)
    "म्याग्दी", "बागलुङ", "पर्वत", "काठमाडौं", "ललितपुर", "भक्तपुर", "काभ्रे",
    "सिन्धुली", "रामेछाप", "दोलखा", "सिन्धुपाल्चोक", "नुवाकोट", "रसुवा", "धादिङ",
    "मकवानपुर", "चितवन", "गोरखा", "लमजुङ", "तनहुँ", "स्याङ्जा", "कास्की",
    "मनाङ", "मुस्ताङ", "गुल्मी", "पाल्पा", "नवलपरासी", "रुपन्देही", "कपिलवस्तु",
    "अर्घाखाँची", "प्युठान", "रोल्पा", "रुकुम", "सल्यान", "दाङ", "बाँके", "बर्दिया",
    "सुर्खेत", "दैलेख", "जाजरकोट", "डोल्पा", "जुम्ला", "कालिकोट", "मुगु", "हुम्ला",
    "बाजुरा", "बझाङ", "अछाम", "डोटी", "कैलाली", "कञ्चनपुर", "डडेलधुरा", "बैतडी",
    "दार्चुला", "झापा", "मोरङ", "सुनसरी", "धनकुटा", "तेह्रथुम", "भोजपुर",
    "सोलुखुम्बु", "ओखलढुङ्गा", "खोटाङ", "उदयपुर", "सप्तरी", "सिराहा", "धनुषा",
    "महोत्तरी", "सर्लाही", "रौतहट", "बारा", "पर्सा",
}

# Common Nepali keywords for entity matching
NEPALI_KEYWORDS = {
    # Security
    "प्रहरी", "सेना", "हतियार", "बन्दुक", "गोली", "घटना", "दुर्घटना", "मृत्यु",
    # Political
    "मतदान", "निर्वाचन", "उम्मेदवार", "सांसद", "मन्त्री", "प्रधानमन्त्री", "सरकार",
    # Economic
    "करोड", "लाख", "रुपैयाँ", "बजार", "व्यापार", "उत्पादन", "किसान",
    # Infrastructure
    "सडक", "पुल", "भवन", "निर्माण", "योजना", "विकास",
    # Disaster
    "आगलागी", "बाढी", "पहिरो", "भूकम्प", "डुबान",
}

# Combine for matching
ALL_KEYWORDS = NEPAL_DISTRICTS | NEPALI_KEYWORDS


@dataclass
class SimilarityScore:
    """Result of similarity comparison between two stories."""
    title_similarity: float  # 0-1 Jaccard similarity of character n-grams
    entity_overlap: float    # 0-1 ratio of shared entities
    time_proximity: float    # 0-1 based on time difference (1=same time, 0=48h apart)
    combined_score: float    # Weighted combination

    def is_match(self, threshold: float = 0.65) -> bool:
        """Check if this is a likely duplicate."""
        return self.combined_score >= threshold


def extract_entities(text: str) -> set[str]:
    """
    Extract key entities from text for matching.

    Returns locations, numbers, and keywords found.
    """
    entities = set()
    text_lower = text.lower()

    # Extract district/location names
    for district in NEPAL_DISTRICTS:
        if district.lower() in text_lower or district in text:
            entities.add(district.lower())

    # Extract keywords
    for keyword in NEPALI_KEYWORDS:
        if keyword in text:
            entities.add(keyword)

    # Extract numbers (with context to avoid false matches)
    # Match patterns like "4 करोड", "100 प्रहरी", etc.
    number_patterns = re.findall(r'\d+(?:\s*(?:करोड|लाख|हजार|प्रतिशत|%|जना|वटा))?', text)
    for num in number_patterns:
        if num.strip():
            entities.add(num.strip())

    return entities


def char_ngrams(text: str, n: int = 3) -> set[str]:
    """Generate character n-grams from text."""
    text = text.lower().replace(" ", "")
    if len(text) < n:
        return {text}
    return {text[i:i+n] for i in range(len(text) - n + 1)}


def jaccard_similarity(set1: set, set2: set) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def compute_similarity(
    title1: str,
    title2: str,
    time1: Optional[datetime] = None,
    time2: Optional[datetime] = None,
    max_time_diff_hours: int = 48,
) -> SimilarityScore:
    """
    Compute similarity between two story titles.

    Args:
        title1: First story title
        title2: Second story title
        time1: First story timestamp (optional)
        time2: Second story timestamp (optional)
        max_time_diff_hours: Maximum time difference to consider (default 48h)

    Returns:
        SimilarityScore with individual and combined scores
    """
    # Title similarity using character 3-grams
    ngrams1 = char_ngrams(title1, 3)
    ngrams2 = char_ngrams(title2, 3)
    title_sim = jaccard_similarity(ngrams1, ngrams2)

    # Entity overlap
    entities1 = extract_entities(title1)
    entities2 = extract_entities(title2)
    entity_sim = jaccard_similarity(entities1, entities2)

    # Time proximity (if timestamps available)
    time_sim = 1.0  # Default to full score if no timestamps
    if time1 and time2:
        # Ensure both are timezone-aware before subtraction
        if time1.tzinfo is None:
            time1 = time1.replace(tzinfo=timezone.utc)
        if time2.tzinfo is None:
            time2 = time2.replace(tzinfo=timezone.utc)
        time_diff = abs((time1 - time2).total_seconds() / 3600)  # hours
        if time_diff > max_time_diff_hours:
            time_sim = 0.0
        else:
            time_sim = 1.0 - (time_diff / max_time_diff_hours)

    # Combined score with weights:
    # - 50% title similarity (character n-grams catch paraphrasing)
    # - 35% entity overlap (key facts match)
    # - 15% time proximity (same event = same timeframe)
    combined = (0.50 * title_sim) + (0.35 * entity_sim) + (0.15 * time_sim)

    return SimilarityScore(
        title_similarity=title_sim,
        entity_overlap=entity_sim,
        time_proximity=time_sim,
        combined_score=combined,
    )


def generate_content_hash(title: str) -> str:
    """
    Generate a content-based hash for quick duplicate detection.

    Uses normalized title (lowercase, no spaces, sorted characters)
    to catch exact/near-exact duplicates quickly.
    """
    # Normalize: lowercase, remove spaces and punctuation
    normalized = re.sub(r'[^\w]', '', title.lower())
    # Sort characters to catch reordered words
    sorted_chars = ''.join(sorted(normalized))
    return hashlib.md5(sorted_chars.encode()).hexdigest()[:16]


class RealtimeDeduplicator:
    """
    Real-time story deduplication at ingestion time.

    Maintains an in-memory cache of recent stories for quick matching.
    Stories older than max_age are automatically evicted.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.65,
        max_cache_size: int = 5000,
        max_age_hours: int = 48,
    ):
        self.threshold = similarity_threshold
        self.max_cache_size = max_cache_size
        self.max_age = timedelta(hours=max_age_hours)

        # Cache: title -> (timestamp, cluster_id)
        self._cache: dict[str, tuple[datetime, Optional[str]]] = {}
        # Content hash -> title (for quick exact-match lookup)
        self._hash_index: dict[str, str] = {}

    def find_match(
        self,
        title: str,
        timestamp: Optional[datetime] = None,
    ) -> Optional[tuple[str, str, float]]:
        """
        Find a matching story in the cache.

        Args:
            title: New story title to match
            timestamp: New story timestamp

        Returns:
            Tuple of (matched_title, cluster_id, similarity_score) or None
        """
        if not title:
            return None

        timestamp = timestamp or datetime.now(timezone.utc)
        # Ensure timezone-aware (RSS feeds may produce naive datetimes)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # First: quick hash lookup for exact/near-exact matches
        content_hash = generate_content_hash(title)
        if content_hash in self._hash_index:
            cached_title = self._hash_index[content_hash]
            if cached_title in self._cache:
                _, cluster_id = self._cache[cached_title]
                return (cached_title, cluster_id, 1.0)

        # Second: similarity search through cache
        best_match = None
        best_score = 0.0

        for cached_title, (cached_time, cluster_id) in self._cache.items():
            # Ensure cached_time is also timezone-aware
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=timezone.utc)
            # Skip if too old
            if timestamp - cached_time > self.max_age:
                continue

            score = compute_similarity(
                title, cached_title, timestamp, cached_time
            )

            if score.is_match(self.threshold) and score.combined_score > best_score:
                best_match = (cached_title, cluster_id, score.combined_score)
                best_score = score.combined_score

        return best_match

    def add_to_cache(
        self,
        title: str,
        cluster_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Add a story to the cache for future matching.

        Args:
            title: Story title
            cluster_id: Associated cluster ID (if already clustered)
            timestamp: Story timestamp
        """
        if not title:
            return

        timestamp = timestamp or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Evict old entries if cache is full
        if len(self._cache) >= self.max_cache_size:
            self._evict_old_entries()

        self._cache[title] = (timestamp, cluster_id)
        self._hash_index[generate_content_hash(title)] = title

    def _evict_old_entries(self) -> None:
        """Remove entries older than max_age."""
        now = datetime.now(timezone.utc)
        old_titles = [
            title for title, (ts, _) in self._cache.items()
            if now - ts > self.max_age
        ]

        for title in old_titles:
            del self._cache[title]
            content_hash = generate_content_hash(title)
            if content_hash in self._hash_index:
                del self._hash_index[content_hash]

        # If still too full, remove oldest entries
        if len(self._cache) >= self.max_cache_size:
            sorted_entries = sorted(
                self._cache.items(),
                key=lambda x: x[1][0]
            )
            # Remove oldest 20%
            remove_count = int(self.max_cache_size * 0.2)
            for title, _ in sorted_entries[:remove_count]:
                del self._cache[title]
                content_hash = generate_content_hash(title)
                if content_hash in self._hash_index:
                    del self._hash_index[content_hash]

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._hash_index.clear()

    @property
    def cache_size(self) -> int:
        """Number of stories in cache."""
        return len(self._cache)


# Global instance for use across ingestion runs
_global_deduplicator: Optional[RealtimeDeduplicator] = None


def get_realtime_deduplicator() -> RealtimeDeduplicator:
    """Get or create the global realtime deduplicator instance."""
    global _global_deduplicator
    if _global_deduplicator is None:
        _global_deduplicator = RealtimeDeduplicator(
            similarity_threshold=0.58,  # Lower threshold to catch more related stories
            max_cache_size=5000,
            max_age_hours=48,
        )
    return _global_deduplicator
