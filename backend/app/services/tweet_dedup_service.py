"""Tweet deduplication & location extraction service.

Tier 1 (on_ingest): Free, instant — content hash dedup + keyword location extraction.
Tier 2 (run_batch): Haiku subprocess every 30 min — semantic clustering + LLM location extraction.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ingestion.realtime_dedup import (
    generate_content_hash,
    char_ngrams,
    jaccard_similarity,
    extract_entities,
    NEPAL_DISTRICTS,
)
from app.models.tweet import Tweet
from app.models.tweet_cluster import TweetCluster

logger = logging.getLogger(__name__)

# All 77 districts → 7 provinces
DISTRICT_TO_PROVINCE: dict[str, str] = {
    # Koshi Province (Province 1)
    "taplejung": "Koshi", "panchthar": "Koshi", "ilam": "Koshi",
    "jhapa": "Koshi", "morang": "Koshi", "sunsari": "Koshi",
    "dhankuta": "Koshi", "terhathum": "Koshi", "sankhuwasabha": "Koshi",
    "bhojpur": "Koshi", "solukhumbu": "Koshi", "okhaldhunga": "Koshi",
    "khotang": "Koshi", "udayapur": "Koshi",
    # Madhesh Province (Province 2)
    "saptari": "Madhesh", "siraha": "Madhesh", "dhanusa": "Madhesh",
    "mahottari": "Madhesh", "sarlahi": "Madhesh", "rautahat": "Madhesh",
    "bara": "Madhesh", "parsa": "Madhesh",
    # Bagmati Province (Province 3)
    "sindhuli": "Bagmati", "ramechhap": "Bagmati", "dolakha": "Bagmati",
    "sindhupalchok": "Bagmati", "kavrepalanchok": "Bagmati",
    "lalitpur": "Bagmati", "bhaktapur": "Bagmati", "kathmandu": "Bagmati",
    "nuwakot": "Bagmati", "rasuwa": "Bagmati", "dhading": "Bagmati",
    "makwanpur": "Bagmati", "chitwan": "Bagmati",
    # Gandaki Province (Province 4)
    "gorkha": "Gandaki", "lamjung": "Gandaki", "tanahu": "Gandaki",
    "syangja": "Gandaki", "kaski": "Gandaki", "manang": "Gandaki",
    "mustang": "Gandaki", "myagdi": "Gandaki", "parbat": "Gandaki",
    "baglung": "Gandaki", "nawalparasi": "Gandaki",
    # Lumbini Province (Province 5)
    "rupandehi": "Lumbini", "kapilvastu": "Lumbini",
    "arghakhanchi": "Lumbini", "gulmi": "Lumbini", "palpa": "Lumbini",
    "dang": "Lumbini", "pyuthan": "Lumbini", "rolpa": "Lumbini",
    "rukum": "Lumbini", "banke": "Lumbini", "bardiya": "Lumbini",
    # Karnali Province (Province 6)
    "surkhet": "Karnali", "dailekh": "Karnali", "jajarkot": "Karnali",
    "dolpa": "Karnali", "jumla": "Karnali", "kalikot": "Karnali",
    "mugu": "Karnali", "humla": "Karnali", "salyan": "Karnali",
    # Sudurpashchim Province (Province 7)
    "bajura": "Sudurpashchim", "bajhang": "Sudurpashchim",
    "achham": "Sudurpashchim", "doti": "Sudurpashchim",
    "kailali": "Sudurpashchim", "kanchanpur": "Sudurpashchim",
    "dadeldhura": "Sudurpashchim", "baitadi": "Sudurpashchim",
    "darchula": "Sudurpashchim",
}

# Reverse lookup: Nepali district name → English name
_NEPALI_TO_ENGLISH: dict[str, str] = {
    "काठमाडौं": "kathmandu", "ललितपुर": "lalitpur", "भक्तपुर": "bhaktapur",
    "काभ्रे": "kavrepalanchok", "सिन्धुली": "sindhuli", "रामेछाप": "ramechhap",
    "दोलखा": "dolakha", "सिन्धुपाल्चोक": "sindhupalchok", "नुवाकोट": "nuwakot",
    "रसुवा": "rasuwa", "धादिङ": "dhading", "मकवानपुर": "makwanpur",
    "चितवन": "chitwan", "गोरखा": "gorkha", "लमजुङ": "lamjung",
    "तनहुँ": "tanahu", "स्याङ्जा": "syangja", "कास्की": "kaski",
    "मनाङ": "manang", "मुस्ताङ": "mustang", "म्याग्दी": "myagdi",
    "बागलुङ": "baglung", "पर्वत": "parbat", "गुल्मी": "gulmi",
    "पाल्पा": "palpa", "नवलपरासी": "nawalparasi", "रुपन्देही": "rupandehi",
    "कपिलवस्तु": "kapilvastu", "अर्घाखाँची": "arghakhanchi",
    "प्युठान": "pyuthan", "रोल्पा": "rolpa", "रुकुम": "rukum",
    "सल्यान": "salyan", "दाङ": "dang", "बाँके": "banke",
    "बर्दिया": "bardiya", "सुर्खेत": "surkhet", "दैलेख": "dailekh",
    "जाजरकोट": "jajarkot", "डोल्पा": "dolpa", "जुम्ला": "jumla",
    "कालिकोट": "kalikot", "मुगु": "mugu", "हुम्ला": "humla",
    "बाजुरा": "bajura", "बझाङ": "bajhang", "अछाम": "achham",
    "डोटी": "doti", "कैलाली": "kailali", "कञ्चनपुर": "kanchanpur",
    "डडेलधुरा": "dadeldhura", "बैतडी": "baitadi", "दार्चुला": "darchula",
    "झापा": "jhapa", "मोरङ": "morang", "सुनसरी": "sunsari",
    "धनकुटा": "dhankuta", "तेह्रथुम": "terhathum", "भोजपुर": "bhojpur",
    "सोलुखुम्बु": "solukhumbu", "ओखलढुङ्गा": "okhaldhunga",
    "खोटाङ": "khotang", "उदयपुर": "udayapur", "सप्तरी": "saptari",
    "सिराहा": "siraha", "धनुषा": "dhanusa", "महोत्तरी": "mahottari",
    "सर्लाही": "sarlahi", "रौतहट": "rautahat", "बारा": "bara",
    "पर्सा": "parsa",
}

# Severity ranking for determining cluster severity
_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _extract_districts(text: str) -> list[str]:
    """Extract Nepal district names from text using keyword matching."""
    entities = extract_entities(text)
    districts = []
    for entity in entities:
        e_lower = entity.lower()
        if e_lower in DISTRICT_TO_PROVINCE:
            districts.append(e_lower)
        elif entity in _NEPALI_TO_ENGLISH:
            districts.append(_NEPALI_TO_ENGLISH[entity])
    return list(set(districts))


def _districts_to_provinces(districts: list[str]) -> list[str]:
    """Map district names to unique province names."""
    provinces = set()
    for d in districts:
        prov = DISTRICT_TO_PROVINCE.get(d.lower())
        if prov:
            provinces.add(prov)
    return sorted(provinces)


class TweetDedupService:
    """Handles tweet deduplication and location extraction."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Tier 1: On-Ingest (free, instant) ───────────────────────

    async def on_ingest(self, tweet: Tweet) -> None:
        """Run immediately after a tweet is stored. Zero LLM cost.

        1. Compute content_hash for exact-match dedup.
        2. If hash matches an existing tweet within 48h, assign same cluster.
        3. Extract districts/provinces via keyword matching.
        """
        if not tweet.text:
            return

        # 1. Content hash
        content_hash = generate_content_hash(tweet.text)
        tweet.content_hash = content_hash

        # 2. Check for hash-based duplicate in last 48h
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        result = await self.db.execute(
            select(Tweet)
            .where(
                Tweet.content_hash == content_hash,
                Tweet.id != tweet.id,
                Tweet.fetched_at >= cutoff,
            )
            .order_by(Tweet.fetched_at)
            .limit(1)
        )
        match = result.scalar_one_or_none()

        if match and match.tweet_cluster_id:
            # Join existing cluster
            tweet.tweet_cluster_id = match.tweet_cluster_id
            # Update cluster stats
            await self.db.execute(
                update(TweetCluster)
                .where(TweetCluster.id == match.tweet_cluster_id)
                .values(
                    tweet_count=TweetCluster.tweet_count + 1,
                    last_seen=datetime.now(timezone.utc),
                )
            )

        # 3. Keyword-based location extraction
        districts = _extract_districts(tweet.text)
        if districts:
            tweet.districts = districts
            tweet.provinces = _districts_to_provinces(districts)

        await self.db.commit()

    # ─── Tier 2: Batch (Haiku, every 30 min) ─────────────────────

    async def run_batch(self) -> dict:
        """Process ungrouped tweets from the last 60 minutes.

        1. Pre-filter: group by content_hash, then char-ngram similarity.
        2. Send remaining ungrouped tweets to Haiku for semantic clustering + location extraction.
        3. Create/update TweetCluster records.

        Returns stats dict.
        """
        stats = {"processed": 0, "clusters_created": 0, "locations_extracted": 0, "haiku_called": False}
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)

        # Load ungrouped tweets
        result = await self.db.execute(
            select(Tweet)
            .where(
                Tweet.tweet_cluster_id.is_(None),
                Tweet.fetched_at >= cutoff,
            )
            .order_by(Tweet.fetched_at)
        )
        ungrouped = list(result.scalars().all())
        stats["processed"] = len(ungrouped)

        if not ungrouped:
            logger.info("Tweet dedup batch: no ungrouped tweets")
            return stats

        logger.info(f"Tweet dedup batch: {len(ungrouped)} ungrouped tweets to process")

        # ── Step 1: Pre-filter with content_hash ──
        hash_groups: dict[str, list[Tweet]] = {}
        no_hash_match: list[Tweet] = []

        for tweet in ungrouped:
            h = tweet.content_hash or generate_content_hash(tweet.text)
            if h in hash_groups:
                hash_groups[h].append(tweet)
            else:
                hash_groups[h] = [tweet]

        # Groups with >1 tweet are exact duplicates → cluster them
        still_ungrouped: list[Tweet] = []
        for h, group in hash_groups.items():
            if len(group) > 1:
                cluster = await self._create_cluster(group)
                stats["clusters_created"] += 1
            else:
                still_ungrouped.append(group[0])

        # ── Step 2: Pre-filter with char-ngram similarity ──
        if len(still_ungrouped) > 1:
            still_ungrouped, sim_clusters = self._similarity_prefilter(still_ungrouped)
            for group in sim_clusters:
                cluster = await self._create_cluster(group)
                stats["clusters_created"] += 1

        # ── Step 3: Haiku batch for remaining ungrouped ──
        if len(still_ungrouped) >= 2:
            try:
                haiku_clusters, location_updates = await self._haiku_batch(still_ungrouped)
                stats["haiku_called"] = True

                for group in haiku_clusters:
                    if len(group) > 1:
                        cluster = await self._create_cluster(group)
                        stats["clusters_created"] += 1

                # Apply location updates from Haiku
                for tweet_id, locs in location_updates.items():
                    tweet = next((t for t in still_ungrouped if str(t.id) == tweet_id), None)
                    if tweet and locs:
                        # Merge with existing keyword-extracted districts
                        existing = set(tweet.districts or [])
                        new_districts = set()
                        for loc in locs:
                            loc_lower = loc.lower()
                            if loc_lower in DISTRICT_TO_PROVINCE:
                                new_districts.add(loc_lower)
                        merged = list(existing | new_districts)
                        if merged:
                            tweet.districts = merged
                            tweet.provinces = _districts_to_provinces(merged)
                            stats["locations_extracted"] += 1

            except Exception as e:
                logger.error(f"Haiku batch failed: {e}")

        # Give standalone tweets their own single-tweet cluster so they show cluster_size=1
        for tweet in still_ungrouped:
            if tweet.tweet_cluster_id is None:
                now = datetime.now(timezone.utc)
                cluster = TweetCluster(
                    id=uuid4(),
                    representative_tweet_id=tweet.id,
                    tweet_count=1,
                    category=tweet.category,
                    severity=tweet.severity,
                    districts=tweet.districts or [],
                    first_seen=tweet.tweeted_at or now,
                    last_seen=tweet.tweeted_at or now,
                )
                self.db.add(cluster)
                tweet.tweet_cluster_id = cluster.id

        await self.db.commit()

        logger.info(
            f"Tweet dedup batch: processed {stats['processed']} tweets, "
            f"created {stats['clusters_created']} clusters, "
            f"extracted locations for {stats['locations_extracted']}"
        )
        return stats

    def _similarity_prefilter(
        self, tweets: list[Tweet], threshold: float = 0.60
    ) -> tuple[list[Tweet], list[list[Tweet]]]:
        """Group tweets by char-ngram Jaccard similarity.

        Returns (remaining_ungrouped, list_of_similar_groups).
        """
        n = len(tweets)
        ngram_cache = [char_ngrams(t.text, 3) for t in tweets]
        assigned = [False] * n
        groups: list[list[Tweet]] = []

        for i in range(n):
            if assigned[i]:
                continue
            group = [tweets[i]]
            assigned[i] = True
            for j in range(i + 1, n):
                if assigned[j]:
                    continue
                sim = jaccard_similarity(ngram_cache[i], ngram_cache[j])
                if sim >= threshold:
                    group.append(tweets[j])
                    assigned[j] = True
            if len(group) > 1:
                groups.append(group)

        remaining = [tweets[i] for i in range(n) if not assigned[i]]
        return remaining, groups

    async def _haiku_batch(
        self, tweets: list[Tweet]
    ) -> tuple[list[list[Tweet]], dict[str, list[str]]]:
        """Call Haiku to cluster tweets and extract locations.

        Returns (list_of_tweet_groups, {tweet_id: [location_names]}).
        """
        # Claude runner excluded from skeleton - LLM clustering requires API key
        raise NotImplementedError("Haiku batch clustering requires Claude API (excluded from skeleton)")

        result: dict = {}

        # Parse clusters
        raw_clusters = result.get("clusters", [])
        tweet_groups: list[list[Tweet]] = []
        for group_indices in raw_clusters:
            group = []
            for idx in group_indices:
                if isinstance(idx, int) and idx in id_map:
                    group.append(id_map[idx])
            if group:
                tweet_groups.append(group)

        # Parse locations
        raw_locations = result.get("locations", {})
        location_updates: dict[str, list[str]] = {}
        for idx_str, locs in raw_locations.items():
            try:
                idx = int(idx_str)
                if idx in id_map:
                    location_updates[str(id_map[idx].id)] = locs if isinstance(locs, list) else []
            except (ValueError, TypeError):
                continue

        return tweet_groups, location_updates

    async def _create_cluster(self, tweets: list[Tweet]) -> TweetCluster:
        """Create a TweetCluster from a list of tweets and assign them."""
        now = datetime.now(timezone.utc)

        # Pick representative: highest engagement
        representative = max(
            tweets,
            key=lambda t: (t.retweet_count or 0) + (t.like_count or 0) + (t.reply_count or 0),
        )

        # Aggregate districts across all tweets
        all_districts: set[str] = set()
        for t in tweets:
            if t.districts:
                all_districts.update(t.districts)

        # Determine highest severity
        highest_severity = None
        highest_rank = 0
        for t in tweets:
            if t.severity:
                rank = _SEVERITY_RANK.get(t.severity.lower(), 0)
                if rank > highest_rank:
                    highest_rank = rank
                    highest_severity = t.severity

        # Timestamps
        tweet_times = [t.tweeted_at or t.fetched_at for t in tweets]
        first_seen = min(tweet_times) if tweet_times else now
        last_seen = max(tweet_times) if tweet_times else now

        cluster = TweetCluster(
            id=uuid4(),
            representative_tweet_id=representative.id,
            tweet_count=len(tweets),
            category=representative.category,
            severity=highest_severity,
            districts=sorted(all_districts),
            first_seen=first_seen,
            last_seen=last_seen,
        )
        self.db.add(cluster)

        # Assign all tweets to this cluster
        for t in tweets:
            t.tweet_cluster_id = cluster.id

        return cluster
