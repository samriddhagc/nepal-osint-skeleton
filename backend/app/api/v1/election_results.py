"""API endpoints for live election results from ECN."""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Body
from pydantic import BaseModel
from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.election_result import ElectionCandidate, ElectionPartySummary, ElectionScrapeLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/election-results", tags=["election-results"])

# Cache for the live snapshot (rebuilt every 30s)
_snapshot_cache: dict | None = None
_snapshot_cache_ts: float = 0
SNAPSHOT_TTL = 30  # seconds


@router.get("/summary")
async def get_election_summary(db: AsyncSession = Depends(get_db)):
    """Top-level summary: total seats, counted, party standings."""
    # Party summary for HOR (national)
    result = await db.execute(
        select(ElectionPartySummary)
        .where(ElectionPartySummary.election_type == "hor")
        .where(ElectionPartySummary.state_id.is_(None))
        .order_by(desc(ElectionPartySummary.seats_won + ElectionPartySummary.seats_leading))
    )
    parties = result.scalars().all()

    # Count constituencies with results
    counted = await db.execute(
        select(func.count(func.distinct(
            func.concat(ElectionCandidate.district_cd, "-", ElectionCandidate.constituency_no)
        ))).where(
            ElectionCandidate.election_type == "hor",
            ElectionCandidate.total_vote_received > 0,
        )
    )
    constituencies_counted = counted.scalar() or 0

    total_constituencies = await db.execute(
        select(func.count(func.distinct(
            func.concat(ElectionCandidate.district_cd, "-", ElectionCandidate.constituency_no)
        ))).where(ElectionCandidate.election_type == "hor")
    )
    total = min(total_constituencies.scalar() or 165, 165)  # HOR has exactly 165 FPTP seats

    # Last scrape time
    last_scrape = await db.execute(
        select(ElectionScrapeLog)
        .where(ElectionScrapeLog.error.is_(None))
        .order_by(desc(ElectionScrapeLog.finished_at))
        .limit(1)
    )
    scrape = last_scrape.scalar_one_or_none()

    return {
        "total_seats": 165,
        "total_constituencies": total,
        "constituencies_counted": constituencies_counted,
        "last_updated": scrape.finished_at.isoformat() if scrape and scrape.finished_at else None,
        "parties": [
            {
                "party_name": p.party_name,
                "seats_won": p.seats_won,
                "seats_leading": p.seats_leading,
                "total": p.seats_won + p.seats_leading,
                "total_votes": p.total_votes,
            }
            for p in parties
        ],
    }


@router.get("/parties")
async def get_party_results(
    election_type: str = Query("hor", pattern="^(hor|pa)$"),
    state_id: Optional[int] = Query(None, ge=1, le=7),
    db: AsyncSession = Depends(get_db),
):
    """Party-wise seat counts."""
    query = select(ElectionPartySummary).where(
        ElectionPartySummary.election_type == election_type
    )

    if state_id:
        query = query.where(ElectionPartySummary.state_id == state_id)
    elif election_type == "hor":
        query = query.where(ElectionPartySummary.state_id.is_(None))

    query = query.order_by(
        desc(ElectionPartySummary.seats_won + ElectionPartySummary.seats_leading)
    )

    result = await db.execute(query)
    parties = result.scalars().all()

    return [
        {
            "party_name": p.party_name,
            "party_id": p.party_id,
            "seats_won": p.seats_won,
            "seats_leading": p.seats_leading,
            "total": p.seats_won + p.seats_leading,
            "total_votes": p.total_votes,
        }
        for p in parties
    ]


@router.get("/constituency/{district_cd}/{constituency_no}")
async def get_constituency_results(
    district_cd: int,
    constituency_no: int,
    election_type: str = Query("hor", pattern="^(hor|pa)$"),
    db: AsyncSession = Depends(get_db),
):
    """Candidate-level results for a specific constituency."""
    result = await db.execute(
        select(ElectionCandidate)
        .where(
            ElectionCandidate.district_cd == district_cd,
            ElectionCandidate.constituency_no == constituency_no,
            ElectionCandidate.election_type == election_type,
        )
        .order_by(desc(ElectionCandidate.total_vote_received))
    )
    candidates = result.scalars().all()

    if not candidates:
        return {"candidates": [], "meta": None}

    first = candidates[0]
    return {
        "meta": {
            "district_cd": district_cd,
            "district_name": first.district_name,
            "constituency_no": constituency_no,
            "state_id": first.state_id,
            "state_name": first.state_name,
            "total_voters": first.total_voters,
            "casted_vote": first.casted_vote,
            "turnout_pct": round(first.casted_vote / first.total_voters * 100, 1)
            if first.total_voters > 0 else 0,
        },
        "candidates": [
            {
                "candidate_name": c.candidate_name,
                "party_name": c.party_name,
                "symbol_name": c.symbol_name,
                "gender": c.gender,
                "age": c.age,
                "total_vote_received": c.total_vote_received,
                "rank": c.rank,
                "is_winner": c.is_winner,
                "vote_share_pct": round(c.total_vote_received / first.casted_vote * 100, 1)
                if first.casted_vote > 0 else 0,
            }
            for c in candidates
        ],
    }


@router.get("/by-state/{state_id}")
async def get_state_results(
    state_id: int,
    db: AsyncSession = Depends(get_db),
):
    """All constituency results for a province, showing leading candidates."""
    # Get all candidates ranked #1 in each constituency
    subq = (
        select(
            ElectionCandidate.district_cd,
            ElectionCandidate.constituency_no,
            func.max(ElectionCandidate.total_vote_received).label("max_votes"),
        )
        .where(
            ElectionCandidate.state_id == state_id,
            ElectionCandidate.election_type == "hor",
        )
        .group_by(ElectionCandidate.district_cd, ElectionCandidate.constituency_no)
        .subquery()
    )

    result = await db.execute(
        select(ElectionCandidate)
        .join(
            subq,
            (ElectionCandidate.district_cd == subq.c.district_cd)
            & (ElectionCandidate.constituency_no == subq.c.constituency_no)
            & (ElectionCandidate.total_vote_received == subq.c.max_votes),
        )
        .where(ElectionCandidate.state_id == state_id)
        .order_by(ElectionCandidate.district_cd, ElectionCandidate.constituency_no)
    )
    leaders = result.scalars().all()

    return [
        {
            "district_cd": c.district_cd,
            "district_name": c.district_name,
            "constituency_no": c.constituency_no,
            "leading_candidate": c.candidate_name,
            "leading_party": c.party_name,
            "votes": c.total_vote_received,
            "is_winner": c.is_winner,
            "total_voters": c.total_voters,
            "casted_vote": c.casted_vote,
        }
        for c in leaders
    ]


@router.get("/scrape-status")
async def get_scrape_status(db: AsyncSession = Depends(get_db)):
    """Check last scrape run status."""
    result = await db.execute(
        select(ElectionScrapeLog)
        .order_by(desc(ElectionScrapeLog.started_at))
        .limit(5)
    )
    logs = result.scalars().all()

    return [
        {
            "started_at": l.started_at.isoformat() if l.started_at else None,
            "finished_at": l.finished_at.isoformat() if l.finished_at else None,
            "constituencies_scraped": l.constituencies_scraped,
            "candidates_updated": l.candidates_updated,
            "error": l.error,
        }
        for l in logs
    ]


# ── Static JSON base (loaded once) ──────────────────────────────────
_static_base: dict | None = None

def _load_static_base() -> dict:
    """Load the static election-results-2082.json as the base template."""
    global _static_base
    if _static_base is not None:
        return _static_base

    # Try multiple paths (Docker vs local dev)
    candidates = [
        Path("/app/static/election-results-2082.json"),
        Path(__file__).resolve().parents[3] / "static" / "election-results-2082.json",
    ]
    for p in candidates:
        if p.exists():
            with open(p) as f:
                _static_base = json.load(f)
            logger.info("Loaded static election base from %s (%d results)", p, len(_static_base.get("results", [])))
            return _static_base

    raise FileNotFoundError(f"election-results-2082.json not found in {[str(c) for c in candidates]}")


@router.get("/live-snapshot")
async def get_live_snapshot(db: AsyncSession = Depends(get_db)):
    """Full election data with live vote counts overlaid on static candidate data.

    Returns the same format as election-results-2082.json so the frontend
    ElectionMapWidget can consume it directly.
    """
    global _snapshot_cache, _snapshot_cache_ts

    now = time.monotonic()
    if _snapshot_cache and (now - _snapshot_cache_ts) < SNAPSHOT_TTL:
        return _snapshot_cache

    base = _load_static_base()

    # Fetch all live vote data keyed by ecn_candidate_id
    result = await db.execute(select(ElectionCandidate).where(ElectionCandidate.election_type == "hor"))
    live_rows = result.scalars().all()

    live_by_id: dict[int, ElectionCandidate] = {}
    for row in live_rows:
        live_by_id[row.ecn_candidate_id] = row

    # Fetch party summary
    party_result = await db.execute(
        select(ElectionPartySummary)
        .where(ElectionPartySummary.election_type == "hor", ElectionPartySummary.state_id.is_(None))
        .order_by(desc(ElectionPartySummary.seats_won + ElectionPartySummary.seats_leading))
    )
    party_rows = party_result.scalars().all()

    # Build updated results
    updated_results = []
    total_declared = 0
    total_counting = 0
    total_votes_cast = 0
    leading_party_seats: dict[str, int] = {}
    won_party_seats: dict[str, int] = {}

    for const in base.get("results", []):
        candidates_out = []
        const_total_votes = 0
        const_casted = 0
        has_votes = False
        winner_party = None
        winner_name = None
        winner_votes = None
        const_last_updated = None

        for cand in const.get("candidates", []):
            cand_id = int(cand["id"]) if cand.get("id") else None
            live = live_by_id.get(cand_id) if cand_id else None

            # Track latest update time across all candidates in this constituency
            if live and live.last_updated:
                if const_last_updated is None or live.last_updated > const_last_updated:
                    const_last_updated = live.last_updated

            votes = live.total_vote_received if live else 0
            is_winner = (live.remarks in ("Winner", "Elected")) if live and live.remarks else False
            if not is_winner and live and live.is_winner:
                is_winner = True

            cand_out = {**cand, "votes": votes, "is_winner": is_winner}
            if live and live.casted_vote:
                cand_out["vote_pct"] = round(votes / live.casted_vote * 100, 1) if live.casted_vote > 0 else 0
                const_casted = max(const_casted, live.casted_vote)
            else:
                cand_out["vote_pct"] = 0

            if votes > 0:
                has_votes = True
            const_total_votes += votes

            if is_winner:
                winner_party = cand.get("party")
                winner_name = cand.get("name_en")
                winner_votes = votes
                if winner_party:
                    won_party_seats[winner_party] = won_party_seats.get(winner_party, 0) + 1

            candidates_out.append(cand_out)

        # Sort by votes descending
        candidates_out.sort(key=lambda c: c.get("votes", 0), reverse=True)

        # Determine status
        if winner_party:
            status = "declared"
            total_declared += 1
        elif has_votes:
            status = "counting"
            total_counting += 1
        else:
            status = "pending"

        # Track leading party
        if has_votes and candidates_out:
            lead_party = candidates_out[0].get("party", "")
            if lead_party:
                leading_party_seats[lead_party] = leading_party_seats.get(lead_party, 0) + 1

        total_votes_cast += const_total_votes

        turnout_pct = None
        if const_casted > 0 and const.get("candidates"):
            first_live = live_by_id.get(int(const["candidates"][0]["id"])) if const["candidates"][0].get("id") else None
            if first_live and first_live.total_voters > 0:
                turnout_pct = round(first_live.casted_vote / first_live.total_voters * 100, 1)

        updated_results.append({
            "constituency_id": const["constituency_id"],
            "name_en": const["name_en"],
            "name_ne": const.get("name_ne", ""),
            "district": const["district"],
            "province": const["province"],
            "province_id": const.get("province_id", 0),
            "status": status,
            "winner_party": winner_party,
            "winner_name": winner_name,
            "winner_votes": winner_votes,
            "total_votes": const_total_votes,
            "turnout_pct": turnout_pct,
            "last_updated": const_last_updated.isoformat() if const_last_updated else None,
            "candidates": candidates_out,
        })

    # Build leading party info
    top_party = max(leading_party_seats, key=leading_party_seats.get, default=None) if leading_party_seats else None

    # Build party seats: prefer computed leading_party_seats (always fresh)
    # over DB summary which may lag behind vote ingestion
    if leading_party_seats:
        party_seats_list = [
            {"party": party, "seats": count, "won": won_party_seats.get(party, 0), "leading": count - won_party_seats.get(party, 0)}
            for party, count in sorted(leading_party_seats.items(), key=lambda x: -x[1])
        ]
    else:
        party_seats_list = []
        for p in party_rows:
            party_seats_list.append({
                "party": p.party_name,
                "seats": p.seats_won + p.seats_leading,
                "won": p.seats_won,
                "leading": p.seats_leading,
            })

    total_pending = len(updated_results) - total_declared - total_counting

    snapshot = {
        "election_year": 2082,
        "total_constituencies": len(updated_results),
        "results": updated_results,
        "national_summary": {
            "total_constituencies": len(updated_results),
            "declared": total_declared,
            "counting": total_counting,
            "pending": total_pending,
            "turnout_pct": None,
            "total_votes_cast": total_votes_cast,
            "total_registered_voters": None,
            "leading_party": top_party,
            "leading_party_seats": leading_party_seats.get(top_party, 0) if top_party else 0,
            "party_seats": party_seats_list,
        },
    }

    _snapshot_cache = snapshot
    _snapshot_cache_ts = now
    logger.info("Built live snapshot: %d declared, %d counting, %d pending", total_declared, total_counting, total_pending)
    return snapshot


# ── Election Ticker Breaking News (AI agent → frontend ticker) ──────────────

# In-memory store for AI-extracted breaking election alerts (max 50, TTL 30 min)
_ticker_breaking: list[dict] = []
_TICKER_MAX = 50
_TICKER_TTL = 1800  # 30 minutes


class TickerAlert(BaseModel):
    """A single breaking election alert from the AI agent."""
    id: str
    type: str  # 'elected' | 'leading' | 'breaking' | 'update'
    headline: str
    source: str = "ai-agent"  # 'ai-agent', 'journalist', etc.
    confidence: float = 0.8


class TickerIngestRequest(BaseModel):
    """Batch of breaking alerts from the local AI agent."""
    alerts: list[TickerAlert]


@router.post("/ticker/ingest")
async def ingest_ticker_alerts(
    payload: TickerIngestRequest,
    user=Depends(get_current_user),
):
    """Ingest AI-extracted breaking election alerts for the ticker.

    Called by the local Sonnet agent every 5 minutes.
    """
    global _ticker_breaking

    now = time.time()
    # Remove expired alerts
    _ticker_breaking = [a for a in _ticker_breaking if (now - a.get("_ts", 0)) < _TICKER_TTL]

    seen_ids = {a["id"] for a in _ticker_breaking}
    added = 0
    for alert in payload.alerts:
        if alert.id in seen_ids:
            continue
        _ticker_breaking.append({
            "id": alert.id,
            "type": alert.type,
            "headline": alert.headline,
            "source": alert.source,
            "confidence": alert.confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "_ts": now,
        })
        seen_ids.add(alert.id)
        added += 1

    # Cap size
    if len(_ticker_breaking) > _TICKER_MAX:
        _ticker_breaking = _ticker_breaking[-_TICKER_MAX:]

    logger.info(f"Ticker ingest: {added} new alerts ({len(_ticker_breaking)} total)")
    return {"added": added, "total": len(_ticker_breaking)}


@router.get("/ticker/breaking")
async def get_ticker_breaking():
    """Get AI-extracted breaking election alerts for the ticker."""
    now = time.time()
    active = [
        {k: v for k, v in a.items() if k != "_ts"}
        for a in _ticker_breaking
        if (now - a.get("_ts", 0)) < _TICKER_TTL
    ]
    return active


# ── Ekantipur ingest endpoint (called by local scraper) ──────────────

class EkantipurCandidate(BaseModel):
    ecn_candidate_id: int
    vote_count: int
    is_win: bool = False
    is_lead: bool = False

class EkantipurIngestPayload(BaseModel):
    candidates: list[EkantipurCandidate]
    source: str = "ekantipur"


@router.post("/ingest-votes")
async def ingest_votes(
    payload: EkantipurIngestPayload,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Ingest vote counts from local ekantipur scraper.

    Accepts a list of {ecn_candidate_id, vote_count, is_win, is_lead}.
    Only updates if incoming vote_count > existing (no data loss).
    """
    global _snapshot_cache, _snapshot_cache_ts

    now = datetime.now(timezone.utc)
    updated = 0
    skipped = 0

    for c in payload.candidates:
        if c.vote_count <= 0:
            continue

        result = await db.execute(
            select(ElectionCandidate).where(
                ElectionCandidate.ecn_candidate_id == c.ecn_candidate_id
            )
        )
        row = result.scalar_one_or_none()

        if not row:
            skipped += 1
            continue

        changed = False
        if c.vote_count > (row.total_vote_received or 0):
            row.total_vote_received = c.vote_count
            row.last_updated = now
            changed = True
        if c.is_win and not row.is_winner:
            row.is_winner = True
            row.last_updated = now
            changed = True
        if changed:
            updated += 1

    if updated > 0:
        await db.commit()
        # Invalidate snapshot cache
        _snapshot_cache = None
        _snapshot_cache_ts = 0
        # Flush Redis response cache for election endpoints
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            if redis:
                keys = await redis.keys("rcache:*")
                if keys:
                    await redis.delete(*keys)
                    logger.info("Flushed %d Redis cache keys after vote ingest", len(keys))
        except Exception as e:
            logger.warning("Redis cache flush failed: %s", e)

    logger.info("Ingest from %s: %d updated, %d skipped", payload.source, updated, skipped)
    return {"updated": updated, "skipped": skipped, "source": payload.source}


class NameBasedCandidate(BaseModel):
    candidate_name: str
    party_name: str
    district_name: str
    constituency_no: int
    vote_count: int
    is_win: bool = False
    is_lead: bool = False

class NameBasedIngestPayload(BaseModel):
    candidates: list[NameBasedCandidate]
    source: str = "ekantipur"


@router.post("/ingest-by-name")
async def ingest_by_name(
    payload: NameBasedIngestPayload,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Ingest vote counts by matching candidate name + party + district + constituency.

    For sources like ekantipur that don't have ECN candidate IDs.
    Only updates if incoming vote_count > existing (no data loss).
    """
    global _snapshot_cache, _snapshot_cache_ts

    now = datetime.now(timezone.utc)
    updated = 0
    skipped = 0
    not_found = 0

    for c in payload.candidates:
        if c.vote_count <= 0:
            continue

        # Match by name + party + constituency
        result = await db.execute(
            select(ElectionCandidate).where(
                func.lower(ElectionCandidate.candidate_name) == c.candidate_name.lower().strip(),
                func.lower(ElectionCandidate.party_name) == c.party_name.lower().strip(),
                ElectionCandidate.constituency_no == c.constituency_no,
                ElectionCandidate.election_type == "hor",
            ).limit(1)
        )
        row = result.scalar_one_or_none()

        if not row:
            # Try fuzzy: just name + constituency (party names differ between sources)
            result = await db.execute(
                select(ElectionCandidate).where(
                    func.lower(ElectionCandidate.candidate_name) == c.candidate_name.lower().strip(),
                    ElectionCandidate.constituency_no == c.constituency_no,
                    ElectionCandidate.election_type == "hor",
                ).limit(1)
            )
            row = result.scalar_one_or_none()

        if not row:
            not_found += 1
            continue

        if c.vote_count > (row.total_vote_received or 0):
            row.total_vote_received = c.vote_count
            row.is_winner = c.is_win
            row.last_updated = now
            updated += 1
        else:
            skipped += 1

    if updated > 0:
        await db.commit()
        _snapshot_cache = None
        _snapshot_cache_ts = 0
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            if redis:
                keys = await redis.keys("rcache:*")
                if keys:
                    await redis.delete(*keys)
        except Exception:
            pass

    logger.info("Name-ingest from %s: %d updated, %d skipped, %d not found", payload.source, updated, skipped, not_found)
    return {"updated": updated, "skipped": skipped, "not_found": not_found, "source": payload.source}


# ── PR Votes + Seat Projection ──────────────────────────────────────

_pr_cache: dict | None = None
_pr_cache_ts: float = 0
PR_CACHE_TTL = 60  # seconds

PR_TOTAL_SEATS = 110
PR_THRESHOLD_PCT = 3.0
# Modified Sainte-Laguë divisors: 1.4, 3, 5, 7, 9, ...
SAINTE_LAGUE_FIRST = 1.4


def _compute_pr_seats(parties: list[dict]) -> list[dict]:
    """Apply modified Sainte-Laguë method to allocate 110 PR seats.

    parties: [{"party": str, "votes": int, ...}, ...]
    Returns parties with added "pr_seats" field.
    """
    total_votes = sum(p["votes"] for p in parties)
    if total_votes == 0:
        return parties

    # Step 1: Filter by 3% threshold
    threshold = total_votes * PR_THRESHOLD_PCT / 100
    qualifying = [p for p in parties if p["votes"] >= threshold]
    non_qualifying = [p for p in parties if p["votes"] < threshold]

    for p in non_qualifying:
        p["pr_seats"] = 0
        p["qualifies"] = False

    if not qualifying:
        return parties

    for p in qualifying:
        p["qualifies"] = True
        p["pr_seats"] = 0

    # Step 2: Modified Sainte-Laguë allocation
    # Generate quotients for each qualifying party
    quotients = []
    for p in qualifying:
        # First divisor is 1.4, then 3, 5, 7, 9, ...
        # We need at most PR_TOTAL_SEATS quotients per party
        max_possible = min(PR_TOTAL_SEATS, 110)
        for seat_num in range(max_possible):
            if seat_num == 0:
                divisor = SAINTE_LAGUE_FIRST
            else:
                divisor = 2 * seat_num + 1  # 3, 5, 7, 9, ...
            quotients.append((p["votes"] / divisor, p["party"]))

    # Sort by quotient descending, take top 110
    quotients.sort(key=lambda x: -x[0])
    seat_allocation: dict[str, int] = {}
    for i in range(min(PR_TOTAL_SEATS, len(quotients))):
        party_name = quotients[i][1]
        seat_allocation[party_name] = seat_allocation.get(party_name, 0) + 1

    for p in qualifying:
        p["pr_seats"] = seat_allocation.get(p["party"], 0)

    return qualifying + non_qualifying


@router.get("/pr-votes")
async def get_pr_votes():
    """Fetch PR vote data from ECN and compute projected seat allocation."""
    import httpx

    global _pr_cache, _pr_cache_ts

    now = time.monotonic()
    if _pr_cache and (now - _pr_cache_ts) < PR_CACHE_TTL:
        return _pr_cache

    try:
        async with httpx.AsyncClient(verify=False, timeout=20) as client:
            # Init session
            r = await client.get("https://result.election.gov.np/")
            csrf = r.cookies.get("CsrfToken")
            if not csrf:
                logger.warning("PR: No CSRF token from ECN")
                if _pr_cache:
                    return _pr_cache
                return {"parties": [], "total_votes": 0, "error": "No CSRF token"}

            headers = {
                "X-CSRF-Token": csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://result.election.gov.np/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            }

            r = await client.get(
                "https://result.election.gov.np/Handlers/SecureJson.ashx?file=JSONFiles/Election2082/Common/PRHoRPartyTop5.txt",
                headers=headers,
            )
            if r.status_code != 200:
                logger.warning("PR: ECN returned %d", r.status_code)
                if _pr_cache:
                    return _pr_cache
                return {"parties": [], "total_votes": 0, "error": f"ECN {r.status_code}"}

            text = r.text.strip().lstrip("\ufeff")
            data = json.loads(text)

    except Exception as e:
        logger.warning("PR fetch error: %s", e)
        if _pr_cache:
            return _pr_cache
        return {"parties": [], "total_votes": 0, "error": str(e)}

    # Build party list
    parties = []
    for entry in data:
        votes = int(entry.get("TotalVoteReceived", 0) or 0)
        parties.append({
            "party": entry.get("PoliticalPartyName", ""),
            "votes": votes,
            "symbol_id": entry.get("SymbolID"),
        })

    # Sort by votes descending
    parties.sort(key=lambda x: -x["votes"])
    total_votes = sum(p["votes"] for p in parties)

    # Add vote percentage
    for p in parties:
        p["vote_pct"] = round(p["votes"] / total_votes * 100, 2) if total_votes > 0 else 0

    # Compute seat projection
    parties = _compute_pr_seats(parties)

    result = {
        "parties": parties,
        "total_votes": total_votes,
        "total_pr_seats": PR_TOTAL_SEATS,
        "threshold_pct": PR_THRESHOLD_PCT,
        "method": "Modified Sainte-Laguë",
        "note": "Projected seats based on current vote count. Final allocation may differ.",
    }

    _pr_cache = result
    _pr_cache_ts = now
    return result
