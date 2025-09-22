"""Common utility functions for Gardebot."""

from datetime import datetime


def parse_iso_datetime(s: str) -> datetime:
    """Parse an ISO 8601 datetime string (e.g., '2025-09-22T09:05:31+02:00') into a timezone-aware Python datetime object."""
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        if s.endswith("Z"):
            return datetime.fromisoformat(s[:-1] + "+00:00")
        raise
