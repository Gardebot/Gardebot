"""Domain models for Gardebot application."""

from __future__ import annotations

import hashlib
from typing import List, Optional, Union

import pandas as pd  # type: ignore[import-untyped]
from pandas._libs.tslibs.nattype import NaTType  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from gardebot.common.common import _format_french_date
from gardebot.common.logging_configuration import get_logger
from gardebot.config import GENEVA_TZ, MAX_NB_REMINDER, MINIMUM_ELAPSED_HOURS, TIME_BEFORE_PUBLICATION_DAY

LOGGER = get_logger(__name__)


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
    title: str
    location: str
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    headcount: int
    poll_uid: Optional[str] = None
    published_date: Optional[Union[pd.Timestamp, NaTType]] = None
    scheduled_publication_date: pd.Timestamp = pd.Timestamp(0)
    nb_reminder: int = 0

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _ensure_ts(cls, v: pd.Timestamp) -> pd.Timestamp:
        """Ensure date-like fields are pandas Timestamps."""
        if isinstance(v, pd.Timestamp):
            return v
        return pd.Timestamp(v)

    @computed_field  # type: ignore[misc]
    @property
    def uid(self) -> str:
        """Generate a unique identifier for the event."""
        base = f"{self.title}{self.location}{self.start_date}{self.end_date}"
        return hashlib.sha256(base.encode()).hexdigest()

    @computed_field  # type: ignore[misc]
    @property
    def poll_string(self) -> str:
        """Generate a string for the poll."""
        start_date_str = _format_french_date(self.start_date)
        time_start = f"{self.start_date.hour}h{self.start_date.minute:02d}"
        if self.start_date.date() == self.end_date.date():
            time_end = f"{self.end_date.hour}h{self.end_date.minute:02d}"
            time_part = f"de {time_start} à {time_end}"
        else:
            end_date_str = _format_french_date(self.end_date)
            time_end = f"{self.end_date.hour}h{self.end_date.minute:02d}"
            time_part = f"{time_start} au {end_date_str} {time_end}"
        result = f"{self.title} : {start_date_str} {time_part}, {self.location}"
        return result[0].upper() + result[1:]

    @model_validator(mode="after")
    def _default_pub_date(self) -> "Event":
        """Set default scheduled publication date."""
        self.scheduled_publication_date = self.start_date - pd.Timedelta(days=TIME_BEFORE_PUBLICATION_DAY)
        return self

    def should_send_reminder(self) -> bool:
        """Determine whether a reminder should be sent based on elapsed time and limits."""
        if self.published_date is None:
            return False
        if self.nb_reminder >= MAX_NB_REMINDER:
            return False
        ref = self.published_date
        if ref.tzinfo is None:
            ref = ref.tz_localize(GENEVA_TZ)
        limit_elapsed = MINIMUM_ELAPSED_HOURS * (self.nb_reminder + 1)
        should_remind: bool = (pd.Timestamp.now(tz=GENEVA_TZ) - ref) >= pd.Timedelta(hours=limit_elapsed)
        return should_remind

    def increment_reminder(self) -> Event:
        """Return a new Event model with incremented reminder count."""
        return self.model_copy(update={"nb_reminder": self.nb_reminder + 1})

    def set_published_date(self, when: Optional[pd.Timestamp] = None) -> Event:
        """Return a new Event with published_date set."""
        when_ts = when or pd.Timestamp.now(tz=GENEVA_TZ)
        return self.model_copy(update={"published_date": when_ts})

    def is_published(self) -> bool:
        """Check if the event has been published."""
        if self.published_date is None:
            return False
        if self.poll_uid is None:
            return False
        return True

    def with_poll_uid(self, poll_uid: str) -> "Event":
        """Return a new Event with poll_uid set (idempotent / protective)."""
        if self.poll_uid and self.poll_uid != poll_uid:
            raise ValueError(f"poll_uid already set to {self.poll_uid}")
        return self.model_copy(update={"poll_uid": poll_uid})


class VoteRecord(BaseModel):
    """Represents a single vote row (normalized storage)."""

    event: Event
    sapeur: Sapeur
    value: Optional[bool] = Field(None, description="One of: 'Présent'=True, 'Absent':False, or None (no response).")


class OnDutyAssignment(BaseModel):
    """Represents an on-duty assignment row."""

    event: Event
    sapeur_list: List[Sapeur]
    assigned: bool = True
