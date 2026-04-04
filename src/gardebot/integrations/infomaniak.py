"""Calendar class to manage events recorded in the Infomaniak Calendar (with improved cleaning)."""

import os
from typing import Any, Dict, Optional

import pandas as pd  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]
from dotenv import load_dotenv
from icalendar import Calendar  # type: ignore[import-untyped]
from icalendar.cal import Component  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.config import GENEVA_TZ

LOGGER = get_logger(__name__)


class InfomaniakCalendar:
    """Calendar class to manage the events recorded in the Infomaniak Calendar."""

    def __init__(self) -> None:
        """Initializes the Calendar class."""
        self.url = os.environ.get("CALENDAR_URL")
        if self.url is None:
            load_dotenv(dotenv_path="credentials.env")
            self.url = os.environ.get("CALENDAR_URL")

    def _get_name_from_event(self, event: Component) -> Optional[str]:
        """Extracts the name from an event."""
        name = event.get("summary")
        if not name:
            LOGGER.error("missing_event_name")
            return None
        return str(name)

    def _get_location_from_event(self, event: Component) -> Optional[str]:
        """Extracts the location from an event."""
        location = event.get("location")
        if not location:
            LOGGER.error("missing_event_location", summary=event.get("summary"))
            return None
        return str(location).split(",", maxsplit=1)[0]

    def _get_headcount_from_event(self, event: Component) -> Optional[int]:
        """Extracts the headcount from an event."""
        headcount = event.get("description")
        if headcount is None or len(headcount) == 0 or int(headcount) == 0:
            LOGGER.error("invalid_headcount", summary=event.get("summary"))
            return None
        return int(headcount)

    def _get_date_from_event(self, event: Component, key: str) -> Optional[pd.Timestamp]:
        """Extracts the date from an event."""
        date = pd.to_datetime(event.get(key).dt, errors="coerce").tz_convert(GENEVA_TZ).tz_localize(None)
        if pd.isnull(date):
            LOGGER.error("invalid_date_field", summary=event.get("summary"), field=key)
            return None
        return date

    def _get_ical_uid_from_event(self, event: Component) -> Optional[str]:
        """Extracts the ICS UID from an event."""
        uid = event.get("uid")
        if not uid:
            LOGGER.error("missing_event_ical_uid", summary=event.get("summary"))
            return None
        return str(uid)

    def clean_event(self, event: Component) -> Optional[Dict[str, Any]]:
        """Cleans an event from the calendar."""
        return {
            "name": self._get_name_from_event(event),
            "location": self._get_location_from_event(event),
            "headcount": self._get_headcount_from_event(event),
            "start_date": self._get_date_from_event(event, "dtstart"),
            "end_date": self._get_date_from_event(event, "dtend"),
            "ical_uid": self._get_ical_uid_from_event(event),
        }

    def fetch_calendar(self) -> pd.DataFrame:
        """Fetch and parse the calendar events into a DataFrame."""
        if not self.url:
            LOGGER.error("calendar_url_missing")
            return pd.DataFrame()
        LOGGER.debug("calendar_fetching", url=self.url)
        response = requests.get(self.url, timeout=200)
        response.raise_for_status()
        cal = Calendar.from_ical(response.content)

        events_data = []
        for component in cal.walk():
            if component.name == "VEVENT":
                start_date = pd.to_datetime(component.get("dtstart").dt, errors="coerce").tz_convert(GENEVA_TZ)
                if start_date > pd.Timestamp.now(tz=GENEVA_TZ):
                    clean_event = self.clean_event(component)
                    if clean_event is None or None in clean_event.values():
                        LOGGER.warning("event_skipped_missing_values", summary=component.get("summary"))
                        continue
                    events_data.append(clean_event)

        df = pd.DataFrame(events_data)
        df = self._remove_na_rows(df)
        LOGGER.debug("calendar_events_processed", count=len(df))
        return df

    def _remove_na_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove rows containing NaNs (previously attempted column removal)."""
        before = len(df)
        cleaned = df.dropna(axis=0, how="any")
        dropped = before - len(cleaned)
        if dropped:
            LOGGER.warning("calendar_rows_dropped", dropped=dropped)
        return cleaned

    def _handle_duplicate_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Suffix duplicate names chronologically: 'Name 2', 'Name 3', etc."""
        if df.empty or "name" not in df.columns:
            return df
        tmp = df.sort_values(by="start_date").copy()
        counts = tmp.groupby("name").cumcount()
        tmp["name"] = [f"{n} {c + 1}" if c > 0 else n for n, c in zip(tmp["name"].tolist(), counts.tolist())]
        return tmp
