"""Stub CandidateProfileResolver for open-source skeleton.

The full implementation resolves candidate profiles from multiple data sources
(JSON files, database overrides, etc.). This stub returns passthrough data.
"""
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class ResolvedProfile:
    """Resolved candidate profile (passthrough in skeleton)."""
    photo_url: Optional[str] = None
    age: Optional[int] = None
    education: Optional[str] = None
    profession: Optional[str] = None
    criminal_cases: int = 0
    assets_npr: Optional[float] = None
    source: str = "database"


class CandidateProfileResolver:
    """Stub resolver that returns database values as-is."""

    def __init__(self, db=None):
        self.db = db

    async def get_active_overrides_map(self, external_ids: list[str]) -> dict:
        """Return empty overrides map."""
        return {}

    def resolve_candidate_profile(self, candidate: Any, overrides: dict = None) -> ResolvedProfile:
        """Return profile from candidate's own database fields."""
        return ResolvedProfile(
            photo_url=getattr(candidate, 'photo_url', None),
            age=getattr(candidate, 'age', None),
            education=getattr(candidate, 'education', None),
            profession=getattr(candidate, 'profession', None),
            criminal_cases=getattr(candidate, 'criminal_cases', 0) or 0,
            assets_npr=getattr(candidate, 'assets_npr', None),
            source="database",
        )
