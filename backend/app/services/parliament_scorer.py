"""
Parliament Performance Scorer.

Calculates MP Performance Index with DYNAMIC weighting.
Categories that have no data get their weight redistributed
to categories that do have data, so scores are always meaningful.

Base Weights (when all data available):
- Legislative Productivity: 30%
- Parliamentary Engagement (speeches): 25%
- Committee Work: 25%
- Participation (attendance): 15%
- Accountability (questions): 5%

When a category has no data system-wide, its weight is redistributed
proportionally to the categories that DO have data. This prevents
scores from being capped at 50/100 when attendance/questions tables
are empty.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.parliament import (
    MPPerformanceRepository,
    BillRepository,
    CommitteeRepository,
    QuestionRepository,
    AttendanceRepository,
)

logger = logging.getLogger(__name__)


# Category keys used throughout the scorer
CAT_LEGISLATIVE = "legislative"
CAT_ENGAGEMENT = "engagement"
CAT_COMMITTEE = "committee"
CAT_PARTICIPATION = "participation"
CAT_ACCOUNTABILITY = "accountability"


@dataclass
class ScoreWeights:
    """Base weights -- redistributed dynamically based on data availability.

    When all five categories have data, these weights apply directly.
    When a category has NO data for ANY MP system-wide, its weight is
    redistributed proportionally to the categories that do.
    """
    legislative: float = 0.30
    engagement: float = 0.25
    committee: float = 0.25
    participation: float = 0.15
    accountability: float = 0.05


class PerformanceScorer:
    """
    Calculate MP performance scores with dynamic weighting and percentile ranking.

    Scoring is done within peer groups for fair comparison:
    - FPTP MPs by province
    - PR MPs by province
    - Ministers (separate group)

    Five internal categories are calculated, then mapped back to the four
    database columns for storage (engagement + participation -> participation_score).
    """

    def __init__(
        self,
        db: AsyncSession,
        weights: Optional[ScoreWeights] = None,
    ):
        self.db = db
        self.weights = weights or ScoreWeights()

        self.mp_repo = MPPerformanceRepository(db)
        self.bill_repo = BillRepository(db)
        self.committee_repo = CommitteeRepository(db)
        self.question_repo = QuestionRepository(db)
        self.attendance_repo = AttendanceRepository(db)

        # Effective weights after dynamic redistribution.
        # Set by calculate_all_scores() before individual MP scoring.
        self._effective_weights: Dict[str, float] = {
            CAT_LEGISLATIVE: self.weights.legislative,
            CAT_ENGAGEMENT: self.weights.engagement,
            CAT_COMMITTEE: self.weights.committee,
            CAT_PARTICIPATION: self.weights.participation,
            CAT_ACCOUNTABILITY: self.weights.accountability,
        }

        # Track which categories have system-wide data
        self._data_availability: Dict[str, bool] = {}

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def calculate_all_scores(self) -> dict:
        """
        Recalculate scores for all current MPs using dynamic weighting.

        Steps:
        1. Pre-scan: determine which categories have data system-wide
        2. Build effective weights (redistribute from empty categories)
        3. Load data + calculate raw category scores per MP
        4. Compute weighted composite score
        5. Assign percentiles within peer groups
        6. Bulk save

        Returns:
            Dict with counts and statistics
        """
        logger.info("Starting score calculation for all MPs")

        # Get all current MPs
        all_mps = await self.mp_repo.list_all_current()
        logger.info(f"Found {len(all_mps)} current MPs to score")

        if not all_mps:
            return {
                "total_scored": 0,
                "peer_groups": 0,
                "avg_score": 0,
                "top_performer": None,
                "effective_weights": self._effective_weights,
                "data_availability": {},
            }

        # ----- Step 1: Pre-scan data availability system-wide -----
        has_bills = await self.bill_repo.has_any_data()
        has_speeches = any(mp.speeches_count > 0 for mp in all_mps)
        has_committees = await self.committee_repo.has_any_data()
        has_attendance = await self.attendance_repo.has_any_data()
        has_questions = await self.question_repo.has_any_data()

        self._data_availability = {
            CAT_LEGISLATIVE: has_bills,
            CAT_ENGAGEMENT: has_speeches,
            CAT_COMMITTEE: has_committees,
            CAT_PARTICIPATION: has_attendance,
            CAT_ACCOUNTABILITY: has_questions,
        }

        logger.info(f"Data availability: {self._data_availability}")

        # ----- Step 2: Build effective weights -----
        self._build_effective_weights()
        logger.info(f"Effective weights: {self._effective_weights}")

        # ----- Step 3 + 4: Score each MP -----
        for mp in all_mps:
            await self._calculate_mp_scores(mp)

        # ----- Step 5: Percentiles within peer groups -----
        peer_groups = self._group_by_peers(all_mps)
        for peer_group, mps in peer_groups.items():
            self._assign_percentiles(mps, peer_group)

        # ----- Step 6: Bulk save -----
        updates = [
            (mp.id, self._extract_scores(mp))
            for mp in all_mps
        ]
        await self.mp_repo.bulk_update_scores(updates)

        # Return statistics
        avg = sum(mp.performance_score for mp in all_mps) / len(all_mps)
        top = max(all_mps, key=lambda x: x.performance_score)

        return {
            "total_scored": len(all_mps),
            "peer_groups": len(peer_groups),
            "avg_score": round(avg, 2),
            "top_performer": top.name_en,
            "top_score": round(top.performance_score, 2),
            "effective_weights": {k: round(v, 4) for k, v in self._effective_weights.items()},
            "data_availability": self._data_availability,
        }

    async def calculate_mp_score(self, mp_id: UUID) -> Optional[dict]:
        """
        Calculate score for a single MP.

        Uses system-wide data availability to set effective weights,
        then scores the individual MP.

        Args:
            mp_id: MP UUID

        Returns:
            Dict with scores or None if MP not found
        """
        mp = await self.mp_repo.get_by_id(mp_id)
        if not mp:
            return None

        # Determine data availability system-wide (needed for single-MP scoring)
        all_mps = await self.mp_repo.list_all_current()

        has_bills = await self.bill_repo.has_any_data()
        has_speeches = any(m.speeches_count > 0 for m in all_mps)
        has_committees = await self.committee_repo.has_any_data()
        has_attendance = await self.attendance_repo.has_any_data()
        has_questions = await self.question_repo.has_any_data()

        self._data_availability = {
            CAT_LEGISLATIVE: has_bills,
            CAT_ENGAGEMENT: has_speeches,
            CAT_COMMITTEE: has_committees,
            CAT_PARTICIPATION: has_attendance,
            CAT_ACCOUNTABILITY: has_questions,
        }
        self._build_effective_weights()

        await self._calculate_mp_scores(mp)

        # Peer group percentile
        peer_groups = self._group_by_peers(all_mps)
        peer_key = self._get_peer_key(mp)
        if peer_key in peer_groups:
            self._assign_percentiles(peer_groups[peer_key], peer_key)

        # Save
        await self.mp_repo.update_scores(mp.id, self._extract_scores(mp))

        return self._extract_scores(mp)

    # ------------------------------------------------------------------ #
    #  Dynamic Weight Redistribution                                       #
    # ------------------------------------------------------------------ #

    def _build_effective_weights(self) -> None:
        """
        Build effective weights by redistributing from empty categories.

        If a category has no data system-wide (no MP has any activity),
        its base weight is redistributed proportionally to categories
        that DO have data.

        If NO categories have data at all, all weights are set to 0
        (everyone gets 0 -- there is genuinely no data).
        """
        base_weights = {
            CAT_LEGISLATIVE: self.weights.legislative,
            CAT_ENGAGEMENT: self.weights.engagement,
            CAT_COMMITTEE: self.weights.committee,
            CAT_PARTICIPATION: self.weights.participation,
            CAT_ACCOUNTABILITY: self.weights.accountability,
        }

        # Collect weights for active categories only
        active: Dict[str, float] = {}
        for cat, has_data in self._data_availability.items():
            if has_data:
                active[cat] = base_weights[cat]

        if not active:
            # No data at all -- zero everything
            self._effective_weights = {cat: 0.0 for cat in base_weights}
            return

        # Normalize: redistribute so active weights sum to 1.0
        total_active = sum(active.values())
        self._effective_weights = {}
        for cat in base_weights:
            if cat in active:
                self._effective_weights[cat] = active[cat] / total_active
            else:
                self._effective_weights[cat] = 0.0

    # ------------------------------------------------------------------ #
    #  Per-MP Scoring                                                      #
    # ------------------------------------------------------------------ #

    async def _calculate_mp_scores(self, mp) -> None:
        """
        Calculate all category scores for an MP.

        Loads fresh data from repositories, updates raw counts on the
        MP object, calculates the five internal category scores, then
        computes the weighted composite using effective weights.
        """
        # ----- Load data from repositories -----
        bills_count = await self.bill_repo.count_by_mp(mp.id)
        committee_roles = await self.committee_repo.count_mp_roles(mp.id)
        committee_attendance = await self.committee_repo.get_average_attendance(mp.id)
        question_count = await self.question_repo.count_by_mp(mp.id)
        attendance_stats = await self.attendance_repo.get_attendance_stats(mp.id)

        # ----- Update MP with latest raw counts -----
        mp.bills_introduced = sum(bills_count.values())
        mp.bills_passed = (
            bills_count.get("passed", 0) + bills_count.get("authenticated", 0)
        )
        mp.bills_pending = (
            bills_count.get("registered", 0)
            + bills_count.get("first_reading", 0)
            + bills_count.get("committee", 0)
            + bills_count.get("second_reading", 0)
        )

        mp.committee_memberships = sum(committee_roles.values())
        mp.committee_leadership_roles = (
            committee_roles.get("chair", 0) + committee_roles.get("vice_chair", 0)
        )
        mp.committee_attendance_pct = committee_attendance

        mp.questions_asked = question_count.get("total", 0)
        mp.questions_answered = (
            await self.question_repo.count_answered_by_mp(mp.id)
            if mp.is_minister
            else 0
        )

        mp.sessions_total = attendance_stats.get("sessions_total", 0)
        mp.sessions_attended = attendance_stats.get("sessions_attended", 0)
        mp.session_attendance_pct = attendance_stats.get("attendance_pct")

        # speeches_count is already on the MP object (set by video archive scraper)
        # No need to reload it here

        # ----- Calculate the five internal category scores (each 0-100) -----
        _legislative = self._calc_legislative(mp)
        _engagement = self._calc_engagement(mp)
        _committee = self._calc_committee(mp)
        _participation = self._calc_participation(mp)
        _accountability = self._calc_accountability(mp)

        # ----- Compute weighted composite using effective weights -----
        mp.performance_score = (
            _legislative * self._effective_weights[CAT_LEGISLATIVE]
            + _engagement * self._effective_weights[CAT_ENGAGEMENT]
            + _committee * self._effective_weights[CAT_COMMITTEE]
            + _participation * self._effective_weights[CAT_PARTICIPATION]
            + _accountability * self._effective_weights[CAT_ACCOUNTABILITY]
        )

        # ----- Map 5 internal categories -> 4 DB columns -----
        # legislative_score = legislative category
        mp.legislative_score = _legislative

        # participation_score = engagement (speeches) + participation (attendance) combined
        # Weighted average: engagement gets more weight since speeches are richer data
        eng_w = self._effective_weights[CAT_ENGAGEMENT]
        part_w = self._effective_weights[CAT_PARTICIPATION]
        combined_w = eng_w + part_w
        if combined_w > 0:
            mp.participation_score = (
                _engagement * eng_w + _participation * part_w
            ) / combined_w
        else:
            mp.participation_score = 0.0

        # accountability_score = accountability category
        mp.accountability_score = _accountability

        # committee_score = committee category
        mp.committee_score = _committee

        # Store internal scores for percentile calculation
        mp._internal_legislative = _legislative
        mp._internal_engagement = _engagement
        mp._internal_committee = _committee
        mp._internal_participation = _participation
        mp._internal_accountability = _accountability

    # ------------------------------------------------------------------ #
    #  Category Score Calculators (each returns 0-100)                     #
    # ------------------------------------------------------------------ #

    def _calc_legislative(self, mp) -> float:
        """
        Calculate legislative productivity score (0-100).

        Factors:
        - Bills introduced: 5 pts each, max 40
        - Bills passed: 15 pts each, max 40
        - Amendments proposed: 4 pts each, max 20
        """
        if mp.bills_introduced == 0 and mp.amendments_proposed == 0:
            return 0.0

        # Bills introduced (5 pts each, max 40)
        intro = min(40, mp.bills_introduced * 5)

        # Bills passed (15 pts each, max 40)
        passed = min(40, mp.bills_passed * 15)

        # Amendments (4 pts each, max 20)
        amend = min(20, mp.amendments_proposed * 4)

        return min(100.0, intro + passed + amend)

    def _calc_engagement(self, mp) -> float:
        """
        Calculate parliamentary engagement score (0-100).

        Based on speeches_count from video archive matching.
        Uses diminishing returns:
        - 1-5 speeches: 8 pts each (max 40)
        - 6-15 speeches: 4 pts each (40 more, max 80)
        - 16+ speeches: 2 pts each (up to 100)
        """
        count = mp.speeches_count or 0
        if count == 0:
            return 0.0

        if count <= 5:
            return min(100.0, count * 8)
        elif count <= 15:
            return min(100.0, 40 + (count - 5) * 4)
        else:
            return min(100.0, 80 + (count - 15) * 2)

    def _calc_committee(self, mp) -> float:
        """
        Calculate committee work score (0-100).

        Factors:
        - Committee memberships: 15 pts each, max 45
        - Leadership roles (chair/vice-chair): 25 pts each, max 50
        - Committee attendance percentage: scaled 0-30
        """
        if mp.committee_memberships == 0:
            return 0.0

        # Memberships (15 pts each, max 45)
        membership = min(45, mp.committee_memberships * 15)

        # Leadership (25 pts per role, max 50)
        leadership = min(50, mp.committee_leadership_roles * 25)

        # Attendance (scale 0-30 from percentage 0-100)
        attendance = (mp.committee_attendance_pct or 0) * 0.3

        return min(100.0, membership + leadership + attendance)

    def _calc_participation(self, mp) -> float:
        """
        Calculate participation score (0-100).

        Based on session attendance and committee attendance.
        - Session attendance: 70% weight
        - Committee attendance: 30% weight

        Returns 0 if no attendance data exists at all.
        """
        session_pct = mp.session_attendance_pct
        committee_pct = mp.committee_attendance_pct

        if session_pct is None and (committee_pct is None or committee_pct == 0):
            return 0.0

        # Session attendance (70% of score)
        session = (session_pct or 0) * 0.7

        # Committee attendance (30% of score)
        committee = (committee_pct or 0) * 0.3

        return min(100.0, session + committee)

    def _calc_accountability(self, mp) -> float:
        """
        Calculate accountability score (0-100).

        Factors:
        - Questions asked: 3 pts each, max 60
        - Motions/resolutions proposed: 5 pts each, max 20
        - Questions answered (ministers only): 2 pts each, max 20
        """
        total_activity = (
            mp.questions_asked + mp.motions_proposed + mp.resolutions_proposed
        )
        if total_activity == 0:
            return 0.0

        # Questions asked (3 pts each, max 60)
        question = min(60, mp.questions_asked * 3)

        # Motions/resolutions (5 pts each, max 20)
        motion = min(20, (mp.motions_proposed + mp.resolutions_proposed) * 5)

        # Answers (ministers only, 2 pts each, max 20)
        answer = 0
        if mp.is_minister and mp.questions_answered > 0:
            answer = min(20, mp.questions_answered * 2)

        return min(100.0, question + motion + answer)

    # ------------------------------------------------------------------ #
    #  Peer Groups and Percentiles                                         #
    # ------------------------------------------------------------------ #

    def _group_by_peers(self, mps: list) -> Dict[str, list]:
        """
        Group MPs by peer comparison category.

        Categories:
        - minister (all ministers compared together)
        - fptp_{province_id} (FPTP MPs by province)
        - pr_{province_id} (PR MPs by province)
        - na (National Assembly members)
        """
        groups: Dict[str, list] = {}

        for mp in mps:
            key = self._get_peer_key(mp)
            if key not in groups:
                groups[key] = []
            groups[key].append(mp)

        return groups

    def _get_peer_key(self, mp) -> str:
        """Get peer group key for an MP."""
        if mp.is_minister:
            return "minister"
        if mp.chamber == "na":
            return "na"
        # HoR members grouped by election type and province
        province = mp.province_id or 0
        election_type = mp.election_type or "fptp"
        return f"{election_type}_{province}"

    def _assign_percentiles(self, mps: list, peer_group: str) -> None:
        """
        Assign percentile ranks within peer group.

        Updates MP objects in-place.
        """
        if not mps:
            return

        # Sort by performance score descending
        sorted_mps = sorted(mps, key=lambda x: x.performance_score, reverse=True)
        total = len(sorted_mps)

        for rank, mp in enumerate(sorted_mps, 1):
            mp.peer_group = peer_group
            mp.peer_rank = rank
            mp.peer_total = total

            # Percentile (100 = top, 0 = bottom)
            mp.performance_percentile = int((1 - (rank - 1) / total) * 100)

            # Category percentiles (using the 4 stored score columns)
            mp.legislative_percentile = self._calc_percentile(
                mp.legislative_score,
                [m.legislative_score for m in sorted_mps],
            )
            mp.participation_percentile = self._calc_percentile(
                mp.participation_score,
                [m.participation_score for m in sorted_mps],
            )
            mp.accountability_percentile = self._calc_percentile(
                mp.accountability_score,
                [m.accountability_score for m in sorted_mps],
            )
            mp.committee_percentile = self._calc_percentile(
                mp.committee_score,
                [m.committee_score for m in sorted_mps],
            )

            # Assign tier
            pct = mp.performance_percentile
            if pct >= 90:
                mp.performance_tier = "top10"
            elif pct >= 60:
                mp.performance_tier = "above_avg"
            elif pct >= 40:
                mp.performance_tier = "average"
            elif pct >= 10:
                mp.performance_tier = "below_avg"
            else:
                mp.performance_tier = "bottom10"

    def _calc_percentile(self, value: float, all_values: list[float]) -> int:
        """Calculate percentile of a value within a list."""
        if not all_values:
            return 50
        below = sum(1 for v in all_values if v < value)
        return int((below / len(all_values)) * 100)

    # ------------------------------------------------------------------ #
    #  Score Extraction (for DB persistence)                               #
    # ------------------------------------------------------------------ #

    def _extract_scores(self, mp) -> dict:
        """Extract scores as dict for saving to database.

        Maps the 5 internal categories back to the 4 DB columns:
        - legislative_score = legislative category
        - participation_score = engagement + participation combined
        - accountability_score = accountability category
        - committee_score = committee category
        """
        return {
            # Raw counts
            "bills_introduced": mp.bills_introduced,
            "bills_passed": mp.bills_passed,
            "bills_pending": mp.bills_pending,
            "amendments_proposed": mp.amendments_proposed,
            "sessions_total": mp.sessions_total,
            "sessions_attended": mp.sessions_attended,
            "session_attendance_pct": mp.session_attendance_pct,
            "questions_asked": mp.questions_asked,
            "questions_answered": mp.questions_answered,
            "committee_memberships": mp.committee_memberships,
            "committee_leadership_roles": mp.committee_leadership_roles,
            "committee_attendance_pct": mp.committee_attendance_pct,
            "speeches_count": mp.speeches_count,

            # Category scores (4 columns mapping 5 internal categories)
            "legislative_score": mp.legislative_score,
            "legislative_percentile": mp.legislative_percentile,
            "participation_score": mp.participation_score,
            "participation_percentile": mp.participation_percentile,
            "accountability_score": mp.accountability_score,
            "accountability_percentile": mp.accountability_percentile,
            "committee_score": mp.committee_score,
            "committee_percentile": mp.committee_percentile,

            # Composite
            "performance_score": mp.performance_score,
            "performance_percentile": mp.performance_percentile,
            "performance_tier": mp.performance_tier,
            "peer_group": mp.peer_group,
            "peer_rank": mp.peer_rank,
            "peer_total": mp.peer_total,

            "score_updated_at": datetime.utcnow(),
        }


# ============ Service Functions ============

async def recalculate_all_scores(db: AsyncSession) -> dict:
    """
    Recalculate performance scores for all MPs.

    For use in scheduler jobs.
    """
    scorer = PerformanceScorer(db)
    return await scorer.calculate_all_scores()


async def calculate_mp_score(db: AsyncSession, mp_id: UUID) -> Optional[dict]:
    """
    Calculate performance score for a single MP.

    For use in API endpoints.
    """
    scorer = PerformanceScorer(db)
    return await scorer.calculate_mp_score(mp_id)
