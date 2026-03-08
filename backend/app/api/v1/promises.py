"""API routes for manifesto promise tracking."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_dev
from app.models.promise import ManifestoPromise

router = APIRouter(prefix="/promises", tags=["promises"])


class PromiseOut(BaseModel):
    id: str
    promise_id: str
    party: str
    election_year: str
    category: str
    promise: str
    detail: Optional[str] = None
    source: Optional[str] = None
    status: str
    status_detail: Optional[str] = None
    evidence_urls: Optional[str] = None
    last_checked_at: Optional[str] = None
    status_changed_at: Optional[str] = None

    class Config:
        from_attributes = True


class PromiseStatusUpdate(BaseModel):
    status: str
    status_detail: Optional[str] = None
    evidence_urls: Optional[str] = None


class PromiseBulkIngest(BaseModel):
    """Bulk ingest from local agent."""
    updates: list[dict]  # [{promise_id, status, status_detail, evidence_urls}]


@router.get("", response_model=list[PromiseOut])
async def list_promises(
    party: str = Query("RSP"),
    election_year: str = Query("2082"),
    category: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all manifesto promises, optionally filtered."""
    q = select(ManifestoPromise).where(
        ManifestoPromise.party == party,
        ManifestoPromise.election_year == election_year,
    ).order_by(ManifestoPromise.promise_id)

    if category:
        q = q.where(ManifestoPromise.category == category)
    if status:
        q = q.where(ManifestoPromise.status == status)

    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        PromiseOut(
            id=str(r.id),
            promise_id=r.promise_id,
            party=r.party,
            election_year=r.election_year,
            category=r.category,
            promise=r.promise,
            detail=r.detail,
            source=r.source,
            status=r.status,
            status_detail=r.status_detail,
            evidence_urls=r.evidence_urls,
            last_checked_at=r.last_checked_at.isoformat() if r.last_checked_at else None,
            status_changed_at=r.status_changed_at.isoformat() if r.status_changed_at else None,
        )
        for r in rows
    ]


@router.get("/summary")
async def promise_summary(
    party: str = Query("RSP"),
    election_year: str = Query("2082"),
    db: AsyncSession = Depends(get_db),
):
    """Summary stats for promise tracker widget."""
    q = select(ManifestoPromise).where(
        ManifestoPromise.party == party,
        ManifestoPromise.election_year == election_year,
    )
    result = await db.execute(q)
    rows = result.scalars().all()

    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_category[r.category] = by_category.get(r.category, 0) + 1

    return {
        "total": len(rows),
        "by_status": by_status,
        "by_category": by_category,
        "promises": [
            {
                "promise_id": r.promise_id,
                "category": r.category,
                "promise": r.promise,
                "detail": r.detail,
                "source": r.source,
                "status": r.status,
                "status_detail": r.status_detail,
                "evidence_urls": r.evidence_urls,
                "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
                "status_changed_at": r.status_changed_at.isoformat() if r.status_changed_at else None,
            }
            for r in rows
        ],
    }


@router.post("/ingest")
async def ingest_promise_updates(
    payload: PromiseBulkIngest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """Bulk update promise statuses from local agent."""
    from datetime import datetime, timezone

    updated = 0
    for u in payload.updates:
        pid = u.get("promise_id")
        if not pid:
            continue

        result = await db.execute(
            select(ManifestoPromise).where(ManifestoPromise.promise_id == pid)
        )
        promise = result.scalar_one_or_none()
        if not promise:
            continue

        old_status = promise.status
        new_status = u.get("status", old_status)

        promise.status = new_status
        if u.get("status_detail"):
            promise.status_detail = u["status_detail"]
        if u.get("evidence_urls"):
            promise.evidence_urls = u["evidence_urls"]
        promise.last_checked_at = datetime.now(timezone.utc)
        if new_status != old_status:
            promise.status_changed_at = datetime.now(timezone.utc)
        updated += 1

    await db.commit()
    return {"updated": updated, "total": len(payload.updates)}


@router.post("/seed")
async def seed_promises(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_dev),
):
    """Seed initial RSP manifesto promises (idempotent)."""
    from uuid import uuid4

    # ── VERIFIED against RSP Manifesto (वाचा पत्र 2082) PDF, page-by-page ──
    SEED_DATA = [
        # Governance — from Point 10, 15, 16, 17, 18, 26, 27
        ("G1", "Governance", "Constitutional amendment discussion paper", "Prepare a 'discussion paper' (बहस पत्र) for national consensus on constitutional amendments. Topics include: directly elected executive, fully proportional parliament, MPs not becoming ministers, non-partisan local government, reformed provincial structure.", "Point 10"),
        ("G2", "Governance", "Limit federal ministries to 18 with expert ministers", "Cap ministries at 18. Establish new standard of specialist ('विज्ञ') ministers and expertise-based civil service administration.", "Point 17"),
        ("G3", "Governance", "Party leader term limited to two terms", "Party president cannot hold the top party position for more than two consecutive terms.", "Point 15"),
        ("G4", "Governance", "Reform National Planning Commission into think-tank", "Transform NPC from traditional format into a modern policy research, data, and monitoring-focused think-tank.", "Point 18"),
        ("G5", "Governance", "Professionalize civil service, end political unions in bureaucracy", "Abolish partisan trade unions in civil service. Make administration fully professional, impartial, and accountable.", "Point 7"),
        ("G6", "Governance", "End nepotism in personal secretary appointments", "Bar officials from appointing family members to positions like personal secretary (स्वकीय सचिव) to end nepotism.", "Point 16"),
        ("G7", "Governance", "Classify & reform public institutions", "Classify public enterprises: merge some, bring private-public partnership to some, bring strategic partners into others, decentralize others, or transfer immovable assets to government.", "Point 26"),
        ("G8", "Governance", "Mission-mode (मिसन मोड) public organizations", "Run public projects with clear objectives, fixed budgets, time limits, qualified human resources, and results-based targets.", "Point 27"),
        # Anti-Corruption — from Points 5, 11, 15, 16, 20
        ("AC1", "Anti-Corruption", "Mandatory public asset disclosure before and after office", "Full asset disclosure before taking office and independent audit of wealth change after term ends, for officials and their families.", "Point 16"),
        ("AC2", "Anti-Corruption", "Digital governance with mandatory e-signatures", "Make digital signatures legally mandatory. Digitize all government memos (tippani.gov.np) and directives (paripatra.gov.np). End paper-based file routing.", "Point 5"),
        ("AC3", "Anti-Corruption", "Amend CIAA Act 2048, Constitutional Council Act 2066, Judicial Council Act 2073", "Strengthen independence of constitutional bodies by amending their governing acts to improve capacity, jurisdiction, appointments, and institutional governance.", "Point 11"),
        ("AC4", "Anti-Corruption", "Political party funding from public funds based on vote share", "Provide annual public funding to recognized parties based on vote share. Reform Political Party Act and election laws. Cap party leader tenure.", "Point 15"),
        ("AC5", "Anti-Corruption", "End cartel pricing and rent-seeking via independent regulators", "Create politically independent, professional, transparent regulators to control cartels, unhealthy competition, rent-seeking, and policy exploitation.", "Point 20"),
        # Judiciary — from Points 1, 12, 13, 14, 32
        ("J1", "Judiciary", "Merit-based judicial appointments", "End political influence and quota-based recommendations in Supreme Court and High Court appointments. Shift to meritocracy and competitive system.", "Point 13"),
        ("J2", "Judiciary", "Clear judicial backlog, amend Judicial Code 2046", "Fast-track pending transitional justice cases and implement Judicial Code of 2046 immediately.", "Point 12"),
        ("J3", "Judiciary", "Study live broadcast of court proceedings", "Study options for live or recorded broadcasting of court proceedings to increase judicial transparency.", "Point 14"),
        ("J4", "Judiciary", "Define usury and unfair transactions as economic crimes", "Legally classify meter-byaj (usury) and unfair financial transactions as economic crimes and dismantle networks within five years.", "Point 32"),
        ("J5", "Judiciary", "End caste-based discrimination via enforcement", "Address historical injustice faced by Dalit communities through state policy, legal reform, and active enforcement.", "Point 1"),
        # Economy — from Citizen Contract, Points 19-23, 39
        ("E1", "Economy", "$3,000 per-capita income and $100B economy target", "Raise per-capita income to minimum $3,000 and grow economy to $100 billion within target period (7% real annual growth).", "Citizen Contract \u00a72"),
        ("E2", "Economy", "Progressive tax reform to reduce middle-class burden", "Review 'family burden' tax threshold for middle-class families. End retroactive tax rules. Stop tax evasion with enforcement.", "Point 22"),
        ("E3", "Economy", "Create 12 lakh new formal jobs", "Generate 1.2 million new jobs in IT, construction, tourism, agriculture, mining, sports, and trade to reduce outward migration.", "Citizen Contract \u00a73"),
        ("E4", "Economy", "Break cartels and monopolies", "Build independent regulators to eliminate cartel pricing, rent-seeking, and regulatory capture.", "Point 20"),
        ("E5", "Economy", "Review Indian rupee peg policy", "Conduct study with international experts on the decades-old fixed NPR-INR exchange rate policy.", "Point 23"),
        ("E6", "Economy", "Export electricity, agriculture & computation", "Transform Nepal from raw electricity exporter to also exporting AI/computation power, leveraging cold mountain climate for data centers.", "Point 39"),
        # Digital & IT — from Points 4, 5, 9, 36, 37, 38
        ("D1", "Digital & IT", "National digital ID for all citizens", "Issue national identity card to every citizen, build unified database, and link to all government services.", "Point 4"),
        ("D2", "Digital & IT", "Digitize tippani.gov.np & paripatra.gov.np", "All government memos (tippani) and official directives (paripatra) issued and tracked digitally.", "Point 5"),
        ("D3", "Digital & IT", "Complete government file digitization", "End manual file routing. Every government file tracked digitally with process audit trail (प्रक्रिया लेखाजोखा).", "Point 9"),
        ("D4", "Digital & IT", "Digital Parks in all 7 provinces, $30B IT export target", "Declare IT as 'national strategic industry.' Build modern digital parks in all 7 provinces. Grow IT exports from current $1.5B to $30B in 10 years.", "Point 36"),
        ("D5", "Digital & IT", "Comprehensive digital infrastructure & cybersecurity", "Build complete digital ecosystem: data centers, cloud services, cybersecurity framework, privacy laws, and high-speed connectivity.", "Point 37"),
        ("D6", "Digital & IT", "International payment gateway & Digital-First nation", "Remove legal and technical barriers for startups to access international payment gateways. Transform Nepal into a 'Digital-First' nation.", "Point 38"),
        # Financial Sector — from Points 29, 30, 33, 34
        ("F1", "Financial Sector", "Cooperative & microfinance regulation under NRB", "Bring all cooperatives and microfinance with 50Cr+ transactions under direct Nepal Rastra Bank supervision.", "Points 29, 30"),
        ("F2", "Financial Sector", "NEPSE restructuring & capital market reform", "Restructure Nepal Stock Exchange and CDS. Increase private sector share ownership. Develop competitive depository services.", "Point 33"),
        ("F3", "Financial Sector", "Grow institutional investors", "Expand pension funds, insurance, mutual funds, and other institutional investors. Build insider trading regulation framework.", "Point 34"),
        # Social — from Citizen Contract, Points 1, 62, 71, 99
        ("S1", "Social", "End caste, ethnic, and gender discrimination", "Address systemic discrimination against Dalits and marginalized communities through policy, law, and social reform.", "Point 1"),
        ("S2", "Social", "Fundamental reform of public education system", "Overhaul public education quality, access, and competitiveness. Reform teacher evaluation, curriculum, and school governance.", "Points 62-65"),
        ("S3", "Social", "Universal health insurance expansion", "Strengthen and expand health insurance model to ensure quality healthcare reaches every citizen. Increase health budget priority.", "Citizen Contract \u00a72, Point 71"),
        ("S4", "Social", "Diaspora voting rights & engagement", "Grant online voting rights to Nepalis abroad. Establish universal diaspora fund. 'One-time Nepali, always Nepali' policy. Safe remittance channels.", "Citizen Contract \u00a75, Point 99"),
        # Infrastructure — from Citizen Contract, Points 44, 57
        ("I1", "Infrastructure", "15,000 MW installed hydropower capacity", "Establish 15,000 MW installed electricity capacity and 'Smart National Grid.' Make Nepal an energy export hub.", "Citizen Contract \u00a74"),
        ("I2", "Infrastructure", "High-speed internet to all settlements", "Extend high-speed affordable internet to every settlement. Build 30,000 km national fiber-optic highway.", "Citizen Contract \u00a74"),
        ("I3", "Infrastructure", "Integrated connectivity: roads, rail, and air", "Build 15,000 km quality roads, 10 national highway construction/upgrades, railway masterplan, and signature infrastructure projects.", "Citizen Contract \u00a74, Point 57"),
        # Trade & Investment — from Points 24, 33, 35
        ("T1", "Trade & Investment", "One-stop shop for investment (वान-स्टप सेवा केन्द्र)", "Single window for all domestic and foreign investment approvals — file once, no running between agencies.", "Point 24"),
        ("T2", "Trade & Investment", "Reduce import dependence via domestic production", "Shift from remittance-dependent consumption economy to production-oriented economy. Prioritize domestic energy, agriculture, IT.", "Point 35, Citizen Contract \u00a73"),
        ("T3", "Trade & Investment", "Investment-friendly regulatory framework", "Transparent, predictable regulations. Strengthen NEPSE, build competitive financial markets.", "Points 24, 33"),
    ]

    created = 0
    for pid, cat, promise, detail, source in SEED_DATA:
        existing = await db.execute(
            select(ManifestoPromise).where(ManifestoPromise.promise_id == pid)
        )
        if existing.scalar_one_or_none():
            continue
        db.add(ManifestoPromise(
            id=uuid4(),
            promise_id=pid,
            party="RSP",
            election_year="2082",
            category=cat,
            promise=promise,
            detail=detail,
            source=source,
            status="not_started",
        ))
        created += 1

    await db.commit()
    return {"seeded": created, "total": len(SEED_DATA)}
