"""
Parliament Linker Service.

Links parliament MPs to election candidates using fuzzy name matching.
Considers multiple signals:
- Nepali name match (highest weight)
- English name match
- Party match
- Constituency match
"""

import logging
import re
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.parliament import MPPerformanceRepository
from app.repositories.election import CandidateRepository, ConstituencyRepository

logger = logging.getLogger(__name__)

# Party name aliases for matching
PARTY_ALIASES = {
    'CPN-UML': [
        'uml', 'cpn-uml', 'cpn uml', 'communist party of nepal (unified marxist-leninist)',
        'nepal communist party (uml)', 'nepal communist party uml',
        'नेकपा (एमाले)', 'एमाले', 'नेकपा एमाले',
        'नेपाल कम्युनिष्ट पार्टी (एमाले)',
    ],
    'Nepali Congress': [
        'nc', 'nepali congress', 'congress', 'नेपाली कांग्रेस', 'कांग्रेस',
    ],
    'CPN-Maoist Centre': [
        'maoist', 'cpn-mc', 'cpn maoist', 'maoist centre', 'maoist center',
        'नेकपा माओवादी केन्द्र', 'माओवादी', 'माओवादी केन्द्र',
    ],
    'Rastriya Swatantra Party': [
        'rsp', 'rastriya swatantra', 'swatantra party',
        'राष्ट्रिय स्वतन्त्र पार्टी', 'रास्वपा',
    ],
    'Rashtriya Prajatantra Party': [
        'rpp', 'rashtriya prajatantra', 'prajatantra',
        'राष्ट्रिय प्रजातन्त्र पार्टी', 'राप्रपा',
    ],
    'Janata Samajwadi Party': [
        'jsp', 'janata samajwadi', 'samajwadi',
        'जनता समाजवादी पार्टी', 'जसपा',
    ],
    'Loktantrik Samajwadi Party': [
        'lsp', 'loktantrik samajwadi',
        'लोकतान्त्रिक समाजवादी पार्टी', 'लोसपा',
    ],
    'Janamat Party': [
        'janamat', 'जनमत पार्टी',
    ],
    'Nagarik Unmukti Party': [
        'nup', 'nagarik unmukti',
        'नागरिक उन्मुक्ति पार्टी',
    ],
    'Independent': [
        'independent', 'स्वतन्त्र', 'निर्दलीय',
    ],
}

# Honorific prefixes to remove
HONORIFICS = [
    'hon.', 'hon', 'dr.', 'dr', 'prof.', 'prof', 'mr.', 'mr',
    'mrs.', 'mrs', 'ms.', 'ms', 'shri', 'shree', 'श्री', 'माननीय',
    'pm', 'pm.', 'k.p.', 'k.p',  # PM and common abbreviations
]


class ParliamentLinker:
    """
    Links parliament MPs to election candidates by name matching.

    Uses fuzzy matching with multiple signals:
    - Nepali name (40% weight)
    - English name (30% weight)
    - Party match (15% weight)
    - Constituency match (15% weight)

    Only links with confidence >= 0.85 threshold.
    """

    def __init__(
        self,
        db: AsyncSession,
        confidence_threshold: float = 0.85,
    ):
        """
        Initialize the linker.

        Args:
            db: Database session
            confidence_threshold: Minimum confidence for linking (0-1)
        """
        self.db = db
        self.confidence_threshold = confidence_threshold
        self.mp_repo = MPPerformanceRepository(db)
        self.candidate_repo = CandidateRepository(db)
        self.constituency_repo = ConstituencyRepository(db)

        # Cache for candidates
        self._candidates_cache: Optional[List] = None

    async def link_all_members(self, election_id: Optional[UUID] = None) -> dict:
        """
        Run matching for all unlinked MPs.

        Args:
            election_id: Optional specific election to match against

        Returns:
            Dict with counts of linked, unlinked, and failed MPs
        """
        # Get all unlinked MPs
        mps, _ = await self.mp_repo.list_mps(is_current=True, per_page=500)
        unlinked_mps = [mp for mp in mps if not mp.linked_candidate_id]

        logger.info(f"Found {len(unlinked_mps)} unlinked MPs to process")

        # Load candidates for matching
        candidates = await self._load_candidates(election_id)
        logger.info(f"Loaded {len(candidates)} candidates for matching")

        results = {
            'linked': 0,
            'unlinked': 0,
            'failed': 0,
            'details': [],
        }

        for mp in unlinked_mps:
            try:
                match = self._find_best_match(mp, candidates)
                if match:
                    candidate_id, confidence = match
                    await self.mp_repo.update_link(mp.id, candidate_id, confidence)
                    results['linked'] += 1
                    results['details'].append({
                        'mp_id': str(mp.id),
                        'mp_name': mp.name_en,
                        'candidate_id': str(candidate_id),
                        'confidence': confidence,
                    })
                else:
                    results['unlinked'] += 1
            except Exception as e:
                logger.error(f"Error linking MP {mp.name_en}: {e}")
                results['failed'] += 1

        logger.info(
            f"Linking complete: {results['linked']} linked, "
            f"{results['unlinked']} unlinked, {results['failed']} failed"
        )
        return results

    async def link_single_mp(
        self,
        mp_id: UUID,
        election_id: Optional[UUID] = None,
    ) -> Optional[Tuple[UUID, float]]:
        """
        Attempt to link a single MP to a candidate.

        Args:
            mp_id: MP UUID to link
            election_id: Optional specific election to match against

        Returns:
            Tuple of (candidate_id, confidence) or None
        """
        mp = await self.mp_repo.get_by_id(mp_id)
        if not mp:
            return None

        candidates = await self._load_candidates(election_id)
        match = self._find_best_match(mp, candidates)

        if match:
            candidate_id, confidence = match
            await self.mp_repo.update_link(mp_id, candidate_id, confidence)
            return match

        return None

    async def _load_candidates(self, election_id: Optional[UUID] = None) -> List:
        """Load candidates for matching (with caching)."""
        if self._candidates_cache is not None:
            return self._candidates_cache

        # Get winning candidates (most likely to be MPs)
        if election_id:
            candidates = await self.candidate_repo.list_winners_by_election(election_id)
        else:
            # Get all winning candidates from recent elections
            # For now, get from most recent election (2082)
            from app.repositories.election import ElectionRepository
            election_repo = ElectionRepository(self.db)
            elections = await election_repo.list_elections()

            candidates = []
            for election in elections[:2]:  # Last 2 elections
                winners = await self.candidate_repo.list_winners_by_election(election.id)
                for winner in winners:
                    winner._election_year = election.year_bs
                    candidates.append(winner)

        self._candidates_cache = candidates
        return candidates

    def _find_best_match(self, mp, candidates) -> Optional[Tuple[UUID, float]]:
        """
        Find best matching candidate for an MP.

        Args:
            mp: MPPerformance object
            candidates: List of Candidate objects

        Returns:
            Tuple of (candidate_id, confidence) or None
        """
        best_match = None
        best_score = 0.0

        for candidate in candidates:
            score = self._calculate_match_score(mp, candidate)
            if score > best_score and score >= self.confidence_threshold:
                best_score = score
                best_match = (candidate.id, score)

        return best_match

    def _calculate_match_score(self, mp, candidate) -> float:
        """
        Calculate matching score between MP and candidate.

        Weights:
        - Nepali name: 40%
        - English/alternate name: 30%
        - Party: 15%
        - Constituency: 15%

        Args:
            mp: MPPerformance object
            candidate: Candidate object

        Returns:
            Match score (0-1)
        """
        scores = []
        weights = []

        # Nepali name match (40%)
        # Note: candidate.name_en might actually contain Nepali text, so check both
        best_ne_score = 0.0
        if mp.name_ne:
            for cand_name in [candidate.name_ne, candidate.name_en]:
                if cand_name and self._is_nepali(cand_name):
                    score = self._fuzzy_nepali_match(mp.name_ne, cand_name)
                    best_ne_score = max(best_ne_score, score)

        if best_ne_score > 0:
            scores.append(best_ne_score * 0.4)
            weights.append(0.4)

        # English/alternate name match (30%)
        # Try to find the best match between available name fields
        best_en_score = 0.0
        mp_names = [mp.name_en] if mp.name_en else []
        cand_names = [candidate.name_en, candidate.name_ne] if candidate.name_en else []

        for mp_name in mp_names:
            mp_normalized = self._normalize_name(mp_name)
            for cand_name in cand_names:
                if cand_name:
                    cand_normalized = self._normalize_name(cand_name)
                    score = self._fuzzy_match(mp_normalized, cand_normalized)
                    best_en_score = max(best_en_score, score)

        if best_en_score > 0:
            scores.append(best_en_score * 0.3)
            weights.append(0.3)

        # Party match (15%)
        if mp.party and candidate.party:
            party_score = 1.0 if self._parties_match(mp.party, candidate.party) else 0.0
            scores.append(party_score * 0.15)
            weights.append(0.15)

        # Constituency match (15%)
        if mp.constituency:
            const_score = 1.0 if self._constituencies_match(mp.constituency, candidate) else 0.0
            scores.append(const_score * 0.15)
            weights.append(0.15)

        # Normalize by weights actually used
        if not weights:
            return 0.0

        total_weight = sum(weights)
        return sum(scores) / total_weight if total_weight > 0 else 0.0

    def _is_nepali(self, text: str) -> bool:
        """Check if text contains Nepali characters."""
        if not text:
            return False
        # Devanagari range: \u0900-\u097F
        return any('\u0900' <= c <= '\u097F' for c in text)

    def _fuzzy_nepali_match(self, str1: str, str2: str) -> float:
        """
        Calculate fuzzy match for Nepali strings.

        Handles variations like:
        - "के.पी शर्मा ओली" vs "के.पी शर्मा (ओली)"
        - Parentheses, dots, spaces
        """
        if not str1 or not str2:
            return 0.0

        # Normalize: remove parentheses, extra spaces, dots
        def normalize_nepali(s):
            s = s.replace('(', ' ').replace(')', ' ')
            s = s.replace('.', ' ').replace('।', ' ')
            s = ' '.join(s.split())
            return s.strip()

        n1 = normalize_nepali(str1)
        n2 = normalize_nepali(str2)

        if n1 == n2:
            return 1.0

        # Token-based matching
        tokens1 = set(n1.split())
        tokens2 = set(n2.split())

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        # Jaccard similarity
        return len(intersection) / len(union)

    def _normalize_name(self, name: str) -> str:
        """
        Normalize name for matching.

        Removes honorifics, extra whitespace, and normalizes case.
        """
        if not name:
            return ""

        name_lower = name.lower().strip()

        # Remove honorifics
        for honorific in HONORIFICS:
            if name_lower.startswith(honorific.lower()):
                name_lower = name_lower[len(honorific):].strip()

        # Remove extra whitespace
        name_lower = " ".join(name_lower.split())

        return name_lower

    def _fuzzy_match(self, str1: str, str2: str) -> float:
        """
        Calculate fuzzy match score between two strings.

        Uses simple character-level similarity for robustness.
        Returns score between 0 and 1.
        """
        if not str1 or not str2:
            return 0.0

        # Normalize both strings
        s1 = self._normalize_name(str1)
        s2 = self._normalize_name(str2)

        if s1 == s2:
            return 1.0

        # Calculate Levenshtein-like similarity
        # Using simple token overlap for efficiency
        tokens1 = set(s1.split())
        tokens2 = set(s2.split())

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        # Jaccard similarity
        jaccard = len(intersection) / len(union)

        # Character-level similarity (for handling minor typos)
        chars1 = set(s1.replace(" ", ""))
        chars2 = set(s2.replace(" ", ""))
        char_intersection = chars1 & chars2
        char_union = chars1 | chars2
        char_sim = len(char_intersection) / len(char_union) if char_union else 0

        # Combine both scores
        return 0.6 * jaccard + 0.4 * char_sim

    def _parties_match(self, party1: str, party2: str) -> bool:
        """
        Check if two party names refer to the same party.

        Uses alias matching to handle different representations.
        """
        if not party1 or not party2:
            return False

        p1 = party1.lower().strip()
        p2 = party2.lower().strip()

        # Direct match
        if p1 == p2:
            return True

        # Check if both belong to same canonical party
        canonical1 = self._get_canonical_party(p1)
        canonical2 = self._get_canonical_party(p2)

        if canonical1 and canonical2:
            return canonical1 == canonical2

        # Fuzzy match for unrecognized parties
        return self._fuzzy_match(p1, p2) > 0.8

    def _get_canonical_party(self, party: str) -> Optional[str]:
        """Get canonical party name from aliases."""
        party_lower = party.lower()
        for canonical, aliases in PARTY_ALIASES.items():
            if party_lower in [a.lower() for a in aliases]:
                return canonical
            if canonical.lower() in party_lower:
                return canonical
        return None

    def _constituencies_match(self, mp_constituency: str, candidate) -> bool:
        """
        Check if MP constituency matches candidate's constituency.

        Handles different formats like:
        - "Kathmandu-1"
        - "Kathmandu District, Constituency 1"
        - "काठमाडौं-१"
        """
        if not mp_constituency:
            return False

        # Get constituency code from candidate
        constituency_code = None
        if hasattr(candidate, 'constituency_code'):
            constituency_code = candidate.constituency_code
        elif hasattr(candidate, 'constituency') and candidate.constituency:
            constituency_code = getattr(candidate.constituency, 'constituency_code', None)

        if not constituency_code:
            return False

        # Normalize both strings
        const_lower = mp_constituency.lower().strip()
        code_lower = constituency_code.lower().strip()

        # Direct match
        if const_lower == code_lower:
            return True

        # Try to match district and number
        # Pattern: "district-number" or "district number"
        match = re.search(r'([a-z]+)[- ]?(\d+)', const_lower)
        if match:
            district = match.group(1)
            number = match.group(2)
            return district in code_lower and number in code_lower

        return False

    async def find_matches_for_name(
        self,
        name_en: str,
        name_ne: Optional[str] = None,
        party: Optional[str] = None,
        top_n: int = 5,
    ) -> List[Tuple[dict, float]]:
        """
        Find top matching candidates for a given name.

        Useful for debugging and manual verification.

        Args:
            name_en: English name to match
            name_ne: Optional Nepali name
            party: Optional party name
            top_n: Number of top matches to return

        Returns:
            List of (candidate_dict, confidence) tuples
        """
        candidates = await self._load_candidates()

        # Create a mock MP object for matching
        class MockMP:
            pass

        mock_mp = MockMP()
        mock_mp.name_en = name_en
        mock_mp.name_ne = name_ne
        mock_mp.party = party
        mock_mp.constituency = None

        matches = []
        for candidate in candidates:
            score = self._calculate_match_score(mock_mp, candidate)
            if score > 0.3:  # Low threshold for debugging
                matches.append((
                    {
                        'id': str(candidate.id),
                        'name_en': candidate.name_en,
                        'name_ne': candidate.name_ne,
                        'party': candidate.party,
                        'election_year': getattr(candidate, '_election_year', None),
                    },
                    score,
                ))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:top_n]


    async def match_video_speakers(
        self,
        chamber: str = 'hor',
        max_pages: int = 5,
        max_sessions: int = 50,
    ) -> dict:
        """
        Match video speakers to MPs and update speeches_count.

        Scrapes parliament video archives, extracts speaker names,
        and uses fuzzy matching to link them to MPs.

        Args:
            chamber: 'hor' or 'na'
            max_pages: Max pages of session list to scrape
            max_sessions: Max session detail pages to fetch

        Returns:
            Dict with match statistics
        """
        from app.ingestion.parliament_scraper import ParliamentScraper

        logger.info(f"Starting video speaker matching for {chamber}...")

        # Scrape videos
        async with ParliamentScraper() as scraper:
            videos = await scraper.scrape_videos(chamber, max_pages, max_sessions)

        logger.info(f"Scraped {len(videos)} video records")

        # Get all MPs for matching
        mps, _ = await self.mp_repo.list_mps(chamber=chamber, is_current=True, per_page=500)
        logger.info(f"Loaded {len(mps)} MPs for matching")

        # Count speeches per speaker name
        speech_counts = {}
        for video in videos:
            if video.speaker_name_normalized:
                name = video.speaker_name_normalized
                speech_counts[name] = speech_counts.get(name, 0) + 1

        logger.info(f"Found {len(speech_counts)} unique speaker names")

        # Match each speaker to an MP
        mp_speeches = {}  # mp_id -> count
        matched_speakers = []
        unmatched_speakers = []

        for speaker_name, count in speech_counts.items():
            mp_match = self._find_mp_for_speaker(speaker_name, mps)
            if mp_match:
                mp_id, confidence = mp_match
                mp_speeches[mp_id] = mp_speeches.get(mp_id, 0) + count
                matched_speakers.append({
                    'speaker': speaker_name,
                    'mp_id': str(mp_id),
                    'mp_name': next((m.name_en for m in mps if m.id == mp_id), None),
                    'count': count,
                    'confidence': confidence,
                })
            else:
                unmatched_speakers.append({
                    'speaker': speaker_name,
                    'count': count,
                })

        logger.info(f"Matched {len(matched_speakers)} speakers, {len(unmatched_speakers)} unmatched")

        # Update speeches_count for each MP
        updated_count = 0
        for mp_id, count in mp_speeches.items():
            try:
                await self.mp_repo.update_speeches_count(mp_id, count)
                updated_count += 1
            except Exception as e:
                logger.error(f"Error updating speeches for MP {mp_id}: {e}")

        return {
            'total_videos': len(videos),
            'unique_speakers': len(speech_counts),
            'matched_speakers': len(matched_speakers),
            'unmatched_speakers': len(unmatched_speakers),
            'mps_updated': updated_count,
            'matched_details': matched_speakers[:20],  # Top 20
            'unmatched_details': unmatched_speakers[:20],  # Top 20
        }

    def _find_mp_for_speaker(
        self,
        speaker_name: str,
        mps: List,
        threshold: float = 0.65,  # Lower threshold for speaker matching
    ) -> Optional[Tuple[UUID, float]]:
        """
        Find best matching MP for a speaker name.

        Uses fuzzy matching on English names.
        """
        if not speaker_name:
            return None

        best_match = None
        best_score = 0.0

        speaker_normalized = self._normalize_name(speaker_name)

        for mp in mps:
            # Match against English name
            mp_normalized = self._normalize_name(mp.name_en)
            score = self._fuzzy_match(speaker_normalized, mp_normalized)

            # Also try Nepali name if available
            if mp.name_ne:
                # Check if speaker name could be Nepali
                ne_score = self._fuzzy_nepali_match(speaker_name, mp.name_ne)
                score = max(score, ne_score)

            if score > best_score and score >= threshold:
                best_score = score
                best_match = (mp.id, score)

        return best_match


# ============ Service Functions ============

async def link_all_mps(db: AsyncSession) -> dict:
    """
    Link all unlinked MPs to election candidates.

    For use in scheduler jobs.
    """
    linker = ParliamentLinker(db)
    return await linker.link_all_members()


async def link_mp_to_candidate(
    db: AsyncSession,
    mp_id: UUID,
    election_id: Optional[UUID] = None,
) -> Optional[Tuple[UUID, float]]:
    """
    Link a single MP to a candidate.

    For use in API endpoints.
    """
    linker = ParliamentLinker(db)
    return await linker.link_single_mp(mp_id, election_id)


async def match_video_speakers(
    db: AsyncSession,
    chamber: str = 'hor',
    max_pages: int = 5,
    max_sessions: int = 50,
) -> dict:
    """
    Match video archive speakers to MPs and update speeches_count.

    Scrapes parliament video archives, extracts speaker names,
    and uses fuzzy matching to link them to MPs.

    For use in scheduler jobs or manual triggering.
    """
    linker = ParliamentLinker(db)
    return await linker.match_video_speakers(chamber, max_pages, max_sessions)
