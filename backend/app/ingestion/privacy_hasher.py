"""Privacy-preserving hasher for PII fields (phone numbers, etc).

Uses HMAC-SHA256 with a secret salt so that:
  - Same input always produces the same hash (enables matching)
  - Hash cannot be reversed to recover the original value
  - Salt prevents rainbow table attacks

Usage:
    from app.ingestion.privacy_hasher import hash_phone

    h1 = hash_phone("9808565443")
    h2 = hash_phone("9808565443")
    assert h1 == h2  # Same phone -> same hash -> connection detected
"""
import hashlib
import hmac
import os

from app.config import get_settings

# Salt loaded from env; falls back to a default for development only.
# In production, set IRD_HASH_SALT to a strong random value.
_SALT: bytes | None = None


def _get_salt() -> bytes:
    global _SALT
    if _SALT is None:
        settings = get_settings()
        salt_str = getattr(settings, "ird_hash_salt", None) or os.environ.get(
            "IRD_HASH_SALT",
            "nepal-osint-v5-default-dev-salt-CHANGE-IN-PRODUCTION",
        )
        _SALT = salt_str.encode("utf-8")
    return _SALT


def hash_phone(phone: str | None) -> str | None:
    """Hash a phone number using HMAC-SHA256.

    Normalises the phone first: strips whitespace, leading +977 / 977, leading 0.
    Returns hex digest or None if input is empty/None.
    """
    if not phone:
        return None

    normalised = _normalise_phone(phone)
    if not normalised:
        return None

    return hmac.new(_get_salt(), normalised.encode("utf-8"), hashlib.sha256).hexdigest()


def _normalise_phone(phone: str) -> str:
    """Normalise a Nepali phone number to a canonical form.

    Examples:
        +977-9808565443 -> 9808565443
        977 9808565443  -> 9808565443
        098-123456      -> 98123456  (landline, strip leading 0)
        9808565443      -> 9808565443
    """
    # Strip all non-digit characters
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        return ""

    # Strip country code +977 / 977
    if digits.startswith("977") and len(digits) > 10:
        digits = digits[3:]

    # Strip leading zero (landline area code prefix)
    if digits.startswith("0") and len(digits) > 7:
        digits = digits[1:]

    # Reject placeholder/junk values — real Nepali numbers are 7+ digits
    if len(digits) < 7:
        return ""

    return digits
