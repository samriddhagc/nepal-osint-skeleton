"""Source Reliability API endpoints (stub - analyst features excluded from skeleton)."""
from fastapi import APIRouter

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/reliability")
async def list_source_reliability():
    """List source reliability ratings (stub)."""
    return {"sources": [], "total": 0}
