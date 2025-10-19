"""Calendar class to manage the events recorded in the Infomaniak Calendar."""

import logging
import os
from typing import Any, Dict, Optional

import pandas as pd  # type: ignore[import-untyped]
import pytz  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]
from dotenv import load_dotenv
from icalendar import Calendar  # type: ignore[import-untyped]
from icalendar.cal import Component  # type: ignore[import-untyped]

LOGGER = logging.getLogger(__name__)
geneva_tz = pytz.timezone("Europe/Zurich")


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
        if name is None or len(name) == 0:
            LOGGER.error("⚠️ Missing name for one of your event. Not writing it in calendar dataframe ⚠️")
            return None
        return str(name)

    def _get_location_from_event(self, event: Component) -> Optional[str]:
        """Extracts the location from an event."""
        location = event.get("location")
        if location is None or len(location) == 0:
            LOGGER.error(
                "⚠️ Missing location for event '%s'. Not writing it in calendar dataframe ⚠️",
                event.get("summary"),
            )
            return None
        return str(location).split(",", maxsplit=1)[0]

    def _get_headcount_from_event(self, event: Component) -> Optional[int]:
        """Extracts the headcount from an event."""
        headcount = event.get("description")
        if headcount is None or len(headcount) == 0 or int(headcount) == 0:
            LOGGER.error(
                "⚠️ Missing or zero headcount for event '%s'. Not writing it in calendar dataframe ⚠️",
                event.get("summary"),
            )
            return None
        return int(headcount)

    def _get_date_from_event(self, event: Component, key: str) -> Optional[pd.Timestamp]:
        """Extracts the date from an event."""
        date = pd.to_datetime(event.get(key).dt, errors="coerce").tz_convert(geneva_tz).tz_localize(None)
        if pd.isnull(date):
            LOGGER.error(
                "⚠️ Missing or invalid %s date for event '%s'. Not writing it in calendar dataframe ⚠️",
                "start" if key == "dtstart" else "end",
                event.get("summary"),
            )
            return None
        return date

    def _get_start_date_from_event(self, event: Component) -> Optional[pd.Timestamp]:
        """Extracts the start date from an event."""
        return self._get_date_from_event(event, "dtstart")

    def _get_end_date_from_event(self, event: Component) -> Optional[pd.Timestamp]:
        """Extracts the end date from an event."""
        return self._get_date_from_event(event, "dtend")

    def clean_event(self, event: Component) -> Optional[Dict[str, Any]]:
        """Cleans an event from the calendar."""
        return {
            "name": self._get_name_from_event(event),
            "location": self._get_location_from_event(event),
            "headcount": self._get_headcount_from_event(event),
            "start_date": self._get_start_date_from_event(event),
            "end_date": self._get_end_date_from_event(event),
        }

    def fetch_calendar(self) -> pd.DataFrame:
        """Fetch calendar data from URL and process it."""
        LOGGER.debug("Reading calendar from %s", self.url)

        response = requests.get(
            self.url,
            timeout=200,  # pyright: ignore[reportArgumentType]
        )
        response.raise_for_status()
        cal = Calendar.from_ical(
            response.content  # pyright: ignore[reportArgumentType]
        )

        events_data = []
        for component in cal.walk():
            if component.name == "VEVENT":
                start_date = pd.to_datetime(component.get("dtstart").dt, errors="coerce").tz_convert(geneva_tz)
                if start_date > pd.Timestamp.now(tz=geneva_tz):
                    clean_event = self.clean_event(component)
                    if clean_event is None:
                        LOGGER.error("Failed to clean event: %s", component.get("summary"))
                        continue
                    if None not in clean_event.values():
                        events_data.append(clean_event)
                    else:
                        LOGGER.warning(
                            "Event '%s' has missing values and will be skipped.",
                            component.get("summary"),
                        )

        df = pd.DataFrame(events_data)
        df = self._handle_duplicate_names(df)
        df = self._remove_na(df)

        LOGGER.debug("Calendar data processed with %d events", len(df))
        return df

    def _remove_na(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove rows with any NaN values."""
        for _, row in df.iterrows():
            for col in [c for c in df.columns if c != "name"]:
                if pd.isnull(row[col]):
                    LOGGER.warning(
                        "⚠️ Missing value for event '%s' in column '%s'. Not writing it in calendar dataframe ⚠️",
                        row["name"],
                        col,
                    )

        return df.dropna(axis=1, how="any")

    def _handle_duplicate_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Handle duplicate event names by appending a counter in chronological order."""
        tmp_df = df.sort_values(by="start_date")
        counts = tmp_df.groupby(by="name").cumcount()
        names = tmp_df["name"].tolist()
        new_names = [f"{idx} {count + 1}" if count > 0 else idx for idx, count in zip(names, counts)]
        tmp_df["name"] = new_names
        return tmp_df
