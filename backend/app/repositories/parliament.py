"""Parliament repository for MP Performance Index database operations.

Provides CRUD operations for:
- MP Performance records
- Parliament Bills
- Committees and Memberships
- Parliamentary Questions
- Session Attendance
"""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.parliament import (
    MPPerformance,
    ParliamentBill,
    BillSponsor,
    ParliamentCommittee,
    CommitteeMembership,
    ParliamentQuestion,
    SessionAttendance,
)


class MPPerformanceRepository:
    """Repository for MP Performance database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, mp_id: UUID) -> Optional[MPPerformance]:
        """Get MP by internal UUID."""
        result = await self.db.execute(
            select(MPPerformance).where(MPPerformance.id == mp_id)
        )
        return result.scalar_one_or_none()

    async def get_by_mp_id(self, mp_id: str) -> Optional[MPPerformance]:
        """Get MP by parliament website ID."""
        result = await self.db.execute(
            select(MPPerformance).where(MPPerformance.mp_id == mp_id)
        )
        return result.scalar_one_or_none()

    async def get_by_candidate_id(self, candidate_id: UUID) -> Optional[MPPerformance]:
        """Get MP linked to a specific election candidate.

        Note: Returns first match if multiple MPs are linked (can happen due to
        duplicate MP records from HoR/NA scraping).
        """
        result = await self.db.execute(
            select(MPPerformance).where(
                MPPerformance.linked_candidate_id == candidate_id
            ).order_by(MPPerformance.performance_score.desc())  # Prefer higher score
        )
        return result.scalars().first()

    async def list_mps(
        self,
        chamber: Optional[str] = None,
        party: Optional[str] = None,
        province_id: Optional[int] = None,
        election_type: Optional[str] = None,
        min_score: Optional[float] = None,
        tier: Optional[str] = None,
        q: Optional[str] = None,
        is_current: bool = True,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[MPPerformance], int]:
        """List MPs with filters and pagination."""
        query = select(MPPerformance)
        count_query = select(func.count(MPPerformance.id))

        filters = []
        if chamber:
            filters.append(MPPerformance.chamber == chamber)
        if party:
            filters.append(MPPerformance.party.ilike(f"%{party}%"))
        if province_id:
            filters.append(MPPerformance.province_id == province_id)
        if election_type:
            filters.append(MPPerformance.election_type == election_type)
        if min_score is not None:
            filters.append(MPPerformance.performance_score >= min_score)
        if tier:
            filters.append(MPPerformance.performance_tier == tier)
        if q and q.strip():
            search_term = q.strip()
            filters.append(
                or_(
                    MPPerformance.name_en.ilike(f"%{search_term}%"),
                    MPPerformance.name_ne.ilike(f"%{search_term}%"),
                    MPPerformance.party.ilike(f"%{search_term}%"),
                    MPPerformance.constituency.ilike(f"%{search_term}%"),
                    MPPerformance.mp_id.ilike(f"%{search_term}%"),
                )
            )
        if is_current:
            filters.append(MPPerformance.is_current_member == True)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = await self.db.scalar(count_query) or 0

        query = query.order_by(MPPerformance.performance_score.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)

        result = await self.db.execute(query)
        mps = list(result.scalars().all())

        return mps, total

    async def list_all_current(self, chamber: Optional[str] = None) -> list[MPPerformance]:
        """List all current MPs (no pagination, for scoring)."""
        query = select(MPPerformance).where(MPPerformance.is_current_member == True)
        if chamber:
            query = query.where(MPPerformance.chamber == chamber)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_rankings(
        self,
        category: str = "overall",
        peer_group: Optional[str] = None,
        limit: int = 20,
    ) -> list[MPPerformance]:
        """Get top MPs by category within optional peer group."""
        query = select(MPPerformance).where(MPPerformance.is_current_member == True)

        if peer_group:
            query = query.where(MPPerformance.peer_group == peer_group)

        # Order by appropriate score category
        if category == "legislative":
            query = query.order_by(MPPerformance.legislative_score.desc())
        elif category == "participation":
            query = query.order_by(MPPerformance.participation_score.desc())
        elif category == "accountability":
            query = query.order_by(MPPerformance.accountability_score.desc())
        elif category == "committee":
            query = query.order_by(MPPerformance.committee_score.desc())
        else:  # overall
            query = query.order_by(MPPerformance.performance_score.desc())

        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search_by_name(
        self, name: str, limit: int = 10
    ) -> list[MPPerformance]:
        """Search MPs by name (English or Nepali).

        Uses token-based search to handle variations like:
        - "के.पी शर्मा ओली" vs "के.पी शर्मा (ओली)"
        """
        # Try exact match first
        result = await self.db.execute(
            select(MPPerformance)
            .where(
                or_(
                    MPPerformance.name_en.ilike(f"%{name}%"),
                    MPPerformance.name_ne.ilike(f"%{name}%"),
                )
            )
            .order_by(MPPerformance.performance_score.desc())
            .limit(limit)
        )
        mps = list(result.scalars().all())

        if mps:
            return mps

        # Fallback: token-based search (match MPs containing all key tokens)
        # Split name into tokens and search for each
        tokens = [t.strip() for t in name.replace("(", " ").replace(")", " ").replace(".", " ").split() if len(t.strip()) > 1]

        if len(tokens) >= 2:
            # Use first and last significant tokens
            conditions = []
            for token in tokens[:3]:  # Use up to 3 tokens
                conditions.append(
                    or_(
                        MPPerformance.name_en.ilike(f"%{token}%"),
                        MPPerformance.name_ne.ilike(f"%{token}%"),
                    )
                )

            if conditions:
                result = await self.db.execute(
                    select(MPPerformance)
                    .where(and_(*conditions))
                    .order_by(MPPerformance.performance_score.desc())
                    .limit(limit)
                )
                return list(result.scalars().all())

        return []

    async def upsert(self, mp_data: dict) -> MPPerformance:
        """Insert or update MP by parliament website ID."""
        mp_id = mp_data.get("mp_id")
        existing = await self.get_by_mp_id(mp_id)

        if existing:
            # Update existing record
            for key, value in mp_data.items():
                if hasattr(existing, key) and key != "id":
                    setattr(existing, key, value)
            existing.scraped_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            # Create new record
            mp = MPPerformance(**mp_data)
            mp.scraped_at = datetime.utcnow()
            self.db.add(mp)
            await self.db.commit()
            await self.db.refresh(mp)
            return mp

    async def update_link(
        self, mp_uuid: UUID, candidate_id: UUID, confidence: float
    ) -> MPPerformance:
        """Update candidate linking for an MP."""
        mp = await self.get_by_id(mp_uuid)
        if mp:
            mp.linked_candidate_id = candidate_id
            mp.link_confidence = confidence
            await self.db.commit()
            await self.db.refresh(mp)
        return mp

    async def update_scores(self, mp_uuid: UUID, scores: dict) -> MPPerformance:
        """Update performance scores for an MP."""
        mp = await self.get_by_id(mp_uuid)
        if mp:
            for key, value in scores.items():
                if hasattr(mp, key):
                    setattr(mp, key, value)
            mp.score_updated_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(mp)
        return mp

    async def update_speeches_count(self, mp_uuid: UUID, count: int) -> Optional[MPPerformance]:
        """Update speeches_count for an MP (from video archives)."""
        mp = await self.get_by_id(mp_uuid)
        if mp:
            mp.speeches_count = count
            await self.db.commit()
            await self.db.refresh(mp)
        return mp

    async def bulk_update_scores(self, updates: list[tuple[UUID, dict]]):
        """Bulk update scores for multiple MPs."""
        for mp_uuid, scores in updates:
            mp = await self.get_by_id(mp_uuid)
            if mp:
                for key, value in scores.items():
                    if hasattr(mp, key):
                        setattr(mp, key, value)
                mp.score_updated_at = datetime.utcnow()
        await self.db.commit()

    async def get_peer_groups(self) -> list[str]:
        """Get all unique peer groups."""
        result = await self.db.execute(
            select(MPPerformance.peer_group)
            .distinct()
            .where(MPPerformance.peer_group.isnot(None))
        )
        return [row[0] for row in result.all()]


class BillRepository:
    """Repository for Parliament Bill database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, bill_id: UUID) -> Optional[ParliamentBill]:
        """Get bill by ID."""
        result = await self.db.execute(
            select(ParliamentBill)
            .options(selectinload(ParliamentBill.sponsors))
            .where(ParliamentBill.id == bill_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[ParliamentBill]:
        """Get bill by parliament website ID."""
        result = await self.db.execute(
            select(ParliamentBill).where(ParliamentBill.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def list_bills(
        self,
        status: Optional[str] = None,
        bill_type: Optional[str] = None,
        chamber: Optional[str] = None,
        presenting_mp_id: Optional[UUID] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[ParliamentBill], int]:
        """List bills with filters and pagination."""
        query = select(ParliamentBill)
        count_query = select(func.count(ParliamentBill.id))

        filters = []
        if status:
            filters.append(ParliamentBill.status == status)
        if bill_type:
            filters.append(ParliamentBill.bill_type == bill_type)
        if chamber:
            filters.append(ParliamentBill.chamber == chamber)
        if presenting_mp_id:
            filters.append(ParliamentBill.presenting_mp_id == presenting_mp_id)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = await self.db.scalar(count_query) or 0

        query = query.order_by(ParliamentBill.presented_date.desc().nullslast())
        query = query.offset((page - 1) * per_page).limit(per_page)

        result = await self.db.execute(query)
        bills = list(result.scalars().all())

        return bills, total

    async def list_by_mp(
        self, mp_id: UUID, status: Optional[str] = None, limit: int = 20
    ) -> list[ParliamentBill]:
        """List bills introduced by a specific MP."""
        query = select(ParliamentBill).where(
            ParliamentBill.presenting_mp_id == mp_id
        )
        if status:
            query = query.where(ParliamentBill.status == status)
        query = query.order_by(ParliamentBill.presented_date.desc().nullslast())
        query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_by_sponsor(self, mp_id: UUID, limit: int = 20) -> list[ParliamentBill]:
        """List bills sponsored/co-sponsored by an MP."""
        result = await self.db.execute(
            select(ParliamentBill)
            .join(BillSponsor, BillSponsor.bill_id == ParliamentBill.id)
            .where(BillSponsor.mp_id == mp_id)
            .order_by(ParliamentBill.presented_date.desc().nullslast())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_mp(self, mp_id: UUID) -> dict:
        """Count bills by status for an MP."""
        result = await self.db.execute(
            select(ParliamentBill.status, func.count(ParliamentBill.id))
            .where(ParliamentBill.presenting_mp_id == mp_id)
            .group_by(ParliamentBill.status)
        )
        return {row[0]: row[1] for row in result.all()}

    async def has_any_data(self) -> bool:
        """Check if any bills exist in the system (for dynamic weight calculation)."""
        result = await self.db.scalar(
            select(func.count(ParliamentBill.id)).limit(1)
        )
        return (result or 0) > 0

    async def upsert(self, bill_data: dict) -> ParliamentBill:
        """Insert or update bill by external ID."""
        external_id = bill_data.get("external_id")
        if external_id:
            existing = await self.get_by_external_id(external_id)
            if existing:
                for key, value in bill_data.items():
                    if hasattr(existing, key) and key != "id":
                        setattr(existing, key, value)
                existing.scraped_at = datetime.utcnow()
                await self.db.commit()
                await self.db.refresh(existing)
                return existing

        bill = ParliamentBill(**bill_data)
        bill.scraped_at = datetime.utcnow()
        self.db.add(bill)
        await self.db.commit()
        await self.db.refresh(bill)
        return bill

    async def add_sponsor(
        self, bill_id: UUID, mp_id: UUID, sponsor_type: str = "co-sponsor"
    ) -> BillSponsor:
        """Add a sponsor to a bill."""
        # Check if already exists
        existing = await self.db.execute(
            select(BillSponsor).where(
                BillSponsor.bill_id == bill_id,
                BillSponsor.mp_id == mp_id,
            )
        )
        if existing.scalar_one_or_none():
            return existing.scalar_one_or_none()

        sponsor = BillSponsor(
            bill_id=bill_id,
            mp_id=mp_id,
            sponsor_type=sponsor_type,
        )
        self.db.add(sponsor)
        await self.db.commit()
        await self.db.refresh(sponsor)
        return sponsor


class CommitteeRepository:
    """Repository for Parliament Committee database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, committee_id: UUID) -> Optional[ParliamentCommittee]:
        """Get committee by ID with memberships."""
        result = await self.db.execute(
            select(ParliamentCommittee)
            .options(selectinload(ParliamentCommittee.memberships))
            .where(ParliamentCommittee.id == committee_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[ParliamentCommittee]:
        """Get committee by parliament website ID."""
        result = await self.db.execute(
            select(ParliamentCommittee).where(
                ParliamentCommittee.external_id == external_id
            )
        )
        return result.scalar_one_or_none()

    async def list_committees(
        self,
        chamber: Optional[str] = None,
        committee_type: Optional[str] = None,
        is_active: bool = True,
    ) -> list[ParliamentCommittee]:
        """List committees with filters."""
        query = select(ParliamentCommittee)

        filters = []
        if chamber:
            filters.append(ParliamentCommittee.chamber == chamber)
        if committee_type:
            filters.append(ParliamentCommittee.committee_type == committee_type)
        if is_active is not None:
            filters.append(ParliamentCommittee.is_active == is_active)

        if filters:
            query = query.where(and_(*filters))

        query = query.order_by(ParliamentCommittee.name_en)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_by_mp(self, mp_id: UUID, is_current: bool = True) -> list[dict]:
        """List committees for an MP with their roles."""
        query = (
            select(ParliamentCommittee, CommitteeMembership)
            .join(CommitteeMembership, CommitteeMembership.committee_id == ParliamentCommittee.id)
            .where(CommitteeMembership.mp_id == mp_id)
        )

        if is_current:
            query = query.where(CommitteeMembership.is_current == True)

        result = await self.db.execute(query)

        committees = []
        for row in result.all():
            committee, membership = row
            committees.append({
                "committee": committee.to_dict(),
                "role": membership.role,
                "attendance_pct": membership.attendance_pct,
                "meetings_attended": membership.meetings_attended,
                "meetings_total": membership.meetings_total,
            })

        return committees

    async def upsert(self, committee_data: dict) -> ParliamentCommittee:
        """Insert or update committee by external ID."""
        external_id = committee_data.get("external_id")
        if external_id:
            existing = await self.get_by_external_id(external_id)
            if existing:
                for key, value in committee_data.items():
                    if hasattr(existing, key) and key != "id":
                        setattr(existing, key, value)
                await self.db.commit()
                await self.db.refresh(existing)
                return existing

        committee = ParliamentCommittee(**committee_data)
        self.db.add(committee)
        await self.db.commit()
        await self.db.refresh(committee)
        return committee

    async def upsert_membership(
        self,
        committee_id: UUID,
        mp_id: UUID,
        role: str,
        attendance_data: Optional[dict] = None,
    ) -> CommitteeMembership:
        """Insert or update committee membership."""
        # Check for existing
        result = await self.db.execute(
            select(CommitteeMembership).where(
                CommitteeMembership.committee_id == committee_id,
                CommitteeMembership.mp_id == mp_id,
                CommitteeMembership.is_current == True,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.role = role
            if attendance_data:
                existing.meetings_total = attendance_data.get("meetings_total", existing.meetings_total)
                existing.meetings_attended = attendance_data.get("meetings_attended", existing.meetings_attended)
                if existing.meetings_total > 0:
                    existing.attendance_pct = (existing.meetings_attended / existing.meetings_total) * 100
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        membership = CommitteeMembership(
            committee_id=committee_id,
            mp_id=mp_id,
            role=role,
            joined_date=date.today(),
        )
        if attendance_data:
            membership.meetings_total = attendance_data.get("meetings_total", 0)
            membership.meetings_attended = attendance_data.get("meetings_attended", 0)
            if membership.meetings_total > 0:
                membership.attendance_pct = (membership.meetings_attended / membership.meetings_total) * 100

        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(membership)
        return membership

    async def count_mp_roles(self, mp_id: UUID) -> dict:
        """Count committee roles for an MP."""
        result = await self.db.execute(
            select(CommitteeMembership.role, func.count(CommitteeMembership.id))
            .where(
                CommitteeMembership.mp_id == mp_id,
                CommitteeMembership.is_current == True,
            )
            .group_by(CommitteeMembership.role)
        )
        return {row[0]: row[1] for row in result.all()}

    async def get_average_attendance(self, mp_id: UUID) -> Optional[float]:
        """Get average committee attendance for an MP."""
        result = await self.db.execute(
            select(func.avg(CommitteeMembership.attendance_pct))
            .where(
                CommitteeMembership.mp_id == mp_id,
                CommitteeMembership.is_current == True,
                CommitteeMembership.attendance_pct.isnot(None),
            )
        )
        return result.scalar()

    async def has_any_data(self) -> bool:
        """Check if any committee memberships exist (for dynamic weight calculation)."""
        result = await self.db.scalar(
            select(func.count(CommitteeMembership.id)).limit(1)
        )
        return (result or 0) > 0


class QuestionRepository:
    """Repository for Parliamentary Question database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, question_id: UUID) -> Optional[ParliamentQuestion]:
        """Get question by ID."""
        result = await self.db.execute(
            select(ParliamentQuestion).where(ParliamentQuestion.id == question_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[ParliamentQuestion]:
        """Get question by parliament website ID."""
        result = await self.db.execute(
            select(ParliamentQuestion).where(
                ParliamentQuestion.external_id == external_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_mp(
        self,
        mp_id: UUID,
        question_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[ParliamentQuestion]:
        """List questions asked by an MP."""
        query = select(ParliamentQuestion).where(ParliamentQuestion.mp_id == mp_id)

        if question_type:
            query = query.where(ParliamentQuestion.question_type == question_type)

        query = query.order_by(ParliamentQuestion.question_date.desc().nullslast())
        query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_answered_by_mp(
        self, mp_id: UUID, limit: int = 50
    ) -> list[ParliamentQuestion]:
        """List questions answered by an MP (ministers)."""
        result = await self.db.execute(
            select(ParliamentQuestion)
            .where(ParliamentQuestion.answered_by_mp_id == mp_id)
            .order_by(ParliamentQuestion.answer_date.desc().nullslast())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_mp(self, mp_id: UUID) -> dict:
        """Count questions by type for an MP."""
        result = await self.db.execute(
            select(ParliamentQuestion.question_type, func.count(ParliamentQuestion.id))
            .where(ParliamentQuestion.mp_id == mp_id)
            .group_by(ParliamentQuestion.question_type)
        )
        counts = {row[0]: row[1] for row in result.all()}
        counts["total"] = sum(counts.values())
        return counts

    async def count_answered_by_mp(self, mp_id: UUID) -> int:
        """Count questions answered by an MP."""
        result = await self.db.execute(
            select(func.count(ParliamentQuestion.id))
            .where(ParliamentQuestion.answered_by_mp_id == mp_id)
        )
        return result.scalar() or 0

    async def has_any_data(self) -> bool:
        """Check if any questions exist in the system (for dynamic weight calculation)."""
        result = await self.db.scalar(
            select(func.count(ParliamentQuestion.id)).limit(1)
        )
        return (result or 0) > 0

    async def upsert(self, question_data: dict) -> ParliamentQuestion:
        """Insert or update question by external ID."""
        external_id = question_data.get("external_id")
        if external_id:
            existing = await self.get_by_external_id(external_id)
            if existing:
                for key, value in question_data.items():
                    if hasattr(existing, key) and key != "id":
                        setattr(existing, key, value)
                existing.scraped_at = datetime.utcnow()
                await self.db.commit()
                await self.db.refresh(existing)
                return existing

        question = ParliamentQuestion(**question_data)
        question.scraped_at = datetime.utcnow()
        self.db.add(question)
        await self.db.commit()
        await self.db.refresh(question)
        return question


class AttendanceRepository:
    """Repository for Session Attendance database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_attendance_record(
        self, mp_id: UUID, session_date: date, session_type: Optional[str] = None
    ) -> Optional[SessionAttendance]:
        """Get specific attendance record."""
        query = select(SessionAttendance).where(
            SessionAttendance.mp_id == mp_id,
            SessionAttendance.session_date == session_date,
        )
        if session_type:
            query = query.where(SessionAttendance.session_type == session_type)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_by_mp(
        self,
        mp_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
    ) -> list[SessionAttendance]:
        """List attendance records for an MP."""
        query = select(SessionAttendance).where(SessionAttendance.mp_id == mp_id)

        if start_date:
            query = query.where(SessionAttendance.session_date >= start_date)
        if end_date:
            query = query.where(SessionAttendance.session_date <= end_date)

        query = query.order_by(SessionAttendance.session_date.desc())
        query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_attendance_stats(self, mp_id: UUID) -> dict:
        """Get attendance statistics for an MP."""
        from sqlalchemy import case
        result = await self.db.execute(
            select(
                func.count(SessionAttendance.id).label("total"),
                func.sum(
                    case((SessionAttendance.present == True, 1), else_=0)
                ).label("attended"),
            )
            .where(SessionAttendance.mp_id == mp_id)
        )
        row = result.one()
        total = row.total or 0
        attended = row.attended or 0

        return {
            "sessions_total": total,
            "sessions_attended": attended,
            "attendance_pct": (attended / total * 100) if total > 0 else None,
        }

    async def record_attendance(
        self,
        mp_id: UUID,
        session_date: date,
        present: bool,
        session_type: Optional[str] = None,
        chamber: Optional[str] = None,
        term: Optional[str] = None,
    ) -> SessionAttendance:
        """Record attendance for a session (upsert)."""
        existing = await self.get_attendance_record(mp_id, session_date, session_type)

        if existing:
            existing.present = present
            existing.scraped_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        attendance = SessionAttendance(
            mp_id=mp_id,
            session_date=session_date,
            present=present,
            session_type=session_type,
            chamber=chamber,
            term=term,
            scraped_at=datetime.utcnow(),
        )
        self.db.add(attendance)
        await self.db.commit()
        await self.db.refresh(attendance)
        return attendance

    async def bulk_record_attendance(self, records: list[dict]) -> int:
        """Bulk record attendance from scraping."""
        count = 0
        for record in records:
            await self.record_attendance(
                mp_id=record["mp_id"],
                session_date=record["session_date"],
                present=record["present"],
                session_type=record.get("session_type"),
                chamber=record.get("chamber"),
                term=record.get("term"),
            )
            count += 1
        return count

    async def has_any_data(self) -> bool:
        """Check if any attendance records exist (for dynamic weight calculation)."""
        result = await self.db.scalar(
            select(func.count(SessionAttendance.id)).limit(1)
        )
        return (result or 0) > 0

    async def get_session_dates(
        self, chamber: Optional[str] = None, limit: int = 50
    ) -> list[date]:
        """Get list of session dates."""
        query = select(SessionAttendance.session_date).distinct()
        if chamber:
            query = query.where(SessionAttendance.chamber == chamber)
        query = query.order_by(SessionAttendance.session_date.desc()).limit(limit)

        result = await self.db.execute(query)
        return [row[0] for row in result.all()]
