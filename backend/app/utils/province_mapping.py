"""Province to government source domain mapping for Nepal."""
from typing import List, Optional

# Mapping of province names to their government source domains
PROVINCE_SOURCES = {
    "Koshi": ["koshi.gov.np"],
    "Madhesh": ["madhesh.gov.np"],
    "Bagmati": ["bagmati.gov.np"],
    "Gandaki": ["gandaki.gov.np"],
    "Lumbini": ["lumbini.gov.np"],
    "Karnali": ["karnali.gov.np"],
    "Sudurpashchim": ["sudurpashchim.gov.np"],
}

# Case-insensitive lookup for convenience
_PROVINCE_SOURCES_LOWER = {k.lower(): v for k, v in PROVINCE_SOURCES.items()}

# All valid province names (normalized to title case)
VALID_PROVINCES = list(PROVINCE_SOURCES.keys())


def get_sources_for_province(province: str) -> Optional[List[str]]:
    """
    Get the list of source domains for a given province.

    Args:
        province: Province name (case-insensitive)

    Returns:
        List of source domains or None if province not found
    """
    return _PROVINCE_SOURCES_LOWER.get(province.lower())


def normalize_province_name(province: str) -> Optional[str]:
    """
    Normalize a province name to its canonical form.

    Args:
        province: Province name (case-insensitive)

    Returns:
        Canonical province name or None if not found
    """
    province_lower = province.lower()
    for canonical_name in PROVINCE_SOURCES:
        if canonical_name.lower() == province_lower:
            return canonical_name
    return None


def is_valid_province(province: str) -> bool:
    """
    Check if a province name is valid.

    Args:
        province: Province name to check (case-insensitive)

    Returns:
        True if valid province name, False otherwise
    """
    return province.lower() in _PROVINCE_SOURCES_LOWER
