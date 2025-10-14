"""Domain models for Gardebot application."""

from __future__ import annotations

import hashlib
from typing import Optional

import pandas as pd  # type: ignore[import-untyped]
import pytz  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from gardebot.config import (
    MAX_NB_REMINDER,
    MINIMUM_ELAPSED_HOURS,
    TIME_BEFORE_PUBLICATION_DAY,
)

geneva_tz = pytz.timezone("Europe/Zurich")


def _format_french_date(ts: pd.Timestamp) -> str:
    """Lightweight re-export (or inline) of original formatting to avoid import cycle."""
    timestamp_str: str = ts.strftime("%d/%m/%Y")
    return timestamp_str


class Sapeur(BaseModel):
    """Represents a participant (sapeur)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    uid: str
    name: str
    pushname: str
    phone: str
    joined_date: pd.Timestamp
    group_id: str

    @field_validator("joined_date", mode="before")
    @classmethod
    def _ensure_timestamp(cls, v: pd.Timestamp) -> pd.Timestamp:
        """Ensure joined_date is a pandas Timestamp."""
        if isinstance(v, pd.Timestamp):
            return v
        return pd.Timestamp(v)


class Event(BaseModel):
    """Domain model for an event (garde)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    uid: str
    title: str
    location: str
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    headcount: int
    poll_uid: Optional[str] = None
    admin_poll_uid: Optional[str] = None
    poll_string: str
    scheduled_publication_date: pd.Timestamp
    published_date: Optional[pd.Timestamp] = None
    nb_reminder: int = 0

    @field_validator("start_date", "end_date", "scheduled_publication_date", mode="before")
    @classmethod
    def _ensure_ts(cls, v: pd.Timestamp) -> pd.Timestamp:
        """Ensure date-like fields are pandas Timestamps."""
        if isinstance(v, pd.Timestamp):
            return v
        return pd.Timestamp(v)

    @field_validator("uid")
    @classmethod
    def _auto_uid(cls, info: ValidationInfo, v: Optional[str] = None) -> str:
        """Generate UID if not provided."""
        if v:
            return v
        values = info.context
        if values is None:
            raise ValueError("Cannot compute uid without context")
        base = f"{values.get('title')}{values.get('location')}{values.get('start_date')}{values.get('end_date')}"
        return hashlib.sha256(base.encode()).hexdigest()

    @field_validator("poll_string")
    @classmethod
    def _auto_poll_string(cls, v: Optional[str] = None, info: ValidationInfo) -> str:
        """Generate poll string if absent."""
        if v:
            return v
        values = info.context
        if values is None:
            raise ValueError("Cannot compute poll_string without context")
        start: pd.Timestamp = values["start_date"]
        end: pd.Timestamp = values["end_date"]
        title = values["title"]
        location = values["location"]
        start_date_str = _format_french_date(start)
        time_start = f"{start.hour}h{start.minute:02d}"
        if start.date() == end.date():
            time_end = f"{end.hour}h{end.minute:02d}"
            time_part = f"de {time_start} à {time_end}"
        else:
            end_date_str = _format_french_date(end)
            time_end = f"{end.hour}h{end.minute:02d}"
            time_part = f"{time_start} au {end_date_str} {time_end}"
        result = f"{title} : {start_date_str} {time_part}, {location}"
        return result[0].upper() + result[1:]

    @field_validator("scheduled_publication_date")
    @classmethod
    def _auto_sched_pub(cls, info: ValidationInfo, v: Optional[pd.Timestamp] = None) -> pd.Timestamp:
        if v:
            return v
        values = info.context
        if values is None:
            raise ValueError("Cannot compute scheduled_publication_date without context")
        start: pd.Timestamp = values["start_date"]
        return start - pd.Timedelta(days=TIME_BEFORE_PUBLICATION_DAY)

    def should_send_reminder(self) -> bool:
        """Determine whether a reminder should be sent based on elapsed time and limits."""
        if self.published_date is None:
            return False
        if self.nb_reminder >= MAX_NB_REMINDER:
            return False
        ref = self.published_date
        if ref.tzinfo is None:
            ref = ref.tz_localize(geneva_tz)
        limit_elapsed = MINIMUM_ELAPSED_HOURS * (self.nb_reminder + 1)
        should_remind: bool = (pd.Timestamp.now(tz=geneva_tz) - ref) >= pd.Timedelta(hours=limit_elapsed)
        return should_remind

    def increment_reminder(self) -> Event:
        """Return a new Event model with incremented reminder count."""
        return self.model_copy(update={"nb_reminder": self.nb_reminder + 1})

    def mark_published(self, when: Optional[pd.Timestamp] = None) -> Event:
        """Return a new Event with published_date set."""
        when_ts = when or pd.Timestamp.now(tz=geneva_tz)
        return self.model_copy(update={"published_date": when_ts})


class VoteRecord(BaseModel):
    """Represents a single vote row (normalized storage)."""

    poll_string: str
    voter_name: str
    vote: Optional[str] = Field(None, description="One of: 'Présent', 'Absent', or None (no response).")


class OnDutyAssignment(BaseModel):
    """Represents an on-duty assignment row."""

    poll_string: str
    sapeur_name: str
    assigned: bool = True


class ParticipationScore(BaseModel):
    """Represents a computed participation score for nomination."""

    sapeur_name: str
    score: float
    source: str  # e.g., 'non_responding' or 'absent'
