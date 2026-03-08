"""Scraper for Nepal Election Commission live results.

Polls result.election.gov.np for HOR FPTP constituency-level vote counts
and party summaries. Designed to run every 2-5 minutes during counting.

Endpoints used:
  - /Handlers/SecureJson.ashx?file=JSONFiles/Election2082/Common/HoRPartyTop5.txt
  - /Handlers/SecureJson.ashx?file=JSONFiles/Election2082/HOR/FPTP/HOR-{dist}-{const}.json
  - /Handlers/SecureJson.ashx?file=JSONFiles/Election2082/HOR/Lookup/constituencies.json
  - /Handlers/SecureJson.ashx?file=JSONFiles/Election2082/Local/Lookup/districts.json
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.election_result import ElectionCandidate, ElectionPartySummary, ElectionScrapeLog

logger = logging.getLogger(__name__)

BASE_URL = "https://result.election.gov.np"
HANDLER = "/Handlers/SecureJson.ashx"
ELECTION_YEAR = "2082"


class ECNResultsClient:
    """HTTP client that handles ECN session + CSRF token."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=15.0,
            verify=False,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; OSINT/1.0)"},
        )
        self.csrf_token: str | None = None

    async def init_session(self):
        """Get session cookie + CSRF token by hitting the main page. Retries up to 3 times."""
        for attempt in range(3):
            try:
                r = await self.client.get(f"{BASE_URL}/")
                if r.status_code in (502, 503, 504):
                    logger.warning(f"ECN main page returned {r.status_code}, retry {attempt+1}/3")
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                self.csrf_token = self.client.cookies.get("CsrfToken")
                if not self.csrf_token:
                    raise RuntimeError("Failed to get CsrfToken from ECN")
                logger.info(f"ECN session established, CSRF: {self.csrf_token[:8]}...")
                return
            except httpx.ConnectError:
                logger.warning(f"ECN connection error, retry {attempt+1}/3")
                await asyncio.sleep(5 * (attempt + 1))
        raise RuntimeError("ECN unreachable after 3 retries")

    async def fetch_json(self, file_path: str) -> list | dict | None:
        """Fetch a JSON file via SecureJson handler. Retries on 429/403."""
        if not self.csrf_token:
            await self.init_session()

        url = f"{BASE_URL}{HANDLER}?file={file_path}"

        for attempt in range(4):
            r = await self.client.get(
                url,
                headers={
                    "X-CSRF-Token": self.csrf_token,
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{BASE_URL}/",
                },
            )

            if r.status_code == 429:
                wait = 10 * (2 ** attempt)  # 10, 20, 40, 80s
                logger.warning(f"ECN 429 rate-limited on {file_path}, waiting {wait}s (attempt {attempt+1}/4)")
                await asyncio.sleep(wait)
                continue

            if r.status_code == 403:
                # Session expired — re-init and retry
                logger.info("ECN 403 — refreshing session")
                await self.init_session()
                continue

            break
        else:
            logger.warning(f"ECN gave up after 4 retries for {file_path}")
            return None

        if r.status_code == 404:
            return None

        if r.status_code in (500, 502, 503, 504):
            logger.warning(f"ECN server error {r.status_code} for {file_path}")
            return None

        r.raise_for_status()

        text = r.text.strip()
        if text.startswith("\ufeff"):
            text = text[1:]

        if not text or text == "[]":
            return []

        return json.loads(text)

    async def close(self):
        await self.client.aclose()


async def scrape_election_results():
    """Main scraper entry point. Fetches all HOR FPTP results."""
    log_id = None
    client = ECNResultsClient()

    try:
        await client.init_session()

        async with AsyncSessionLocal() as db:
            # Create scrape log
            log = ElectionScrapeLog()
            db.add(log)
            await db.flush()
            log_id = log.id

            # 1. Fetch constituencies lookup
            consts_data = await client.fetch_json(
                f"JSONFiles/Election{ELECTION_YEAR}/HOR/Lookup/constituencies.json"
            )
            if not consts_data:
                logger.warning("No constituencies data available yet")
                log.error = "No constituencies data"
                log.finished_at = datetime.now(timezone.utc)
                await db.commit()
                return

            # 2. Fetch districts lookup for name mapping
            districts_data = await client.fetch_json(
                f"JSONFiles/Election{ELECTION_YEAR}/Local/Lookup/districts.json"
            )
            dist_map = {}
            if districts_data:
                for d in districts_data:
                    dist_map[d["id"]] = d

            # 3. Fetch states lookup
            states_data = await client.fetch_json(
                f"JSONFiles/Election{ELECTION_YEAR}/Local/Lookup/states.json"
            )
            state_map = {}
            if states_data:
                for s in states_data:
                    state_map[s["id"]] = s["name"]

            # 4. Scrape each constituency (deduplicate — ECN lookup has duplicate distId=77)
            total_scraped = 0
            total_updated = 0
            seen_districts = set()

            for const_entry in consts_data:
                dist_id = const_entry["distId"]
                if dist_id in seen_districts:
                    continue
                seen_districts.add(dist_id)
                num_consts = const_entry["consts"]

                for const_no in range(1, num_consts + 1):
                    try:
                        candidates = await client.fetch_json(
                            f"JSONFiles/Election{ELECTION_YEAR}/HOR/FPTP/HOR-{dist_id}-{const_no}.json"
                        )

                        if not candidates:
                            continue

                        total_scraped += 1

                        updated = await _upsert_candidates(
                            db, candidates, dist_id, const_no, dist_map, state_map
                        )
                        total_updated += updated

                        # Commit every 10 constituencies to avoid losing data
                        if total_scraped % 10 == 0:
                            await db.commit()

                        # Respectful delay to avoid ECN 429 rate limiting
                        await asyncio.sleep(4)

                    except Exception as e:
                        logger.warning(f"Error scraping HOR-{dist_id}-{const_no}: {e}")

            # 5. Fetch party summary
            party_data = await client.fetch_json(
                f"JSONFiles/Election{ELECTION_YEAR}/Common/HoRPartyTop5.txt"
            )
            if party_data:
                await _upsert_party_summary(db, party_data, "hor")

            # Also fetch PA party summaries for each state
            for state_id in range(1, 8):
                pa_data = await client.fetch_json(
                    f"JSONFiles/Election{ELECTION_YEAR}/Common/PAPartyTop5-S{state_id}.txt"
                )
                if pa_data:
                    await _upsert_party_summary(db, pa_data, "pa", state_id=state_id)

            # 6. Update scrape log
            log.constituencies_scraped = total_scraped
            log.candidates_updated = total_updated
            log.finished_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                f"ECN scrape complete: {total_scraped} constituencies, "
                f"{total_updated} candidates updated"
            )

            # Check if ECN has any actual vote data yet
            vote_check = await db.execute(
                select(func.count(ElectionCandidate.id)).where(
                    ElectionCandidate.election_type == "hor",
                    ElectionCandidate.total_vote_received > 0,
                )
            )
            candidates_with_votes = vote_check.scalar() or 0

            if candidates_with_votes == 0:
                logger.info("ECN has 0 vote data — trying ekantipur fallback")
                try:
                    await scrape_ekantipur_fallback()
                except Exception as e:
                    logger.warning(f"Ekantipur fallback failed: {e}")

    except Exception as e:
        logger.error(f"ECN scraper error: {e}")
        if log_id:
            try:
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(ElectionScrapeLog)
                        .where(ElectionScrapeLog.id == log_id)
                        .values(error=str(e), finished_at=datetime.now(timezone.utc))
                    )
                    await db.commit()
            except Exception:
                pass
    finally:
        await client.close()


async def _upsert_candidates(
    db: AsyncSession,
    candidates: list[dict],
    dist_id: int,
    const_no: int,
    dist_map: dict,
    state_map: dict,
) -> int:
    """Upsert candidates for a constituency. Returns count of updated rows."""
    updated = 0
    now = datetime.now(timezone.utc)

    for c in candidates:
        ecn_id = c.get("CandidateID")
        if not ecn_id:
            continue

        state_id = c.get("State", 0)
        district_name = c.get("DistrictName", "")
        if not district_name and dist_id in dist_map:
            district_name = dist_map[dist_id].get("name", "")

        state_name = c.get("StateName", "")
        if not state_name and state_id in state_map:
            state_name = state_map[state_id]

        rank_val = None
        if c.get("Rank"):
            try:
                rank_val = int(c["Rank"])
            except (ValueError, TypeError):
                pass

        values = {
            "ecn_candidate_id": ecn_id,
            "state_id": state_id,
            "state_name": state_name,
            "district_cd": dist_id,
            "district_name": district_name,
            "constituency_no": const_no,
            "election_type": "hor",
            "candidate_name": c.get("CandidateName", ""),
            "gender": c.get("Gender"),
            "age": c.get("Age"),
            "party_name": c.get("PoliticalPartyName", ""),
            "party_id": c.get("PartyID"),
            "symbol_name": c.get("SymbolName"),
            "symbol_id": c.get("SymbolID"),
            "total_vote_received": c.get("TotalVoteReceived", 0),
            "casted_vote": c.get("CastedVote", 0),
            "total_voters": c.get("TotalVoters", 0),
            "rank": rank_val,
            "remarks": c.get("Remarks"),
            "last_updated": now,
        }

        stmt = pg_insert(ElectionCandidate).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ecn_candidate_id"],
            set_={
                "total_vote_received": stmt.excluded.total_vote_received,
                "casted_vote": stmt.excluded.casted_vote,
                "total_voters": stmt.excluded.total_voters,
                "rank": stmt.excluded.rank,
                "remarks": stmt.excluded.remarks,
                "is_winner": stmt.excluded.remarks == "Winner" if c.get("Remarks") else False,
                "last_updated": now,
            },
        )
        await db.execute(stmt)
        updated += 1

    return updated


async def _upsert_party_summary(
    db: AsyncSession, data: list[dict], election_type: str, state_id: int | None = None
):
    """Upsert party summary rows."""
    now = datetime.now(timezone.utc)

    for p in data:
        party_name = p.get("PartyName", p.get("PoliticalPartyName", ""))
        if not party_name:
            continue

        values = {
            "election_type": election_type,
            "state_id": state_id or p.get("StateId"),
            "party_name": party_name,
            "party_id": p.get("PartyId", p.get("PartyID")),
            "seats_won": p.get("Winner", p.get("Won", 0)),
            "seats_leading": p.get("Leader", p.get("Leading", 0)),
            "total_votes": p.get("TotalVote", p.get("TotalVotes", 0)),
            "last_updated": now,
        }

        existing = await db.execute(
            select(ElectionPartySummary).where(
                ElectionPartySummary.party_name == party_name,
                ElectionPartySummary.election_type == election_type,
                ElectionPartySummary.state_id == values["state_id"],
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.seats_won = values["seats_won"]
            row.seats_leading = values["seats_leading"]
            row.total_votes = values["total_votes"]
            row.last_updated = now
        else:
            db.add(ElectionPartySummary(**values))


async def scrape_ekantipur_fallback():
    """Fallback scraper: parse ekantipur.com embedded election data.

    Ekantipur embeds all candidate data as JS in the page HTML.
    We parse competiviveDist + the full per-district data and upsert
    vote counts into the same election_candidates_2082 table.
    Only updates rows where ekantipur has newer/non-zero data.
    """
    import re

    logger.info("Running ekantipur fallback scraper")
    url = "https://election.ekantipur.com/?lng=eng"

    async with httpx.AsyncClient(
        timeout=30.0, verify=False, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    ) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"Ekantipur fetch failed: {e}")
            return

    html = r.text

    # Extract competiviveDist JSON (embedded in a <script> tag)
    m = re.search(r"competiviveDist\s*=\s*(\{.+?\});\s*(?:\n|var|let|const)", html, re.DOTALL)
    if not m:
        logger.warning("Ekantipur: competiviveDist not found in page")
        return

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        logger.error(f"Ekantipur: JSON parse error: {e}")
        return

    logger.info(f"Ekantipur: parsed {len(data)} constituencies")

    now = datetime.now(timezone.utc)
    updated = 0

    async with AsyncSessionLocal() as db:
        for const_key, candidates in data.items():
            for c in candidates:
                vote_count = c.get("vote_count", 0) or 0
                if vote_count <= 0:
                    continue

                # Match by candidate name + district + party (ekantipur doesn't have ecn_candidate_id)
                cand_name = c.get("name", "").strip()
                party_name = c.get("party_name", "").strip()
                district_slug = c.get("district_slug", "")

                if not cand_name or not district_slug:
                    continue

                # Find matching candidate in our DB
                result = await db.execute(
                    select(ElectionCandidate).where(
                        ElectionCandidate.candidate_name == cand_name,
                        ElectionCandidate.party_name == party_name,
                        ElectionCandidate.election_type == "hor",
                    ).limit(1)
                )
                row = result.scalar_one_or_none()

                if row and vote_count > (row.total_vote_received or 0):
                    row.total_vote_received = vote_count
                    row.is_winner = bool(c.get("is_win", 0))
                    row.last_updated = now
                    updated += 1

        if updated > 0:
            await db.commit()

    logger.info(f"Ekantipur fallback: updated {updated} candidates with vote data")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(scrape_election_results())
