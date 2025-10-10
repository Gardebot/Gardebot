"""Common utility functions for Gardebot."""

import os
from datetime import datetime

import pandas as pd  # type: ignore[import-untyped]
from dopplersdk import DopplerSDK  # type: ignore[import-untyped]
from dotenv import load_dotenv

from gardebot.config import MONTHS_FR, WEEKDAYS_FR


def _load_secret(name: str, project: str = "gardebot", config: str = "dev") -> str:
    doppler = DopplerSDK()
    doppler_token = os.environ.get("DOPPLER_TOKEN")
    if not doppler_token:
        load_dotenv("credentials.env")
        doppler_token = os.environ.get("DOPPLER_TOKEN")
    if not doppler_token:
        raise ValueError("DOPPLER_TOKEN environment variable is not set.")
    doppler.set_access_token(doppler_token)
    result = doppler.secrets.get(project=project, name=name, config=config)
    return str(vars(result)["value"]["raw"])


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
