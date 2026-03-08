"""Election repository for database operations."""
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.election import (
    Election,
    Constituency,
    Candidate,
    UserConstituencyWatchlist,
    ConstituencyStatus,
)


# Nepali character variation mappings for fuzzy matching
# These are common spelling variations in Nepali names
NEPALI_CHAR_VARIANTS = {
    "ब": "व",  # ba ↔ va (very common: रबि/रवि)
    "व": "ब",
    "श": "ष",  # sha variants
    "ष": "श",
    "छ": "क्ष",  # chha ↔ ksha
    "क्ष": "छ",
    "ण": "न",  # retroflex vs dental n
    "न": "ण",
    "ृ": "्रि",  # vowel variations
}


def normalize_nepali_name(name: str) -> str:
    """Normalize Nepali name by replacing variant characters with canonical forms.

    This helps match names like रबि लामिछाने and रवि लामिछाने.
    """
    if not name:
        return name

    # Normalize to canonical form (use first character in each pair)
    normalized = name
    # Replace व with ब (canonical form)
    normalized = normalized.replace("व", "ब")
    # Replace ष with श
    normalized = normalized.replace("ष", "श")
    # Replace ण with न
    normalized = normalized.replace("ण", "न")

    return normalized


def generate_nepali_name_variants(name: str) -> list[str]:
    """Generate possible spelling variants of a Nepali name.

    For names like रबि लामिछाने, generates [रबि लामिछाने, रवि लामिछाने].
    """
    if not name:
        return []

    variants = {name}  # Start with original

    # Generate variants by swapping characters
    for original, replacement in NEPALI_CHAR_VARIANTS.items():
        if original in name:
            variants.add(name.replace(original, replacement))

    return list(variants)


class ElectionRepository:
    """Repository for Election database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, election_id: UUID) -> Optional[Election]:
        """Get election by ID."""
        result = await self.db.execute(
            select(Election).where(Election.id == election_id)
        )
        return result.scalar_one_or_none()

    async def get_by_year(self, year_bs: int) -> Optional[Election]:
        """Get election by Bikram Sambat year."""
        result = await self.db.execute(
            select(Election).where(Election.year_bs == year_bs)
        )
        return result.scalar_one_or_none()

    async def get_latest(self) -> Optional[Election]:
        """Get the most recent election by year."""
        result = await self.db.execute(
            select(Election).order_by(Election.year_bs.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_elections(self) -> list[Election]:
        """List all elections ordered by year descending."""
        result = await self.db.execute(
            select(Election).order_by(Election.year_bs.desc())
        )
        return list(result.scalars().all())

    async def create(self, election: Election) -> Election:
        """Create a new election."""
        self.db.add(election)
        await self.db.commit()
        await self.db.refresh(election)
        return election

    async def get_national_summary(self, year_bs: int) -> Optional[dict]:
        """Get national summary for an election year."""
        election = await self.get_by_year(year_bs)
        if not election:
            return None

        # Count constituencies by status
        status_counts = await self.db.execute(
            select(Constituency.status, func.count(Constituency.id))
            .where(Constituency.election_id == election.id)
            .group_by(Constituency.status)
        )
        status_map = {row[0]: row[1] for row in status_counts.all()}

        # Get party seats
        party_seats = await self.db.execute(
            select(Constituency.winner_party, func.count(Constituency.id))
            .where(
                Constituency.election_id == election.id,
                Constituency.status == ConstituencyStatus.DECLARED.value,
                Constituency.winner_party.isnot(None),
            )
            .group_by(Constituency.winner_party)
            .order_by(func.count(Constituency.id).desc())
        )
        party_seats_list = [
            {"party": row[0], "seats": row[1]}
            for row in party_seats.all()
        ]

        # Get leading party
        leading_party = party_seats_list[0] if party_seats_list else None

        return {
            "election_id": str(election.id),
            "year_bs": election.year_bs,
            "year_ad": election.year_ad,
            "status": election.status,
            "total_constituencies": election.total_constituencies,
            "declared": status_map.get(ConstituencyStatus.DECLARED.value, 0),
            "counting": status_map.get(ConstituencyStatus.COUNTING.value, 0),
            "pending": status_map.get(ConstituencyStatus.PENDING.value, 0),
            "turnout_pct": election.turnout_pct or 0.0,
            "total_votes_cast": election.total_votes_cast or 0,
            "total_registered_voters": election.total_registered_voters or 0,
            "leading_party": leading_party["party"] if leading_party else None,
            "leading_party_seats": leading_party["seats"] if leading_party else 0,
            "party_seats": party_seats_list,
        }


class ConstituencyRepository:
    """Repository for Constituency database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, constituency_id: UUID) -> Optional[Constituency]:
        """Get constituency by ID."""
        result = await self.db.execute(
            select(Constituency).where(Constituency.id == constituency_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, election_id: UUID, code: str) -> Optional[Constituency]:
        """Get constituency by code within an election."""
        result = await self.db.execute(
            select(Constituency).where(
                Constituency.election_id == election_id,
                Constituency.constituency_code == code,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code_with_candidates(
        self, election_id: UUID, code: str
    ) -> Optional[Constituency]:
        """Get constituency with candidates loaded."""
        result = await self.db.execute(
            select(Constituency)
            .options(
                selectinload(Constituency.candidates).selectinload(Candidate.political_entity)
            )
            .where(
                Constituency.election_id == election_id,
                Constituency.constituency_code == code,
            )
        )
        return result.scalar_one_or_none()

    async def list_constituencies(
        self,
        election_id: UUID,
        province: Optional[str] = None,
        province_id: Optional[int] = None,
        district: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Constituency], int]:
        """List constituencies with pagination and filters."""
        query = select(Constituency).where(Constituency.election_id == election_id)
        count_query = select(func.count(Constituency.id)).where(
            Constituency.election_id == election_id
        )

        filters = []
        if province:
            filters.append(Constituency.province.ilike(f"%{province}%"))
        if province_id:
            filters.append(Constituency.province_id == province_id)
        if district:
            filters.append(Constituency.district.ilike(f"%{district}%"))
        if status:
            filters.append(Constituency.status == status)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = await self.db.scalar(count_query) or 0

        query = query.order_by(Constituency.province_id, Constituency.district, Constituency.constituency_code)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        constituencies = list(result.scalars().all())

        return constituencies, total

    async def get_all_for_election(self, election_id: UUID) -> list[Constituency]:
        """Get all constituencies for an election (no pagination)."""
        result = await self.db.execute(
            select(Constituency)
            .where(Constituency.election_id == election_id)
            .order_by(Constituency.province_id, Constituency.district, Constituency.constituency_code)
        )
        return list(result.scalars().all())

    async def get_all_with_candidates(self, election_id: UUID) -> list[Constituency]:
        """Get all constituencies with candidates and linked entities preloaded."""
        result = await self.db.execute(
            select(Constituency)
            .options(
                selectinload(Constituency.candidates).selectinload(Candidate.political_entity)
            )
            .where(Constituency.election_id == election_id)
            .order_by(Constituency.province_id, Constituency.district, Constituency.constituency_code)
        )
        return list(result.scalars().all())

    async def create(self, constituency: Constituency) -> Constituency:
        """Create a new constituency."""
        self.db.add(constituency)
        await self.db.commit()
        await self.db.refresh(constituency)
        return constituency

    async def get_district_aggregates(self, election_id: UUID) -> list[dict]:
        """Get aggregated data per district for map display."""
        # Get constituency counts and status by district
        result = await self.db.execute(
            select(
                Constituency.district,
                Constituency.province,
                Constituency.province_id,
                func.count(Constituency.id).label("total"),
                func.sum(
                    func.case(
                        (Constituency.status == ConstituencyStatus.DECLARED.value, 1),
                        else_=0,
                    )
                ).label("declared"),
                func.sum(
                    func.case(
                        (Constituency.status == ConstituencyStatus.COUNTING.value, 1),
                        else_=0,
                    )
                ).label("counting"),
                func.sum(Constituency.total_votes_cast).label("total_votes"),
            )
            .where(Constituency.election_id == election_id)
            .group_by(
                Constituency.district,
                Constituency.province,
                Constituency.province_id,
            )
        )
        district_stats = result.all()

        # Get party seats by district
        party_result = await self.db.execute(
            select(
                Constituency.district,
                Constituency.winner_party,
                func.count(Constituency.id).label("seats"),
            )
            .where(
                Constituency.election_id == election_id,
                Constituency.status == ConstituencyStatus.DECLARED.value,
                Constituency.winner_party.isnot(None),
            )
            .group_by(Constituency.district, Constituency.winner_party)
        )
        party_data = party_result.all()

        # Build party map per district
        party_map: dict[str, dict[str, int]] = {}
        for row in party_data:
            district = row.district
            if district not in party_map:
                party_map[district] = {}
            party_map[district][row.winner_party] = row.seats

        # Combine into result
        aggregates = []
        for row in district_stats:
            parties = party_map.get(row.district, {})
            dominant_party = max(parties, key=parties.get) if parties else None

            aggregates.append({
                "district": row.district,
                "province": row.province,
                "province_id": row.province_id,
                "constituencies": row.total,
                "declared": row.declared or 0,
                "counting": row.counting or 0,
                "pending": row.total - (row.declared or 0) - (row.counting or 0),
                "dominant_party": dominant_party,
                "parties": parties,
                "total_votes": row.total_votes or 0,
            })

        return aggregates


class CandidateRepository:
    """Repository for Candidate database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, candidate_id: UUID) -> Optional[Candidate]:
        """Get candidate by ID."""
        result = await self.db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(
        self, external_id: str, election_id: Optional[UUID] = None
    ) -> Optional[Candidate]:
        """Get candidate by ECN external ID.

        If election_id is not provided, returns the most recent match.
        """
        query = (
            select(Candidate)
            .options(selectinload(Candidate.political_entity))
            .where(Candidate.external_id == external_id)
        )

        if election_id:
            query = query.where(Candidate.election_id == election_id)
        else:
            # Order by election year descending to get most recent
            query = query.order_by(Candidate.created_at.desc())

        query = query.limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_by_constituency(
        self, constituency_id: UUID, order_by_votes: bool = True
    ) -> list[Candidate]:
        """List candidates for a constituency."""
        query = select(Candidate).where(Candidate.constituency_id == constituency_id)
        query = query.options(selectinload(Candidate.political_entity))

        if order_by_votes:
            query = query.order_by(Candidate.votes.desc())
        else:
            query = query.order_by(Candidate.rank)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_winners_by_election(self, election_id: UUID) -> list[Candidate]:
        """List all winners for an election with constituency data."""
        result = await self.db.execute(
            select(Candidate)
            .options(selectinload(Candidate.constituency))
            .where(
                Candidate.election_id == election_id,
                Candidate.is_winner == True,
            )
            .order_by(Candidate.votes.desc())
        )
        return list(result.scalars().all())

    async def get_party_candidates(
        self, election_id: UUID, party: str
    ) -> list[Candidate]:
        """List all candidates from a party."""
        result = await self.db.execute(
            select(Candidate)
            .where(
                Candidate.election_id == election_id,
                Candidate.party.ilike(f"%{party}%"),
            )
            .order_by(Candidate.votes.desc())
        )
        return list(result.scalars().all())

    async def find_previous_runs(
        self,
        name_en: str,
        name_ne: Optional[str],
        current_election_id: UUID,
        current_year_bs: int = 9999,
        name_en_roman: Optional[str] = None,
        aliases: Optional[list] = None,
    ) -> list[dict]:
        """Find previous election runs by matching candidate name.

        Uses multiple matching strategies:
        1. Exact name_en (Nepali script) match
        2. Nepali name variants (spelling variations like रबि/रवि)
        3. Romanized name (name_en_roman) ILIKE match
        4. Aliases matching

        Only returns elections BEFORE current_year_bs (no future runs).
        """
        from sqlalchemy import or_

        # Build name matching conditions
        name_conditions = [Candidate.name_en == name_en]

        # Nepali name variants
        if name_ne:
            nepali_variants = generate_nepali_name_variants(name_ne)
            for variant in nepali_variants:
                name_conditions.append(Candidate.name_ne == variant)

        # Romanized name matching — exact only to avoid false positives
        if name_en_roman:
            name_conditions.append(
                func.lower(Candidate.name_en_roman) == name_en_roman.lower()
            )

        # Alias matching — exact only
        if aliases:
            for alias in aliases[:5]:
                if alias and len(alias) >= 3:
                    name_conditions.append(
                        func.lower(Candidate.name_en_roman) == alias.lower()
                    )
                    name_conditions.append(Candidate.name_en == alias)

        # Find matching candidates in PREVIOUS elections only
        result = await self.db.execute(
            select(Candidate, Election, Constituency)
            .join(Election, Candidate.election_id == Election.id)
            .join(Constituency, Candidate.constituency_id == Constituency.id)
            .where(
                or_(*name_conditions),
                Candidate.election_id != current_election_id,
                Election.year_bs < current_year_bs,
            )
            .order_by(Election.year_bs.desc())
        )

        # Deduplicate: one entry per election year (keep the one with most votes)
        seen: dict[int, dict] = {}
        for row in result.all():
            candidate, election, constituency = row
            year = election.year_bs
            entry = {
                "election_year": year,
                "party_name": candidate.party,
                "constituency_name": constituency.name_en,
                "is_winner": candidate.is_winner,
                "votes_received": candidate.votes,
            }
            if year not in seen or candidate.votes > (seen[year].get("votes_received") or 0):
                seen[year] = entry

        return sorted(seen.values(), key=lambda x: x["election_year"], reverse=True)

    async def find_by_name_in_election(
        self,
        name_en: str,
        name_ne: Optional[str],
        election_id: UUID,
        constituency_code: Optional[str] = None,
        name_en_roman: Optional[str] = None,
        aliases: Optional[list] = None,
    ) -> Optional[Candidate]:
        """Find a candidate by name in a specific election.

        Used to check if a candidate is running in a specific election year.
        Uses multiple matching strategies for robustness.
        """
        from sqlalchemy import or_

        # STRICT match: exact name_en, nepali variants, exact romanized name, exact aliases
        # No fuzzy matching here to avoid false positives across different people
        strict_conditions = [Candidate.name_en == name_en]

        if name_ne:
            for variant in generate_nepali_name_variants(name_ne):
                strict_conditions.append(Candidate.name_ne == variant)

        if name_en_roman:
            strict_conditions.append(
                func.lower(Candidate.name_en_roman) == name_en_roman.lower()
            )

        if aliases:
            for alias in aliases[:5]:
                if alias and len(alias) >= 3:
                    strict_conditions.append(
                        func.lower(Candidate.name_en_roman) == alias.lower()
                    )
                    strict_conditions.append(Candidate.name_en == alias)

        result = await self.db.execute(
            select(Candidate).where(
                or_(*strict_conditions),
                Candidate.election_id == election_id,
            ).limit(1)
        )
        candidate = result.scalar_one_or_none()

        if candidate:
            return candidate

        # FUZZY fallback: same constituency + first AND last romanized name tokens
        # Only applied when constituency matches (same seat = likely same person)
        if constituency_code and name_en_roman:
            tokens = name_en_roman.strip().split()
            if len(tokens) >= 2:
                first_tok = tokens[0].lower()
                last_tok = tokens[-1].lower()
                if len(first_tok) >= 3 and len(last_tok) >= 3:
                    result = await self.db.execute(
                        select(Candidate)
                        .join(Constituency, Candidate.constituency_id == Constituency.id)
                        .where(
                            Candidate.election_id == election_id,
                            Constituency.constituency_code == constituency_code,
                            func.lower(Candidate.name_en_roman).ilike(f"{first_tok[:4]}%"),
                            func.lower(Candidate.name_en_roman).ilike(f"%{last_tok[:4]}%"),
                        )
                        .limit(1)
                    )
                    candidate = result.scalar_one_or_none()

        return candidate

    async def create(self, candidate: Candidate) -> Candidate:
        """Create a new candidate."""
        self.db.add(candidate)
        await self.db.commit()
        await self.db.refresh(candidate)
        return candidate

    async def bulk_create(self, candidates: list[Candidate]) -> int:
        """Bulk create candidates."""
        self.db.add_all(candidates)
        await self.db.commit()
        return len(candidates)


class WatchlistRepository:
    """Repository for UserConstituencyWatchlist database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, watchlist_id: UUID) -> Optional[UserConstituencyWatchlist]:
        """Get watchlist item by ID."""
        result = await self.db.execute(
            select(UserConstituencyWatchlist).where(
                UserConstituencyWatchlist.id == watchlist_id
            )
        )
        return result.scalar_one_or_none()

    async def get_user_watchlist(
        self, user_id: str, active_only: bool = True
    ) -> list[UserConstituencyWatchlist]:
        """Get all watchlist items for a user."""
        query = select(UserConstituencyWatchlist).options(
            selectinload(UserConstituencyWatchlist.constituency)
        ).where(UserConstituencyWatchlist.user_id == user_id)

        if active_only:
            query = query.where(UserConstituencyWatchlist.is_active == True)

        query = query.order_by(UserConstituencyWatchlist.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def is_on_watchlist(self, user_id: str, constituency_id: UUID) -> bool:
        """Check if constituency is on user's watchlist."""
        result = await self.db.execute(
            select(func.count(UserConstituencyWatchlist.id)).where(
                UserConstituencyWatchlist.user_id == user_id,
                UserConstituencyWatchlist.constituency_id == constituency_id,
                UserConstituencyWatchlist.is_active == True,
            )
        )
        return (result.scalar() or 0) > 0

    async def add_to_watchlist(
        self,
        user_id: str,
        constituency_id: UUID,
        alert_level: str = "medium",
        notes: Optional[str] = None,
    ) -> UserConstituencyWatchlist:
        """Add constituency to user's watchlist."""
        # Check if already exists (reactivate if inactive)
        existing = await self.db.execute(
            select(UserConstituencyWatchlist).where(
                UserConstituencyWatchlist.user_id == user_id,
                UserConstituencyWatchlist.constituency_id == constituency_id,
            )
        )
        item = existing.scalar_one_or_none()

        if item:
            item.is_active = True
            item.alert_level = alert_level
            if notes:
                item.notes = notes
            await self.db.commit()
            await self.db.refresh(item)
            return item

        # Create new
        item = UserConstituencyWatchlist(
            user_id=user_id,
            constituency_id=constituency_id,
            alert_level=alert_level,
            notes=notes,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def remove_from_watchlist(self, user_id: str, constituency_id: UUID) -> bool:
        """Remove constituency from user's watchlist (soft delete)."""
        result = await self.db.execute(
            select(UserConstituencyWatchlist).where(
                UserConstituencyWatchlist.user_id == user_id,
                UserConstituencyWatchlist.constituency_id == constituency_id,
            )
        )
        item = result.scalar_one_or_none()

        if not item:
            return False

        item.is_active = False
        await self.db.commit()
        return True

    async def hard_delete(self, user_id: str, constituency_id: UUID) -> bool:
        """Permanently delete watchlist item."""
        result = await self.db.execute(
            delete(UserConstituencyWatchlist).where(
                UserConstituencyWatchlist.user_id == user_id,
                UserConstituencyWatchlist.constituency_id == constituency_id,
            )
        )
        await self.db.commit()
        return result.rowcount > 0

    async def update_alert_level(
        self, user_id: str, constituency_id: UUID, alert_level: str
    ) -> Optional[UserConstituencyWatchlist]:
        """Update alert level for a watchlist item."""
        result = await self.db.execute(
            select(UserConstituencyWatchlist).where(
                UserConstituencyWatchlist.user_id == user_id,
                UserConstituencyWatchlist.constituency_id == constituency_id,
            )
        )
        item = result.scalar_one_or_none()

        if not item:
            return None

        item.alert_level = alert_level
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def count_user_watchlist(self, user_id: str) -> int:
        """Count items in user's watchlist."""
        result = await self.db.execute(
            select(func.count(UserConstituencyWatchlist.id)).where(
                UserConstituencyWatchlist.user_id == user_id,
                UserConstituencyWatchlist.is_active == True,
            )
        )
        return result.scalar() or 0
