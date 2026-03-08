"""Aviation monitoring service — multi-source ADS-B + Mode-S polling for Nepal airspace.

Data sources (geographic — every 60s):
  1. adsb.lol        — crowdsourced ADS-B, no auth
  2. airplanes.live  — crowdsourced ADS-B, no auth, 1 req/sec

Data sources (Nepal-specific hex lookup — every 60s):
  3. adsb.fi         — multi-hex batch query for known Nepal aircraft

Data sources (Mode-S + satellite — every 5 min):
  4. OpenSky Network — ADS-B, Mode-S, MLAT, ADS-C, FLARM
     Tracks aircraft by hex AND by Nepal bbox (400 credits/day anonymous)

Aircraft are categorised:
  - in_nepal:      inside Nepal border polygon
  - near_nepal:    within 120 nm of Nepal center
  - nepal_carrier: Nepal-registered hex (70a*) or Nepal airline callsign prefix
  - overflight:    high-altitude transit through wider query area
"""
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select, func, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.nepal_airports import NEPAL_AIRPORTS

logger = logging.getLogger(__name__)

# ── Nepal identification constants ──────────────────────────────

NEPAL_HEX_PREFIX = "70a"

# Nepal airline ICAO callsign prefixes
NEPAL_CALLSIGN_PREFIXES = frozenset({
    "RNA",  # Nepal Airlines
    "BWA",  # Buddha Air
    "NYT",  # Yeti Airlines
    "SIM",  # Simrik Air (Simrik Airlines)
    "TRA",  # Tara Air
    "GUA",  # Guna Airlines
    "SRR",  # Surya Air (Saurya Airlines)
    "MYH",  # Summit Air (Makalu Air)
    "SHE",  # Shree Airlines
    "JAR",  # Jazeera Airways Nepal (JetConnect)
    "HMN",  # Himalaya Airlines
})

# Nepal 9N- registration prefix
NEPAL_REG_PREFIX = "9N-"

# Known Nepal-registered aircraft ICAO hex codes
# Sources: OpenSky aircraft DB, hexdb.io, FlightRadar24
# Queried via adsb.fi (batch) and OpenSky (icao24 param)
NEPAL_KNOWN_HEX_CODES = [
    # ── Nepal Army (Military) ──
    "70a04c",  # NA-058, AgustaWestland AW139 helicopter
    "70a54a",  # NA-064, PZL M-28-05 Skytruck (confirmed via tar1090-db)
    # NA-062 (CN-235), NA-063 (M-28), NA-068 (M-28), NA-069 (M-28) — hex unknown, no ADS-B seen yet

    # ── Government of Nepal ──
    "70ae27",  # 9N-RAM, AW139 helicopter (VIP/government transport)

    # ── Nepal Airlines (RNA) — A330, A320, B757 ──
    "70aa75",  # 9N-ALY, A330-243
    "70aa79",  # 9N-ALZ, A330-243
    "70ab21",  # 9N-AKW, A320
    "70ab26",  # 9N-AKX, A320
    "70ab27",  # 9N-ACB, B757
    "70a9e6",  # 9N-ACA, B757

    # ── Himalaya Airlines (HMN) — A320 ──
    "70aea3",  # 9N-ALM, A320
    "70aeae",  # 9N-ALV, A320
    "70aeb4",  # 9N-ALW / 9N-AJS, A320 / ATR 72

    # ── Buddha Air (BWA) — ATR 42/72, Beech 1900D ──
    "70a062",  # 9N-AIT, ATR 72-500
    "70a9f2",  # 9N-AMF, ATR 72-500
    "70a9fc",  # 9N-AMU, ATR 72-500
    "70a9ac",  # 9N-ANI, ATR 72-500
    "70aa66",  # 9N-AIN, ATR 72-500
    "70aa67",  # 9N-AIM, ATR 42-320
    "70aa6f",  # 9N-AJO, ATR 72-500
    "70aa71",  # 9N-AJS, ATR 72-500
    "70afb7",  # 9N-AJX, ATR 72-500
    "70afb9",  # 9N-AMU, ATR 72-500
    "70ac30",  # 9N-AEE, Beech 1900D

    # ── Yeti Airlines (NYT) — ATR 72, Jetstream 41 ──
    "70a00d",  # 9N-AIH, BAe Jetstream 41
    "70a97c",  # 9N-AHU, Jetstream 41
    "70aeb7",  # 9N-ANC, ATR 72-500

    # ── Shree Airlines (SHE) — CRJ-200, DHC-8-400 ──
    "70a9a9",  # 9N-AMA, CRJ-200ER
    "70a9b0",  # 9N-ANE, DHC-8-402
    "70a9b4",  # 9N-ANS, DHC-8-402
    "70a9f8",  # 9N-AMA, CRJ-200ER (alt entry)

    # ── Saurya Airlines (SRR) — CRJ-200 ──
    "70aa70",  # 9N-ALE, CRJ-200ER

    # ── Manang Air — H125 helicopter ──
    "70a8f0",  # 9N-AOE, AS350 B3e (H125)

    # ── Simrik Air — Beech 1900C ──
    "70aaec",  # 9N-AGI, Beech 1900C-1

    # ── Sita Air — Dornier 228 ──
    "70ab30",  # 9N-AIE, Do 228-202K
]

# ── Nepal border polygon (lon, lat) — clockwise ────────────────

NEPAL_POLYGON: list[tuple[float, float]] = [
    (80.06, 30.20), (80.22, 30.41), (80.98, 30.35), (81.55, 30.42),
    (82.10, 30.34), (82.73, 30.00), (83.29, 29.52), (83.93, 29.33),
    (84.23, 28.84), (85.18, 28.32), (86.02, 27.90), (87.23, 27.82),
    (88.02, 27.92), (88.20, 27.37), (88.17, 26.72), (87.82, 26.38),
    (86.97, 26.40), (86.00, 26.39), (85.79, 26.57), (85.11, 26.57),
    (84.64, 26.65), (84.09, 26.63), (83.93, 27.14), (83.29, 27.36),
    (82.73, 27.36), (81.85, 27.19), (81.11, 27.55), (80.58, 28.22),
    (80.22, 28.79), (80.06, 28.84), (80.06, 30.20),
]

# Center of Nepal for "near Nepal" distance calculations
NEPAL_CENTER = (28.4, 84.25)

# Maximum distance (nm) from Nepal center to count as "near_nepal"
NEAR_NEPAL_MAX_NM = 120


def _point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    x, y = lon, lat
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in nautical miles."""
    R_NM = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * R_NM * math.asin(math.sqrt(a))


def _find_nearest_airport(lat: float, lon: float) -> tuple[str | None, float]:
    """Find nearest Nepal airport ICAO code and distance in nm."""
    best_icao = None
    best_dist = float("inf")
    for airport in NEPAL_AIRPORTS:
        d = _haversine_nm(lat, lon, airport["lat"], airport["lon"])
        if d < best_dist:
            best_dist = d
            best_icao = airport["icao"]
    return best_icao, best_dist


def _is_nepal_carrier(hex_code: str, callsign: str | None, registration: str | None) -> bool:
    """Check if aircraft is Nepal-registered or operated by Nepal airline."""
    if hex_code.startswith(NEPAL_HEX_PREFIX):
        return True
    if callsign:
        prefix = callsign[:3].upper()
        if prefix in NEPAL_CALLSIGN_PREFIXES:
            return True
    if registration and registration.upper().startswith(NEPAL_REG_PREFIX):
        return True
    return False


def _classify_aircraft(lat: float, lon: float, hex_code: str,
                       callsign: str | None, registration: str | None) -> str:
    """Classify aircraft into airspace category."""
    # Priority 1: Inside Nepal border
    if _point_in_polygon(lat, lon, NEPAL_POLYGON):
        return "in_nepal"
    # Priority 2: Nepal carrier (anywhere)
    if _is_nepal_carrier(hex_code, callsign, registration):
        return "nepal_carrier"
    # Priority 3: Near Nepal (within buffer zone)
    dist_to_center = _haversine_nm(lat, lon, *NEPAL_CENTER)
    if dist_to_center <= NEAR_NEPAL_MAX_NM:
        return "near_nepal"
    # Default: overflight through wider query radius
    return "overflight"


def _parse_adsb_aircraft(ac: dict, source: str) -> dict | None:
    """Parse a single aircraft from adsb.lol / airplanes.live format."""
    lat = ac.get("lat")
    lon = ac.get("lon")
    if lat is None or lon is None:
        return None

    hex_code = (ac.get("hex") or "").strip().lower()
    if not hex_code:
        return None

    callsign = (ac.get("flight") or "").strip() or None
    registration = ac.get("r") or None
    db_flags = ac.get("dbFlags", 0) or 0
    is_military = bool(db_flags & 1)

    nearest_icao, nearest_dist = _find_nearest_airport(lat, lon)
    airspace_cat = _classify_aircraft(lat, lon, hex_code, callsign, registration)

    return {
        "hex_code": hex_code,
        "callsign": callsign,
        "registration": registration,
        "aircraft_type": ac.get("t") or None,
        "latitude": lat,
        "longitude": lon,
        "altitude_ft": ac.get("alt_baro") if isinstance(ac.get("alt_baro"), (int, float)) else None,
        "ground_speed_kts": ac.get("gs"),
        "track_deg": ac.get("track"),
        "vertical_rate_fpm": ac.get("baro_rate"),
        "squawk": ac.get("squawk"),
        "is_military": is_military,
        "is_on_ground": bool(ac.get("alt_baro") == "ground"),
        "category": ac.get("category"),
        "nearest_airport_icao": nearest_icao,
        "airspace_category": airspace_cat,
        "source": source,
        "seen_at": datetime.now(timezone.utc),
    }


def _parse_opensky_state(state: list, source: str = "opensky") -> dict | None:
    """Parse a single OpenSky state vector into our format.

    OpenSky state vector indices:
      0: icao24, 1: callsign, 2: origin_country, 3: time_position,
      4: last_contact, 5: longitude, 6: latitude, 7: baro_altitude (m),
      8: on_ground, 9: velocity (m/s), 10: true_track, 11: vertical_rate (m/s),
      12: sensors, 13: geo_altitude (m), 14: squawk, 15: spi, 16: position_source
    """
    if not state or len(state) < 14:
        return None

    hex_code = (state[0] or "").strip().lower()
    if not hex_code:
        return None

    lat = state[6]
    lon = state[5]
    if lat is None or lon is None:
        return None

    callsign = (state[1] or "").strip() or None
    registration = None  # OpenSky doesn't include registration in state vectors
    on_ground = bool(state[8])

    # Convert meters to feet
    alt_m = state[7]
    altitude_ft = int(alt_m * 3.28084) if alt_m is not None else None

    # Convert m/s to knots
    vel_ms = state[9]
    speed_kts = round(vel_ms * 1.94384, 1) if vel_ms is not None else None

    # Convert m/s to fpm
    vr_ms = state[11]
    vr_fpm = int(vr_ms * 196.85) if vr_ms is not None else None

    # Military detection: Nepal hex prefix in military range or known mil codes
    is_military = hex_code in NEPAL_MILITARY_HEX

    nearest_icao, _ = _find_nearest_airport(lat, lon)
    airspace_cat = _classify_aircraft(lat, lon, hex_code, callsign, registration)

    return {
        "hex_code": hex_code,
        "callsign": callsign,
        "registration": registration,
        "aircraft_type": None,  # OpenSky states don't include type
        "latitude": lat,
        "longitude": lon,
        "altitude_ft": altitude_ft,
        "ground_speed_kts": speed_kts,
        "track_deg": state[10],
        "vertical_rate_fpm": vr_fpm,
        "squawk": state[14],
        "is_military": is_military,
        "is_on_ground": on_ground,
        "category": None,
        "nearest_airport_icao": nearest_icao,
        "airspace_category": airspace_cat,
        "source": source,
        "seen_at": datetime.now(timezone.utc),
    }


# Set of known military hex codes for fast lookup
NEPAL_MILITARY_HEX = frozenset({
    "70a04c",  # Nepal Army AW139 helicopter (NA-058)
    "70a54a",  # Nepal Army PZL M-28 Skytruck (NA-064)
    "70ae27",  # Government of Nepal AW139 (9N-RAM, VIP transport)
})


class AviationService:
    """Multi-source ADS-B + Mode-S polling for Nepal airspace monitoring."""

    # Geographic sources: 232nm radius from Nepal center (every 60s)
    GEO_SOURCES = [
        {"name": "adsb_lol", "url": "https://api.adsb.lol/v2/lat/28.4/lon/84.25/dist/232"},
        {"name": "airplanes_live", "url": "https://api.airplanes.live/v2/point/28.4/84.25/232"},
    ]
    # Nepal-specific hex lookup (adsb.fi supports comma-separated multi-hex)
    ADSB_FI_BASE = "https://opendata.adsb.fi/api/v2/icao"
    # OpenSky Network (Mode-S + satellite — higher rate limit cost, polled less often)
    OPENSKY_BBOX_URL = "https://opensky-network.org/api/states/all?lamin=26.35&lamax=30.43&lomin=80.06&lomax=88.20"
    OPENSKY_HEX_URL = "https://opensky-network.org/api/states/all"
    POLL_INTERVAL = 60

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _poll_geo_sources(self, client: httpx.AsyncClient) -> dict[str, dict]:
        """Poll geographic ADS-B sources for Nepal area."""
        aircraft: dict[str, dict] = {}
        for src in self.GEO_SOURCES:
            try:
                resp = await client.get(src["url"])
                resp.raise_for_status()
                data = resp.json()
                ac_list = data.get("ac", [])
                count = 0
                for ac in ac_list:
                    parsed = _parse_adsb_aircraft(ac, src["name"])
                    if parsed is None:
                        continue
                    hex_code = parsed["hex_code"]
                    if hex_code not in aircraft:
                        aircraft[hex_code] = parsed
                        count += 1
                    elif parsed.get("callsign") and not aircraft[hex_code].get("callsign"):
                        aircraft[hex_code] = parsed
                logger.info("%s: %d new aircraft (of %d)", src["name"], count, len(ac_list))
            except Exception as e:
                logger.warning("Failed to poll %s: %s", src["name"], e)
        return aircraft

    async def _poll_nepal_hex(self, client: httpx.AsyncClient) -> dict[str, dict]:
        """Query adsb.fi for known Nepal-registered aircraft by hex code."""
        aircraft: dict[str, dict] = {}
        if not NEPAL_KNOWN_HEX_CODES:
            return aircraft
        hex_csv = ",".join(NEPAL_KNOWN_HEX_CODES)
        url = f"{self.ADSB_FI_BASE}/{hex_csv}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            ac_list = data.get("ac", [])
            for ac in ac_list:
                parsed = _parse_adsb_aircraft(ac, "adsb_fi")
                if parsed is None:
                    continue
                aircraft[parsed["hex_code"]] = parsed
            logger.info("adsb.fi Nepal hex: %d aircraft found (of %d known)",
                        len(aircraft), len(NEPAL_KNOWN_HEX_CODES))
        except Exception as e:
            logger.warning("Failed to poll adsb.fi Nepal hex: %s", e)
        return aircraft

    async def _poll_opensky(self, client: httpx.AsyncClient) -> dict[str, dict]:
        """Poll OpenSky Network (Mode-S + ADS-B + satellite).

        Two queries:
        1. Nepal bbox — all aircraft over Nepal area
        2. Known Nepal hex codes — find Nepal aircraft wherever they are
        Uses 2 API credits per call (anonymous: 400/day = 200 calls = fine for 5min interval).
        """
        aircraft: dict[str, dict] = {}
        # 1) Geographic bbox query
        try:
            resp = await client.get(self.OPENSKY_BBOX_URL)
            if resp.status_code == 200:
                data = resp.json()
                states = data.get("states") or []
                for state in states:
                    parsed = _parse_opensky_state(state, "opensky_geo")
                    if parsed:
                        aircraft[parsed["hex_code"]] = parsed
                logger.info("opensky bbox: %d aircraft", len(states))
            else:
                logger.warning("opensky bbox: HTTP %d", resp.status_code)
        except Exception as e:
            logger.warning("Failed to poll OpenSky bbox: %s", e)

        # 2) Nepal hex query (batch up to ~30 per request)
        try:
            params = [("icao24", h) for h in NEPAL_KNOWN_HEX_CODES]
            resp = await client.get(self.OPENSKY_HEX_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                states = data.get("states") or []
                nepal_count = 0
                for state in states:
                    parsed = _parse_opensky_state(state, "opensky_hex")
                    if parsed and parsed["hex_code"] not in aircraft:
                        aircraft[parsed["hex_code"]] = parsed
                        nepal_count += 1
                logger.info("opensky Nepal hex: %d found (of %d known)",
                            nepal_count, len(NEPAL_KNOWN_HEX_CODES))
            elif resp.status_code == 429:
                logger.warning("opensky Nepal hex: rate limited (429)")
            else:
                logger.warning("opensky Nepal hex: HTTP %d", resp.status_code)
        except Exception as e:
            logger.warning("Failed to poll OpenSky Nepal hex: %s", e)

        return aircraft

    async def poll_all_sources(self) -> list[dict]:
        """Poll all ADS-B + Mode-S sources, merge and deduplicate by hex_code."""
        all_aircraft: dict[str, dict] = {}

        async with httpx.AsyncClient(timeout=20.0) as client:
            # 1) Geographic ADS-B sources (adsb.lol + airplanes.live)
            geo = await self._poll_geo_sources(client)
            all_aircraft.update(geo)
            # 2) Nepal-specific hex via adsb.fi
            nepal_fi = await self._poll_nepal_hex(client)
            for hex_code, data in nepal_fi.items():
                if hex_code not in all_aircraft:
                    all_aircraft[hex_code] = data
                elif data.get("callsign") and not all_aircraft[hex_code].get("callsign"):
                    all_aircraft[hex_code] = data

        results = list(all_aircraft.values())
        cats = {}
        for r in results:
            c = r.get("airspace_category", "unknown")
            cats[c] = cats.get(c, 0) + 1
        logger.info("Aviation poll total: %d aircraft — %s", len(results), cats)
        return results

    async def poll_opensky(self) -> list[dict]:
        """Separate OpenSky poll (called on different schedule — every 5 min)."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            aircraft = await self._poll_opensky(client)
        results = list(aircraft.values())
        cats = {}
        for r in results:
            c = r.get("airspace_category", "unknown")
            cats[c] = cats.get(c, 0) + 1
        logger.info("OpenSky poll: %d aircraft — %s", len(results), cats)
        return results

    # Keep backward-compatible alias
    async def poll_adsb_lol(self) -> list[dict]:
        """Backward-compatible: polls all sources now."""
        return await self.poll_all_sources()

    async def store_positions(self, positions: list[dict]) -> int:
        """Store aircraft positions in database."""
        from app.models.aviation import AircraftPosition

        count = 0
        for pos in positions:
            obj = AircraftPosition(id=uuid.uuid4(), **pos)
            self.db.add(obj)
            count += 1

        await self.db.commit()
        return count

    async def get_live_aircraft(self, military_only: bool = False) -> list[dict]:
        """Return latest position per hex_code from last 5 minutes."""
        from app.models.aviation import AircraftPosition

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)

        latest_sub = (
            select(
                AircraftPosition.hex_code,
                func.max(AircraftPosition.seen_at).label("max_seen"),
            )
            .where(AircraftPosition.seen_at >= cutoff)
            .group_by(AircraftPosition.hex_code)
            .subquery()
        )

        query = (
            select(AircraftPosition)
            .join(
                latest_sub,
                (AircraftPosition.hex_code == latest_sub.c.hex_code)
                & (AircraftPosition.seen_at == latest_sub.c.max_seen),
            )
        )

        if military_only:
            query = query.where(AircraftPosition.is_military.is_(True))

        result = await self.db.execute(query)
        rows = result.scalars().all()

        return [
            {
                "hex_code": r.hex_code,
                "callsign": r.callsign,
                "registration": r.registration,
                "aircraft_type": r.aircraft_type,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "altitude_ft": r.altitude_ft,
                "ground_speed_kts": r.ground_speed_kts,
                "track_deg": r.track_deg,
                "vertical_rate_fpm": r.vertical_rate_fpm,
                "squawk": r.squawk,
                "is_military": r.is_military,
                "is_on_ground": r.is_on_ground,
                "category": r.category,
                "airspace_category": r.airspace_category,
                "nearest_airport_icao": r.nearest_airport_icao,
                "seen_at": r.seen_at.isoformat(),
            }
            for r in rows
        ]

    async def get_airport_traffic(self) -> list[dict]:
        """Per-airport traffic with sparklines and type."""
        from app.models.aviation import AircraftPosition

        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)

        airport_map = {a["icao"]: a for a in NEPAL_AIRPORTS}

        current_q = await self.db.execute(
            select(
                AircraftPosition.nearest_airport_icao,
                func.count(func.distinct(AircraftPosition.hex_code)),
            )
            .where(AircraftPosition.seen_at >= hour_ago)
            .where(AircraftPosition.nearest_airport_icao.isnot(None))
            .group_by(AircraftPosition.nearest_airport_icao)
        )
        current_counts = dict(current_q.all())

        # Per-airport: average unique aircraft per hour over the historical window.
        # Use per-airport hourly buckets so the average isn't diluted by hours
        # where we had no data (e.g. system was offline or newly deployed).
        avg_hourly_q = await self.db.execute(
            select(
                AircraftPosition.nearest_airport_icao,
                func.extract("hour", AircraftPosition.seen_at).label("hr"),
                func.extract("day", AircraftPosition.seen_at).label("dy"),
                func.count(func.distinct(AircraftPosition.hex_code)).label("cnt"),
            )
            .where(AircraftPosition.seen_at >= week_ago)
            .where(AircraftPosition.seen_at < hour_ago)
            .where(AircraftPosition.nearest_airport_icao.isnot(None))
            .group_by(
                AircraftPosition.nearest_airport_icao,
                literal_column("dy"),
                literal_column("hr"),
            )
        )
        # Build per-airport: sum of hourly counts and number of hours with data
        airport_hist: dict[str, dict] = {}
        for icao, hr, dy, cnt in avg_hourly_q.all():
            if icao not in airport_hist:
                airport_hist[icao] = {"total": 0, "hours": 0}
            airport_hist[icao]["total"] += cnt
            airport_hist[icao]["hours"] += 1

        # 24h hourly breakdown for sparklines
        hourly_q = await self.db.execute(
            select(
                AircraftPosition.nearest_airport_icao,
                func.extract("hour", AircraftPosition.seen_at).label("hr"),
                func.extract("day", AircraftPosition.seen_at).label("dy"),
                func.count(func.distinct(AircraftPosition.hex_code)),
            )
            .where(AircraftPosition.seen_at >= day_ago)
            .where(AircraftPosition.nearest_airport_icao.isnot(None))
            .group_by(
                AircraftPosition.nearest_airport_icao,
                literal_column("dy"),
                literal_column("hr"),
            )
        )
        hourly_data: dict[str, list[int]] = {}
        for icao, hr, dy, cnt in hourly_q.all():
            if icao not in hourly_data:
                hourly_data[icao] = [0] * 24
            hour_idx = int(hr)
            hourly_data[icao][hour_idx] = max(hourly_data[icao][hour_idx], cnt)

        results = []
        for airport in NEPAL_AIRPORTS:
            icao = airport["icao"]
            current_count = current_counts.get(icao, 0)
            hist = airport_hist.get(icao)

            if hist and hist["hours"] >= 3:
                # Only compute avg if we have at least 3 hours of historical data
                avg_count = hist["total"] / hist["hours"]
                pct_change = ((current_count - avg_count) / avg_count) * 100
                # Cap at ±200% to avoid absurd numbers with sparse data
                pct_change = max(-200, min(200, pct_change))
                status = "busier" if pct_change > 25 else ("quieter" if pct_change < -25 else "normal")
            else:
                avg_count = 0.0
                pct_change = 0.0
                status = "normal"

            results.append({
                "icao": icao,
                "name": airport["name"],
                "type": airport["type"],
                "current_count": current_count,
                "avg_count": round(avg_count, 1),
                "status": status,
                "percent_change": round(pct_change, 1),
                "hourly_counts": hourly_data.get(icao, [0] * 24),
            })

        results.sort(key=lambda x: x["current_count"], reverse=True)
        return results

    # ── Analytics Methods ─────────────────────────────────────────

    async def get_hourly_counts(self, days: int = 7) -> list[dict]:
        """Hourly aircraft counts (total + military) for charts."""
        from app.models.aviation import AircraftPosition

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(
                func.date_trunc("hour", AircraftPosition.seen_at).label("hour"),
                func.count(func.distinct(AircraftPosition.hex_code)).label("total"),
                func.count(func.distinct(
                    case(
                        (AircraftPosition.is_military.is_(True), AircraftPosition.hex_code),
                        else_=None,
                    )
                )).label("military"),
            )
            .where(AircraftPosition.seen_at >= cutoff)
            .group_by(literal_column("hour"))
            .order_by(literal_column("hour"))
        )

        return [
            {"hour": row.hour.isoformat() if row.hour else None,
             "total": row.total, "military": row.military}
            for row in result.all()
        ]

    async def get_military_stats(self, days: int = 7) -> dict:
        """Military aircraft stats with per-aircraft breakdown."""
        from app.models.aviation import AircraftPosition

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(
                AircraftPosition.hex_code,
                func.max(AircraftPosition.callsign).label("callsign"),
                func.max(AircraftPosition.registration).label("registration"),
                func.max(AircraftPosition.aircraft_type).label("aircraft_type"),
                func.count().label("observations"),
                func.max(AircraftPosition.seen_at).label("last_seen"),
            )
            .where(AircraftPosition.is_military.is_(True))
            .where(AircraftPosition.seen_at >= cutoff)
            .group_by(AircraftPosition.hex_code)
            .order_by(func.count().desc())
        )

        aircraft = []
        total_obs = 0
        for row in result.all():
            est_hours = round(row.observations * 60 / 3600, 1)
            total_obs += row.observations
            aircraft.append({
                "hex_code": row.hex_code,
                "callsign": row.callsign,
                "registration": row.registration,
                "aircraft_type": row.aircraft_type,
                "observations": row.observations,
                "est_flight_hours": est_hours,
                "last_seen": row.last_seen.isoformat() if row.last_seen else None,
            })

        daily_q = await self.db.execute(
            select(
                AircraftPosition.hex_code,
                func.date_trunc("day", AircraftPosition.seen_at).label("day"),
                func.count().label("obs"),
            )
            .where(AircraftPosition.is_military.is_(True))
            .where(AircraftPosition.seen_at >= cutoff)
            .group_by(AircraftPosition.hex_code, literal_column("day"))
        )
        daily_map: dict[str, dict[str, int]] = {}
        for row in daily_q.all():
            day_str = row.day.strftime("%Y-%m-%d") if row.day else ""
            daily_map.setdefault(row.hex_code, {})[day_str] = row.obs

        for ac in aircraft:
            ac["daily_activity"] = daily_map.get(ac["hex_code"], {})

        return {
            "unique_aircraft": len(aircraft),
            "total_observations": total_obs,
            "est_total_hours": round(total_obs * 60 / 3600, 1),
            "aircraft": aircraft,
        }

    async def get_top_aircraft(self, days: int = 7, limit: int = 20) -> list[dict]:
        """Most active aircraft by observation count."""
        from app.models.aviation import AircraftPosition

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(
                AircraftPosition.hex_code,
                func.max(AircraftPosition.callsign).label("callsign"),
                func.max(AircraftPosition.registration).label("registration"),
                func.max(AircraftPosition.aircraft_type).label("aircraft_type"),
                func.bool_or(AircraftPosition.is_military).label("is_military"),
                func.count().label("observations"),
                func.max(AircraftPosition.nearest_airport_icao).label("top_airport"),
            )
            .where(AircraftPosition.seen_at >= cutoff)
            .group_by(AircraftPosition.hex_code)
            .order_by(func.count().desc())
            .limit(limit)
        )

        return [
            {
                "hex_code": row.hex_code,
                "callsign": row.callsign,
                "registration": row.registration,
                "aircraft_type": row.aircraft_type,
                "is_military": row.is_military,
                "observations": row.observations,
                "est_hours": round(row.observations * 60 / 3600, 1),
                "top_airport": row.top_airport,
            }
            for row in result.all()
        ]

    async def get_aircraft_history(self, hex_code: str, hours: int = 24) -> list[dict]:
        """Get position history for a single aircraft."""
        from app.models.aviation import AircraftPosition

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.db.execute(
            select(AircraftPosition)
            .where(AircraftPosition.hex_code == hex_code.lower())
            .where(AircraftPosition.seen_at >= cutoff)
            .order_by(AircraftPosition.seen_at.asc())
        )
        rows = result.scalars().all()

        return [
            {
                "latitude": r.latitude,
                "longitude": r.longitude,
                "altitude_ft": r.altitude_ft,
                "ground_speed_kts": r.ground_speed_kts,
                "track_deg": r.track_deg,
                "seen_at": r.seen_at.isoformat(),
            }
            for r in rows
        ]

    async def cleanup_old_positions(self, keep_days: int = 7) -> int:
        """Delete positions older than keep_days."""
        from app.models.aviation import AircraftPosition

        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        result = await self.db.execute(
            delete(AircraftPosition).where(AircraftPosition.seen_at < cutoff)
        )
        await self.db.commit()
        deleted = result.rowcount
        logger.info("Cleaned up %d old aircraft positions (older than %d days)", deleted, keep_days)
        return deleted
