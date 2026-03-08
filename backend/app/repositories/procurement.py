"""Government procurement contract repository for database operations."""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import GovtContract


class ProcurementRepository:
    """Repository for GovtContract database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, contract_id: UUID) -> Optional[GovtContract]:
        """Get contract by ID."""
        result = await self.db.execute(
            select(GovtContract).where(GovtContract.id == contract_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[GovtContract]:
        """Get contract by external ID (hash)."""
        result = await self.db.execute(
            select(GovtContract).where(GovtContract.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def exists(self, external_id: str) -> bool:
        """Check if contract exists by external ID."""
        result = await self.db.execute(
            select(func.count(GovtContract.id)).where(
                GovtContract.external_id == external_id
            )
        )
        return (result.scalar() or 0) > 0

    async def create(self, contract: GovtContract) -> GovtContract:
        """Create a new contract."""
        self.db.add(contract)
        await self.db.commit()
        await self.db.refresh(contract)
        return contract

    async def update(self, contract: GovtContract) -> GovtContract:
        """Update an existing contract."""
        contract.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(contract)
        return contract

    async def upsert(
        self,
        external_id: str,
        ifb_number: str,
        project_name: str,
        procuring_entity: str,
        procurement_type: str,
        contractor_name: str,
        contract_award_date=None,
        contract_amount_npr: Optional[float] = None,
        district: Optional[str] = None,
        province: Optional[int] = None,
        fiscal_year_bs: Optional[str] = None,
        source_url: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> tuple[GovtContract, bool]:
        """
        Create or update contract.
        Returns (contract, created) tuple.
        """
        existing = await self.get_by_external_id(external_id)

        if existing:
            # Update existing record
            existing.ifb_number = ifb_number
            existing.project_name = project_name
            existing.procuring_entity = procuring_entity
            existing.procurement_type = procurement_type
            existing.contractor_name = contractor_name
            if contract_award_date is not None:
                existing.contract_award_date = contract_award_date
            if contract_amount_npr is not None:
                existing.contract_amount_npr = contract_amount_npr
            if district is not None:
                existing.district = district
            if province is not None:
                existing.province = province
            if fiscal_year_bs is not None:
                existing.fiscal_year_bs = fiscal_year_bs
            if source_url is not None:
                existing.source_url = source_url
            if raw_data is not None:
                existing.raw_data = raw_data
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing)
            return existing, False

        # Create new
        contract = GovtContract(
            external_id=external_id,
            ifb_number=ifb_number,
            project_name=project_name,
            procuring_entity=procuring_entity,
            procurement_type=procurement_type,
            contractor_name=contractor_name,
            contract_award_date=contract_award_date,
            contract_amount_npr=contract_amount_npr,
            district=district,
            province=province,
            fiscal_year_bs=fiscal_year_bs,
            source_url=source_url,
            raw_data=raw_data,
            fetched_at=datetime.now(timezone.utc),
        )
        self.db.add(contract)
        await self.db.commit()
        await self.db.refresh(contract)
        return contract, True

    async def list_contracts(
        self,
        procuring_entity: Optional[str] = None,
        procurement_type: Optional[str] = None,
        contractor_name: Optional[str] = None,
        district: Optional[str] = None,
        fiscal_year_bs: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> List[GovtContract]:
        """List contracts with filters and pagination."""
        query = select(GovtContract)

        conditions = self._build_conditions(
            procuring_entity=procuring_entity,
            procurement_type=procurement_type,
            contractor_name=contractor_name,
            district=district,
            fiscal_year_bs=fiscal_year_bs,
            min_amount=min_amount,
            max_amount=max_amount,
            search=search,
        )

        if conditions:
            query = query.where(and_(*conditions))

        offset = (page - 1) * per_page
        query = query.order_by(desc(GovtContract.contract_award_date)).offset(offset).limit(per_page)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        procuring_entity: Optional[str] = None,
        procurement_type: Optional[str] = None,
        contractor_name: Optional[str] = None,
        district: Optional[str] = None,
        fiscal_year_bs: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count contracts with filters."""
        query = select(func.count(GovtContract.id))

        conditions = self._build_conditions(
            procuring_entity=procuring_entity,
            procurement_type=procurement_type,
            contractor_name=contractor_name,
            district=district,
            fiscal_year_bs=fiscal_year_bs,
            min_amount=min_amount,
            max_amount=max_amount,
            search=search,
        )

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        return result.scalar() or 0

    def _build_conditions(
        self,
        procuring_entity: Optional[str] = None,
        procurement_type: Optional[str] = None,
        contractor_name: Optional[str] = None,
        district: Optional[str] = None,
        fiscal_year_bs: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        search: Optional[str] = None,
    ) -> list:
        """Build filter conditions for queries."""
        conditions = []
        if procuring_entity:
            conditions.append(GovtContract.procuring_entity.ilike(f"%{procuring_entity}%"))
        if procurement_type:
            conditions.append(GovtContract.procurement_type == procurement_type)
        if contractor_name:
            conditions.append(GovtContract.contractor_name.ilike(f"%{contractor_name}%"))
        if district:
            conditions.append(GovtContract.district == district)
        if fiscal_year_bs:
            conditions.append(GovtContract.fiscal_year_bs == fiscal_year_bs)
        if min_amount is not None:
            conditions.append(GovtContract.contract_amount_npr >= min_amount)
        if max_amount is not None:
            conditions.append(GovtContract.contract_amount_npr <= max_amount)
        if search:
            conditions.append(
                GovtContract.project_name.ilike(f"%{search}%")
            )
        return conditions

    async def get_stats(self) -> dict:
        """Get aggregate statistics on contracts."""
        # Total count
        total_result = await self.db.execute(
            select(func.count(GovtContract.id))
        )
        total = total_result.scalar() or 0

        # Total value
        value_result = await self.db.execute(
            select(func.sum(GovtContract.contract_amount_npr))
        )
        total_value = value_result.scalar() or 0.0

        # Count by procurement type
        type_query = select(
            GovtContract.procurement_type,
            func.count(GovtContract.id),
            func.sum(GovtContract.contract_amount_npr),
        ).group_by(GovtContract.procurement_type)
        type_result = await self.db.execute(type_query)
        by_type = [
            {"type": row[0], "count": row[1], "total_value": row[2] or 0.0}
            for row in type_result.all()
        ]

        # Count by fiscal year
        fy_query = select(
            GovtContract.fiscal_year_bs,
            func.count(GovtContract.id),
            func.sum(GovtContract.contract_amount_npr),
        ).where(
            GovtContract.fiscal_year_bs.isnot(None)
        ).group_by(GovtContract.fiscal_year_bs).order_by(desc(GovtContract.fiscal_year_bs))
        fy_result = await self.db.execute(fy_query)
        by_fiscal_year = [
            {"fiscal_year": row[0], "count": row[1], "total_value": row[2] or 0.0}
            for row in fy_result.all()
        ]

        return {
            "total_contracts": total,
            "total_value_npr": total_value,
            "by_procurement_type": by_type,
            "by_fiscal_year": by_fiscal_year,
        }

    async def get_top_contractors(self, limit: int = 10) -> list:
        """Get top contractors by total contract value."""
        query = select(
            GovtContract.contractor_name,
            func.count(GovtContract.id).label("contract_count"),
            func.coalesce(func.sum(GovtContract.contract_amount_npr), 0.0).label("total_value"),
        ).group_by(
            GovtContract.contractor_name
        ).order_by(
            desc(func.coalesce(func.sum(GovtContract.contract_amount_npr), 0.0))
        ).limit(limit)

        result = await self.db.execute(query)
        return [
            {
                "contractor_name": row[0],
                "contract_count": row[1],
                "total_value": row[2] or 0.0,
            }
            for row in result.all()
        ]

    async def get_top_procuring_entities(self, limit: int = 10) -> list:
        """Get top procuring entities by total contract value."""
        query = select(
            GovtContract.procuring_entity,
            func.count(GovtContract.id).label("contract_count"),
            func.coalesce(func.sum(GovtContract.contract_amount_npr), 0.0).label("total_value"),
        ).group_by(
            GovtContract.procuring_entity
        ).order_by(
            desc(func.coalesce(func.sum(GovtContract.contract_amount_npr), 0.0))
        ).limit(limit)

        result = await self.db.execute(query)
        return [
            {
                "procuring_entity": row[0],
                "contract_count": row[1],
                "total_value": row[2] or 0.0,
            }
            for row in result.all()
        ]
