"""API v1 router aggregator."""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_dev

from app.api.v1 import (
    stories,
    disasters, disaster_alerts, weather,
    announcements, market, seismic, curfew,
    twitter, elections, energy, auth,
    # Parliament (MP Performance Index)
    parliament,
    # Notifications
    notifications,
    # Companies (public stats)
    companies,
    # Situation Briefs
    briefs,
    # Live election results (ECN)
    election_results,
    # Manifesto Promise Tracker
    promises,
    # Government procurement (Bolpatra)
    procurement,
    # Sources
    sources,
    # Aviation
    aviation,
    # System (dev)
    system,
)

router = APIRouter(prefix="/api/v1")

# Authentication (contains both public + protected endpoints)
router.include_router(auth.router)

# Dependency buckets
any_auth = [Depends(get_current_user)]
dev_auth = [Depends(require_dev)]

# ============================================================
# Consumer-safe (JWT required)
# ============================================================
router.include_router(stories.router, dependencies=any_auth)
router.include_router(disasters.router, dependencies=any_auth)
router.include_router(disaster_alerts.router, dependencies=any_auth)
router.include_router(weather.router, dependencies=any_auth)
router.include_router(announcements.router, dependencies=any_auth)
router.include_router(market.router, dependencies=any_auth)
router.include_router(seismic.router, dependencies=any_auth)
router.include_router(curfew.router, dependencies=any_auth)
router.include_router(twitter.router, dependencies=any_auth)
router.include_router(elections.router, dependencies=any_auth)
router.include_router(energy.router, dependencies=any_auth)
router.include_router(parliament.router, dependencies=any_auth)
router.include_router(notifications.router, dependencies=any_auth)
router.include_router(briefs.router, dependencies=any_auth)
router.include_router(companies.router, dependencies=any_auth)
router.include_router(procurement.router, dependencies=any_auth)
router.include_router(sources.router, dependencies=any_auth)
router.include_router(aviation.router, dependencies=any_auth)
router.include_router(election_results.router)  # Public - election data is open
router.include_router(promises.router, dependencies=any_auth)

# ============================================================
# Dev-only (JWT + dev role required)
# ============================================================
router.include_router(system.router, dependencies=dev_auth)
