"""Company registration repository for database operations."""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import CompanyRegistration, CompanyDirector


class CompanyRepository:
    """Repository for CompanyRegistration database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, company_id: UUID) -> Optional[CompanyRegistration]:
        """Get company by ID."""
        result = await self.db.execute(
            select(CompanyRegistration).where(CompanyRegistration.id == company_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[CompanyRegistration]:
        """Get company by external ID (hash)."""
        result = await self.db.execute(
            select(CompanyRegistration).where(CompanyRegistration.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def exists(self, external_id: str) -> bool:
        """Check if company exists by external ID."""
        result = await self.db.execute(
            select(func.count(CompanyRegistration.id)).where(
                CompanyRegistration.external_id == external_id
            )
        )
        return (result.scalar() or 0) > 0

    async def upsert(
        self,
        external_id: str,
        registration_number: int,
        name_english: str,
        name_nepali: Optional[str] = None,
        registration_date_bs: Optional[str] = None,
        registration_date_ad=None,
        company_type: Optional[str] = None,
        company_type_category: Optional[str] = None,
        company_address: Optional[str] = None,
        district: Optional[str] = None,
        province: Optional[str] = None,
        last_communication_bs: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> tuple[CompanyRegistration, bool]:
        """
        Create or update company registration.
        Returns (company, created) tuple.
        """
        existing = await self.get_by_external_id(external_id)

        if existing:
            existing.name_nepali = name_nepali or existing.name_nepali
            existing.company_type = company_type or existing.company_type
            existing.company_type_category = company_type_category or existing.company_type_category
            existing.company_address = company_address or existing.company_address
            existing.district = district or existing.district
            existing.province = province or existing.province
            if last_communication_bs:
                existing.last_communication_bs = last_communication_bs
            if raw_data:
                existing.raw_data = raw_data
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing)
            return existing, False

        company = CompanyRegistration(
            external_id=external_id,
            registration_number=registration_number,
            name_english=name_english,
            name_nepali=name_nepali,
            registration_date_bs=registration_date_bs,
            registration_date_ad=registration_date_ad,
            company_type=company_type,
            company_type_category=company_type_category,
            company_address=company_address,
            district=district,
            province=province,
            last_communication_bs=last_communication_bs,
            raw_data=raw_data,
            fetched_at=datetime.now(timezone.utc),
        )
        self.db.add(company)
        await self.db.commit()
        await self.db.refresh(company)
        return company, True

    async def list_companies(
        self,
        name: Optional[str] = None,
        registration_number: Optional[int] = None,
        company_type_category: Optional[str] = None,
        district: Optional[str] = None,
        province: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> List[CompanyRegistration]:
        """List companies with filters and pagination."""
        query = select(CompanyRegistration)
        conditions = self._build_conditions(
            name=name,
            registration_number=registration_number,
            company_type_category=company_type_category,
            district=district,
            province=province,
            search=search,
        )
        if conditions:
            query = query.where(and_(*conditions))

        offset = (page - 1) * per_page
        query = query.order_by(CompanyRegistration.registration_number).offset(offset).limit(per_page)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        name: Optional[str] = None,
        registration_number: Optional[int] = None,
        company_type_category: Optional[str] = None,
        district: Optional[str] = None,
        province: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count companies with filters."""
        query = select(func.count(CompanyRegistration.id))
        conditions = self._build_conditions(
            name=name,
            registration_number=registration_number,
            company_type_category=company_type_category,
            district=district,
            province=province,
            search=search,
        )
        if conditions:
            query = query.where(and_(*conditions))
        result = await self.db.execute(query)
        return result.scalar() or 0

    def _build_conditions(
        self,
        name: Optional[str] = None,
        registration_number: Optional[int] = None,
        company_type_category: Optional[str] = None,
        district: Optional[str] = None,
        province: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list:
        """Build filter conditions."""
        conditions = []
        if name:
            conditions.append(CompanyRegistration.name_english.ilike(f"%{name}%"))
        if registration_number is not None:
            conditions.append(CompanyRegistration.registration_number == registration_number)
        if company_type_category:
            conditions.append(CompanyRegistration.company_type_category == company_type_category)
        if district:
            conditions.append(CompanyRegistration.district.ilike(f"%{district}%"))
        if province:
            conditions.append(CompanyRegistration.province.ilike(f"%{province}%"))
        if search:
            conditions.append(
                CompanyRegistration.name_english.ilike(f"%{search}%")
            )
        return conditions

    async def get_stats(self) -> dict:
        """Get aggregate statistics on registered companies."""
        total_result = await self.db.execute(
            select(func.count(CompanyRegistration.id))
        )
        total = total_result.scalar() or 0

        # By type category
        type_query = select(
            CompanyRegistration.company_type_category,
            func.count(CompanyRegistration.id),
        ).group_by(CompanyRegistration.company_type_category)
        type_result = await self.db.execute(type_query)
        by_type = {row[0] or "Unknown": row[1] for row in type_result.all()}

        # By district (top 20)
        district_query = select(
            CompanyRegistration.district,
            func.count(CompanyRegistration.id),
        ).where(
            CompanyRegistration.district.isnot(None)
        ).group_by(
            CompanyRegistration.district
        ).order_by(
            desc(func.count(CompanyRegistration.id))
        ).limit(20)
        district_result = await self.db.execute(district_query)
        by_district = {row[0]: row[1] for row in district_result.all()}

        # Max registration number ingested
        max_reg_result = await self.db.execute(
            select(func.max(CompanyRegistration.registration_number))
        )
        max_reg = max_reg_result.scalar() or 0

        return {
            "total_companies": total,
            "max_registration_number": max_reg,
            "by_type_category": by_type,
            "by_district": by_district,
        }

    async def search_by_name(self, query: str, limit: int = 20) -> List[CompanyRegistration]:
        """Full-text search companies by English or Nepali name."""
        stmt = select(CompanyRegistration).where(
            CompanyRegistration.name_english.ilike(f"%{query}%")
        ).order_by(CompanyRegistration.name_english).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_registration_number(self, reg_number: int) -> Optional[CompanyRegistration]:
        """Get company by OCR registration number."""
        result = await self.db.execute(
            select(CompanyRegistration).where(
                CompanyRegistration.registration_number == reg_number
            )
        )
        return result.scalar_one_or_none()

    # ---- Director methods ----

    async def get_directors(
        self,
        company_id: UUID,
        source: Optional[str] = None,
    ) -> List[CompanyDirector]:
        """Get directors for a company, optionally filtered by source."""
        stmt = select(CompanyDirector).where(CompanyDirector.company_id == company_id)
        if source:
            stmt = stmt.where(CompanyDirector.source == source)
        stmt = stmt.order_by(CompanyDirector.confidence.desc(), CompanyDirector.name_en)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def upsert_director(
        self,
        name_en: str,
        source: str,
        company_id: Optional[UUID] = None,
        name_np: Optional[str] = None,
        role: Optional[str] = None,
        company_name_hint: Optional[str] = None,
        source_url: Optional[str] = None,
        confidence: float = 1.0,
        pan: Optional[str] = None,
        citizenship_no: Optional[str] = None,
        appointed_date=None,
        resigned_date=None,
        raw_data: Optional[dict] = None,
    ) -> tuple[CompanyDirector, bool]:
        """Create or update a director record. Deduplicates by name + company + role + source."""
        conditions = [
            CompanyDirector.name_en.ilike(name_en),
            CompanyDirector.source == source,
        ]
        if company_id:
            conditions.append(CompanyDirector.company_id == company_id)
        if role:
            conditions.append(CompanyDirector.role == role)

        stmt = select(CompanyDirector).where(and_(*conditions)).limit(1)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update with higher confidence or newer data
            if confidence > existing.confidence:
                existing.confidence = confidence
            if pan and not existing.pan:
                existing.pan = pan
            if citizenship_no and not existing.citizenship_no:
                existing.citizenship_no = citizenship_no
            if source_url and not existing.source_url:
                existing.source_url = source_url
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing)
            return existing, False

        director = CompanyDirector(
            company_id=company_id,
            name_en=name_en,
            name_np=name_np,
            role=role,
            company_name_hint=company_name_hint,
            source=source,
            source_url=source_url,
            confidence=confidence,
            pan=pan,
            citizenship_no=citizenship_no,
            appointed_date=appointed_date,
            resigned_date=resigned_date,
            raw_data=raw_data,
            fetched_at=datetime.now(timezone.utc),
        )
        self.db.add(director)
        await self.db.commit()
        await self.db.refresh(director)
        return director, True

    async def get_unenriched(self, limit: int = 100) -> List[CompanyRegistration]:
        """Get companies not yet enriched from CAMIS."""
        stmt = (
            select(CompanyRegistration)
            .where(CompanyRegistration.camis_enriched == False)  # noqa: E712
            .order_by(CompanyRegistration.registration_number)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
