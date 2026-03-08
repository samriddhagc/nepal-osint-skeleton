"""Company registration service for OCR data ingestion and querying."""
import asyncio
import logging
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.ocr_scraper import OCRScraper
from app.ingestion.camis_client import CAMISClient
from app.ingestion.camis_enricher import CAMISEnricher
from app.ingestion.director_extractor import DirectorExtractor
from app.repositories.company import CompanyRepository

logger = logging.getLogger(__name__)


class CompanyService:
    """Service for company registration operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = CompanyRepository(db)

    async def ingest_companies(
        self,
        start: int = 1,
        end: int = 100,
        delay: float = 1.0,
        max_empty_streak: int = 50,
    ) -> dict:
        """
        Run OCR scraper for a range of registration numbers and upsert to database.

        Returns ingestion stats dict.
        """
        logger.info(f"Starting OCR company ingestion: reg #{start} to #{end}")

        # Run sync scraper in executor
        def _scrape():
            scraper = OCRScraper(delay=delay)
            return scraper.scrape_range(start=start, end=end, max_empty_streak=max_empty_streak)

        loop = asyncio.get_event_loop()
        companies = await loop.run_in_executor(None, _scrape)

        stats = {
            "source": "ocr.gov.np",
            "range_start": start,
            "range_end": end,
            "queries_made": end - start + 1,
            "fetched": len(companies),
            "new": 0,
            "updated": 0,
            "errors": [],
        }

        for company in companies:
            try:
                external_id = OCRScraper.generate_external_id(
                    company.registration_number,
                    company.name_english,
                    company.registration_date_bs,
                )
                type_category = OCRScraper.classify_company_type(company.company_type)
                district = OCRScraper.extract_district(company.company_address)
                province = OCRScraper.extract_province(company.company_address)

                _, created = await self.repo.upsert(
                    external_id=external_id,
                    registration_number=company.registration_number,
                    name_english=company.name_english,
                    name_nepali=company.name_nepali,
                    registration_date_bs=company.registration_date_bs,
                    company_type=company.company_type,
                    company_type_category=type_category,
                    company_address=company.company_address,
                    district=district,
                    province=province,
                    last_communication_bs=company.last_communication_bs,
                    raw_data=company.raw_data,
                )

                if created:
                    stats["new"] += 1
                else:
                    stats["updated"] += 1

            except Exception as e:
                error_msg = f"Error ingesting company reg #{company.registration_number} ({company.name_english}): {e}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        logger.info(
            f"OCR ingestion complete: {stats['fetched']} fetched, "
            f"{stats['new']} new, {stats['updated']} updated, "
            f"{len(stats['errors'])} errors"
        )
        return stats

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
    ) -> dict:
        """List companies with filtering and pagination."""
        filter_kwargs = dict(
            name=name,
            registration_number=registration_number,
            company_type_category=company_type_category,
            district=district,
            province=province,
            search=search,
        )

        companies = await self.repo.list_companies(**filter_kwargs, page=page, per_page=per_page)
        total = await self.repo.count(**filter_kwargs)

        return {
            "companies": [c.to_dict() for c in companies],
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_more": (page * per_page) < total,
        }

    async def get_company(self, company_id: str) -> Optional[dict]:
        """Get single company by ID."""
        try:
            uid = UUID(company_id)
        except (ValueError, TypeError):
            return None
        company = await self.repo.get_by_id(uid)
        if not company:
            return None
        return company.to_dict()

    async def search_companies(self, query: str, limit: int = 20) -> list:
        """Search companies by name."""
        companies = await self.repo.search_by_name(query, limit=limit)
        return [c.to_dict() for c in companies]

    async def get_stats(self) -> dict:
        """Get aggregate company statistics."""
        return await self.repo.get_stats()

    # ---- CAMIS Enrichment ----

    async def enrich_from_camis(self, limit: int = 100, workers: int = 8, min_reg_number: int = 0) -> dict:
        """Enrich un-enriched companies with PAN + metadata from CAMIS API."""
        enricher = CAMISEnricher(self.db, workers=workers)
        return await enricher.enrich_batch(limit=limit, min_reg_number=min_reg_number)

    async def search_camis(self, name: Optional[str] = None, reg_number: Optional[str] = None) -> list[dict]:
        """Search companies via CAMIS API (broader than our local DB)."""
        client = CAMISClient()
        return await client.search_companies(name=name, reg_number=reg_number)

    # ---- Directors ----

    async def get_company_directors(self, company_id: str, source: Optional[str] = None) -> list[dict]:
        """Get directors for a company."""
        try:
            uid = UUID(company_id)
        except (ValueError, TypeError):
            return []
        directors = await self.repo.get_directors(uid, source=source)
        return [d.to_dict() for d in directors]

    async def get_company_full(self, company_id: str) -> Optional[dict]:
        """Get company with its directors."""
        company = await self.get_company(company_id)
        if not company:
            return None
        directors = await self.get_company_directors(company_id)
        return {"company": company, "directors": directors}

    async def extract_directors_from_news(self, limit: int = 500) -> dict:
        """Run NER-based director extraction on recent stories."""
        extractor = DirectorExtractor(self.db)
        return await extractor.process_recent_stories(limit=limit)
