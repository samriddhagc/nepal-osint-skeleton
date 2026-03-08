"""
Bikram Sambat (BS) to Gregorian (AD) date converter.

Nepal uses the Bikram Sambat calendar which is ~56.7 years ahead of Gregorian.
This provides approximate conversion using lookup tables for accuracy.
"""

from datetime import datetime, timedelta
from typing import Optional

# Days in each month for BS years (index 0 = Baisakh, index 11 = Chaitra)
BS_MONTH_DAYS = {
    2075: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
    2076: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
    2077: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
    2078: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
    2079: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
    2080: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
    2081: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
    2082: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
    2083: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
    2084: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
    2085: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
    2086: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
    2087: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
    2088: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
    2089: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
    2090: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
}

# Reference point: 2080-01-01 BS = 2023-04-14 AD
BS_REFERENCE_YEAR = 2080
BS_REFERENCE_MONTH = 1
BS_REFERENCE_DAY = 1
AD_REFERENCE = datetime(2023, 4, 14)


def bs_to_ad(bs_date: str) -> Optional[datetime]:
    """
    Convert BS date string to Gregorian datetime.

    Args:
        bs_date: Date in format "YYYY-MM-DD" (e.g., "2082-09-11")

    Returns:
        Gregorian datetime or None if invalid
    """
    if not bs_date:
        return None

    try:
        parts = bs_date.split('-')
        if len(parts) != 3:
            return None

        bs_year = int(parts[0])
        bs_month = int(parts[1])
        bs_day = int(parts[2])

        # Validate ranges
        if bs_month < 1 or bs_month > 12 or bs_day < 1 or bs_day > 32:
            return None

        # Calculate days from reference
        total_days = 0

        # Add days for full years
        for year in range(BS_REFERENCE_YEAR, bs_year):
            month_days = BS_MONTH_DAYS.get(year)
            if month_days:
                total_days += sum(month_days)
            else:
                # Fallback: average BS year has ~365 days
                total_days += 365

        # Add days for full months in target year
        target_month_days = BS_MONTH_DAYS.get(bs_year)
        if target_month_days:
            for month_idx in range(bs_month - 1):
                total_days += target_month_days[month_idx]
        else:
            # Fallback approximation
            total_days += (bs_month - 1) * 30

        # Add remaining days
        total_days += bs_day - 1

        # Create AD date
        ad_date = AD_REFERENCE + timedelta(days=total_days)
        return ad_date

    except (ValueError, IndexError):
        return None
