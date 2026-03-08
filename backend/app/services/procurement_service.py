"""Procurement service for government contract ingestion and querying."""
import asyncio
import logging
from dataclasses import asdict
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.bolpatra_scraper import BolpatraScraper
from app.repositories.procurement import ProcurementRepository
# ProcurementCompanyLinkageService excluded from skeleton

logger = logging.getLogger(__name__)


class ProcurementService:
    """Service for government procurement contract operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ProcurementRepository(db)

    async def ingest_contracts(self, page_size: int = 5000) -> dict:
        """
        Run Bolpatra scraper and upsert all contracts to database.

        Returns ingestion stats dict.
        """
        logger.info("Starting Bolpatra contract ingestion")

        # Run sync scraper in executor
        def _scrape():
            scraper = BolpatraScraper(delay=0.5)
            return scraper.scrape_contracts(page_size=page_size)

        loop = asyncio.get_event_loop()
        contracts = await loop.run_in_executor(None, _scrape)

        stats = {
            "source": "bolpatra.gov.np",
            "fetched": len(contracts),
            "new": 0,
            "updated": 0,
            "errors": [],
        }

        for contract in contracts:
            try:
                external_id = BolpatraScraper.generate_external_id(
                    contract.ifb_number, contract.procuring_entity
                )
                award_date = BolpatraScraper._parse_date(contract.contract_award_date or "")
                fiscal_year = BolpatraScraper._extract_fiscal_year(contract.ifb_number)

                _, created = await self.repo.upsert(
                    external_id=external_id,
                    ifb_number=contract.ifb_number,
                    project_name=contract.project_name,
                    procuring_entity=contract.procuring_entity,
                    procurement_type=contract.procurement_type,
                    contractor_name=contract.contractor_name,
                    contract_award_date=award_date,
                    contract_amount_npr=contract.contract_amount_npr,
                    fiscal_year_bs=fiscal_year,
                    raw_data=contract.raw_data,
                )

                if created:
                    stats["new"] += 1
                else:
                    stats["updated"] += 1

            except Exception as e:
                error_msg = f"Error ingesting contract {contract.ifb_number}: {e}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)

        logger.info(
            f"Bolpatra ingestion complete: {stats['fetched']} fetched, "
            f"{stats['new']} new, {stats['updated']} updated, "
            f"{len(stats['errors'])} errors"
        )

        # ProcurementCompanyLinkageService excluded from skeleton

        return stats

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
    ) -> dict:
        """List contracts with filtering and pagination."""
        filter_kwargs = dict(
            procuring_entity=procuring_entity,
            procurement_type=procurement_type,
            contractor_name=contractor_name,
            district=district,
            fiscal_year_bs=fiscal_year_bs,
            min_amount=min_amount,
            max_amount=max_amount,
            search=search,
        )

        contracts = await self.repo.list_contracts(
            **filter_kwargs,
            page=page,
            per_page=per_page,
        )
        total = await self.repo.count(**filter_kwargs)

        return {
            "contracts": [c.to_dict() for c in contracts],
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_more": (page * per_page) < total,
        }

    async def get_contract(self, contract_id: str) -> Optional[dict]:
        """Get single contract by ID."""
        try:
            uid = UUID(contract_id)
        except (ValueError, TypeError):
            return None

        contract = await self.repo.get_by_id(uid)
        if not contract:
            return None
        return contract.to_dict()

    async def get_stats(self) -> dict:
        """Get aggregate procurement statistics."""
        return await self.repo.get_stats()

    async def get_top_contractors(self, limit: int = 10) -> list:
        """Get top contractors by total contract value."""
        return await self.repo.get_top_contractors(limit=limit)

    async def get_top_procuring_entities(self, limit: int = 10) -> list:
        """Get top procuring entities by total contract value."""
        return await self.repo.get_top_procuring_entities(limit=limit)
