"""Election service for business logic."""
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.election import Election, Constituency, Candidate
# CandidateProfileResolver excluded from open-source skeleton
CandidateProfileResolver = None
from app.repositories.election import (
    ElectionRepository,
    ConstituencyRepository,
    CandidateRepository,
    WatchlistRepository,
)
from app.schemas.election import (
    ElectionResponse,
    ConstituencyResponse,
    ConstituencyDetailResponse,
    CandidateResponse,
    NationalSummaryResponse,
    PartySeatResponse,
    DistrictMapDataResponse,
    DistrictElectionData,
    ElectionSnapshotResponse,
    SnapshotConstituencyResponse,
    WatchlistItemResponse,
    WatchlistResponse,
    SwingAnalysisResponse,
    SwingDataResponse,
)


class ElectionService:
    """Service for election-related operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.election_repo = ElectionRepository(db)
        self.constituency_repo = ConstituencyRepository(db)
        self.candidate_repo = CandidateRepository(db)
        self.watchlist_repo = WatchlistRepository(db)
        self.profile_resolver = None  # CandidateProfileResolver excluded

    def _to_candidate_response(
        self,
        candidate: Candidate,
        resolved_profile: Optional[dict] = None,
    ) -> CandidateResponse:
        """Build CandidateResponse from model + resolved profile map."""
        resolved_profile = resolved_profile or {}
        return CandidateResponse(
            id=str(candidate.id),
            external_id=candidate.external_id,
            name_en=candidate.name_en,
            name_ne=candidate.name_ne,
            name_en_roman=resolved_profile.get("name_en_roman", candidate.name_en_roman),
            party=candidate.party,
            party_ne=candidate.party_ne,
            votes=candidate.votes,
            vote_pct=candidate.vote_pct,
            rank=candidate.rank,
            is_winner=candidate.is_winner,
            is_notable=getattr(candidate, "is_notable", None),
            photo_url=candidate.photo_url,
            age=resolved_profile.get("age", candidate.age),
            gender=resolved_profile.get("gender", candidate.gender),
            education=resolved_profile.get("education", candidate.education),
            education_institution=resolved_profile.get("education_institution", candidate.education_institution),
            biography=resolved_profile.get("biography", getattr(candidate, "biography", None)),
            biography_source=resolved_profile.get("biography_source", getattr(candidate, "biography_source", None)),
            biography_source_label=resolved_profile.get("biography_source_label"),
            profile_origin=resolved_profile.get("profile_origin"),
            aliases=resolved_profile.get("aliases", getattr(candidate, "aliases", None)),
            previous_positions=resolved_profile.get("previous_positions", getattr(candidate, "previous_positions", None)),
            linked_entity_id=resolved_profile.get("linked_entity_id"),
            entity_link_confidence=resolved_profile.get("entity_link_confidence", candidate.entity_link_confidence),
            entity_summary=resolved_profile.get("entity_summary"),
        )

    # ============== Elections ==============

    async def get_elections_list(self) -> list[ElectionResponse]:
        """Get list of all elections."""
        elections = await self.election_repo.list_elections()
        return [
            ElectionResponse(
                id=str(e.id),
                year_bs=e.year_bs,
                year_ad=e.year_ad,
                election_type=e.election_type,
                status=e.status,
                total_constituencies=e.total_constituencies,
                total_registered_voters=e.total_registered_voters,
                total_votes_cast=e.total_votes_cast,
                turnout_pct=e.turnout_pct,
                started_at=e.started_at,
                completed_at=e.completed_at,
                created_at=e.created_at,
            )
            for e in elections
        ]

    async def get_election_by_year(self, year_bs: int) -> Optional[Election]:
        """Get election by Bikram Sambat year."""
        return await self.election_repo.get_by_year(year_bs)

    # ============== Constituencies ==============

    async def get_constituencies(
        self,
        year_bs: int,
        province: Optional[str] = None,
        province_id: Optional[int] = None,
        district: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[ConstituencyResponse], int]:
        """Get paginated list of constituencies."""
        election = await self.election_repo.get_by_year(year_bs)
        if not election:
            return [], 0

        constituencies, total = await self.constituency_repo.list_constituencies(
            election_id=election.id,
            province=province,
            province_id=province_id,
            district=district,
            status=status,
            page=page,
            page_size=per_page,
        )

        items = [
            ConstituencyResponse(
                id=str(c.id),
                constituency_code=c.constituency_code,
                name_en=c.name_en,
                name_ne=c.name_ne,
                district=c.district,
                province=c.province,
                province_id=c.province_id,
                status=c.status,
                total_registered_voters=c.total_registered_voters,
                total_votes_cast=c.total_votes_cast,
                turnout_pct=c.turnout_pct,
                winner_party=c.winner_party,
                winner_votes=c.winner_votes,
                winner_margin=c.winner_margin,
            )
            for c in constituencies
        ]

        return items, total

    async def get_constituency_detail(
        self, year_bs: int, code: str
    ) -> Optional[ConstituencyDetailResponse]:
        """Get constituency detail with candidates."""
        election = await self.election_repo.get_by_year(year_bs)
        if not election:
            return None

        constituency = await self.constituency_repo.get_by_code_with_candidates(
            election_id=election.id, code=code
        )
        if not constituency:
            return None

        overrides = await self.profile_resolver.get_active_overrides_map(
            [c.external_id for c in constituency.candidates]
        )
        candidates = [
            self._to_candidate_response(
                c,
                self.profile_resolver.resolve_candidate_profile(
                    c,
                    overrides.get(c.external_id, {}),
                ),
            )
            for c in sorted(constituency.candidates, key=lambda x: x.votes, reverse=True)
        ]

        return ConstituencyDetailResponse(
            id=str(constituency.id),
            constituency_code=constituency.constituency_code,
            name_en=constituency.name_en,
            name_ne=constituency.name_ne,
            district=constituency.district,
            province=constituency.province,
            province_id=constituency.province_id,
            status=constituency.status,
            total_registered_voters=constituency.total_registered_voters,
            total_votes_cast=constituency.total_votes_cast,
            turnout_pct=constituency.turnout_pct,
            winner_party=constituency.winner_party,
            winner_votes=constituency.winner_votes,
            winner_margin=constituency.winner_margin,
            valid_votes=constituency.valid_votes,
            invalid_votes=constituency.invalid_votes,
            candidates=candidates,
        )

    # ============== National Summary ==============

    async def get_national_summary(self, year_bs: int) -> Optional[NationalSummaryResponse]:
        """Get national summary for an election year."""
        summary = await self.election_repo.get_national_summary(year_bs)
        if not summary:
            return None

        return NationalSummaryResponse(
            election_id=summary["election_id"],
            year_bs=summary["year_bs"],
            year_ad=summary["year_ad"],
            status=summary["status"],
            total_constituencies=summary["total_constituencies"],
            declared=summary["declared"],
            counting=summary["counting"],
            pending=summary["pending"],
            turnout_pct=summary["turnout_pct"],
            total_votes_cast=summary["total_votes_cast"],
            total_registered_voters=summary["total_registered_voters"],
            leading_party=summary["leading_party"],
            leading_party_seats=summary["leading_party_seats"],
            party_seats=[
                PartySeatResponse(party=p["party"], seats=p["seats"])
                for p in summary["party_seats"]
            ],
        )

    # ============== Map Data ==============

    async def get_district_map_data(self, year_bs: int) -> Optional[DistrictMapDataResponse]:
        """Get district-level data for map display."""
        election = await self.election_repo.get_by_year(year_bs)
        if not election:
            return None

        aggregates = await self.constituency_repo.get_district_aggregates(election.id)

        districts = [
            DistrictElectionData(
                district=agg["district"],
                province=agg["province"],
                province_id=agg["province_id"],
                constituencies=agg["constituencies"],
                declared=agg["declared"],
                counting=agg["counting"],
                pending=agg["pending"],
                dominant_party=agg["dominant_party"],
                parties=agg["parties"],
                total_votes=agg["total_votes"],
            )
            for agg in aggregates
        ]

        return DistrictMapDataResponse(
            election_id=str(election.id),
            year_bs=year_bs,
            districts=districts,
        )

    # ============== Swing Analysis ==============

    async def get_swing_analysis(
        self, current_year: int, previous_year: int
    ) -> Optional[SwingAnalysisResponse]:
        """Get swing analysis between two election years."""
        current_summary = await self.election_repo.get_national_summary(current_year)
        previous_summary = await self.election_repo.get_national_summary(previous_year)

        if not current_summary or not previous_summary:
            return None

        # Build party seats maps
        current_seats = {p["party"]: p["seats"] for p in current_summary["party_seats"]}
        previous_seats = {p["party"]: p["seats"] for p in previous_summary["party_seats"]}

        # Get all parties
        all_parties = set(current_seats.keys()) | set(previous_seats.keys())

        # Calculate swings
        swings = []
        total_current = sum(current_seats.values())
        total_previous = sum(previous_seats.values())

        for party in all_parties:
            curr = current_seats.get(party, 0)
            prev = previous_seats.get(party, 0)
            change = curr - prev

            # Calculate swing percentage (based on total seats)
            if total_current > 0:
                swing_pct = (change / total_current) * 100
            else:
                swing_pct = 0.0

            swings.append(
                SwingDataResponse(
                    party=party,
                    current_seats=curr,
                    previous_seats=prev,
                    change=change,
                    swing_pct=round(swing_pct, 2),
                )
            )

        # Sort by current seats descending
        swings.sort(key=lambda x: x.current_seats, reverse=True)

        return SwingAnalysisResponse(
            current_year=current_year,
            previous_year=previous_year,
            swings=swings,
        )

    async def get_election_snapshot(
        self,
        year_bs: int,
        source_mode: str = "db_primary_json_fallback",
    ) -> Optional[ElectionSnapshotResponse]:
        """Return frontend-compatible full election snapshot from DB."""
        election = await self.election_repo.get_by_year(year_bs)
        if not election:
            return None

        constituencies = await self.constituency_repo.get_all_with_candidates(election.id)
        external_ids = [
            candidate.external_id
            for constituency in constituencies
            for candidate in constituency.candidates
        ]
        overrides = await self.profile_resolver.get_active_overrides_map(external_ids)

        result_items: list[SnapshotConstituencyResponse] = []
        for constituency in constituencies:
            sorted_candidates = sorted(constituency.candidates, key=lambda c: c.votes, reverse=True)
            candidate_responses = [
                self._to_candidate_response(
                    candidate,
                    self.profile_resolver.resolve_candidate_profile(
                        candidate,
                        overrides.get(candidate.external_id, {}),
                    ),
                )
                for candidate in sorted_candidates
            ]

            winner = next((c for c in sorted_candidates if c.is_winner), None)
            result_items.append(
                SnapshotConstituencyResponse(
                    constituency_id=constituency.constituency_code,
                    name_en=constituency.name_en,
                    name_ne=constituency.name_ne,
                    district=constituency.district,
                    province=constituency.province,
                    province_id=constituency.province_id,
                    status=constituency.status,
                    winner_party=constituency.winner_party,
                    winner_name=(winner.name_en_roman or winner.name_en) if winner else None,
                    winner_votes=constituency.winner_votes,
                    total_votes=constituency.total_votes_cast or 0,
                    turnout_pct=constituency.turnout_pct,
                    candidates=candidate_responses,
                )
            )

        national_summary = await self.get_national_summary(year_bs)
        return ElectionSnapshotResponse(
            election_year=year_bs,
            total_constituencies=election.total_constituencies,
            results=result_items,
            constituencies=result_items,
            national_summary=national_summary,
            source_mode=source_mode,
        )

    # ============== Watchlist ==============

    async def get_user_watchlist(self, user_id: str) -> WatchlistResponse:
        """Get user's watchlist with constituency details."""
        items = await self.watchlist_repo.get_user_watchlist(user_id)

        response_items = []
        for item in items:
            constituency = item.constituency
            response_items.append(
                WatchlistItemResponse(
                    id=str(item.id),
                    user_id=item.user_id,
                    constituency_id=str(item.constituency_id),
                    constituency_code=constituency.constituency_code if constituency else None,
                    constituency_name=constituency.name_en if constituency else None,
                    district=constituency.district if constituency else None,
                    province=constituency.province if constituency else None,
                    province_id=constituency.province_id if constituency else None,
                    status=constituency.status if constituency else None,
                    winner_party=constituency.winner_party if constituency else None,
                    alert_level=item.alert_level,
                    notes=item.notes,
                    is_active=item.is_active,
                    created_at=item.created_at,
                )
            )

        return WatchlistResponse(items=response_items, total=len(response_items))

    async def add_to_watchlist(
        self,
        user_id: str,
        constituency_id: UUID,
        alert_level: str = "medium",
        notes: Optional[str] = None,
    ) -> WatchlistItemResponse:
        """Add constituency to user's watchlist."""
        item = await self.watchlist_repo.add_to_watchlist(
            user_id=user_id,
            constituency_id=constituency_id,
            alert_level=alert_level,
            notes=notes,
        )

        # Get constituency details
        constituency = await self.constituency_repo.get_by_id(constituency_id)

        return WatchlistItemResponse(
            id=str(item.id),
            user_id=item.user_id,
            constituency_id=str(item.constituency_id),
            constituency_code=constituency.constituency_code if constituency else None,
            constituency_name=constituency.name_en if constituency else None,
            district=constituency.district if constituency else None,
            province=constituency.province if constituency else None,
            province_id=constituency.province_id if constituency else None,
            status=constituency.status if constituency else None,
            winner_party=constituency.winner_party if constituency else None,
            alert_level=item.alert_level,
            notes=item.notes,
            is_active=item.is_active,
            created_at=item.created_at,
        )

    async def remove_from_watchlist(self, user_id: str, constituency_id: UUID) -> bool:
        """Remove constituency from user's watchlist."""
        return await self.watchlist_repo.remove_from_watchlist(user_id, constituency_id)

    async def is_on_watchlist(self, user_id: str, constituency_id: UUID) -> bool:
        """Check if constituency is on user's watchlist."""
        return await self.watchlist_repo.is_on_watchlist(user_id, constituency_id)
