"""Common utility functions for Gardebot."""

from datetime import datetime

import pandas as pd  # type: ignore[import-untyped]

from gardebot.config import MONTHS_FR, WEEKDAYS_FR


def parse_iso_datetime(s: str) -> datetime:
    """Parse an ISO 8601 datetime string (e.g., '2025-09-22T09:05:31+02:00') into a timezone-aware Python datetime object."""
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        if s.endswith("Z"):
            return datetime.fromisoformat(s[:-1] + "+00:00")
        raise


def _format_french_date(date: pd.Timestamp) -> str:
    """Format a given datetime object into a French-style date string."""
    weekday = WEEKDAYS_FR[date.weekday()]
    month = MONTHS_FR[date.month]
    return f"{weekday} {date.day} {month} {date.year}"
