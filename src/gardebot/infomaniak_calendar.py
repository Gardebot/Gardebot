"""Calendar class to manage the events recorded in the Infomaniak Calendar."""

import hashlib
import logging
import os
from typing import Any, Dict, Optional

import pandas as pd  # type: ignore[import-untyped]
import pytz  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]
from icalendar import Calendar  # type: ignore[import-untyped]
from icalendar.cal import Component  # type: ignore[import-untyped]

from gardebot.datamanager import DataManager

LOGGER = logging.getLogger(__name__)
geneva_tz = pytz.timezone("Europe/Zurich")


class InfomaniakCalendar(DataManager):
    """Calendar class to manage the events recorded in the Infomaniak Calendar."""

    def __init__(self) -> None:
        """Initializes the Calendar class."""
        super().__init__()
        self.url = os.environ.get("CALENDAR_URL")

    def _get_name_from_event(self, event: Component) -> Optional[str]:
        """Extracts the name from an event.

        Args:
            event (Component): Event to extract the name from.

        Returns:
            Optional[str]: Name of the event or None if not found.
        """
        name = event.get("summary")
        if name is None or len(name) == 0:
            LOGGER.error(
                "⚠️ Missing name for one of your event. Not writing it in calendar dataframe ⚠️"
            )
            return None
        return str(name)

    def _get_location_from_event(self, event: Component) -> Optional[str]:
        """Extracts the location from an event.

        Args:
            event (Component): Event to extract the location from.

        Returns:
            Optional[str]: Location of the event or None if not found.
        """
        location = event.get("location")
        if location is None or len(location) == 0:
            LOGGER.error(
                "⚠️ Missing location for event '%s'. Not writing it in calendar dataframe ⚠️",
                event.get("summary"),
            )
            return None
        return str(location).split(",", maxsplit=1)[0]

    def _get_headcount_from_event(self, event: Component) -> Optional[int]:
        """Extracts the headcount from an event.

        Args:
            event (Component): Event to extract the headcount from.

        Returns:
            Optional[int]: Headcount of the event or None if not found.
        """
        headcount = event.get("description")
        if headcount is None or len(headcount) == 0 or int(headcount) == 0:
            LOGGER.error(
                "⚠️ Missing or zero headcount for event '%s'. Not writing it in calendar dataframe ⚠️",
                event.get("summary"),
            )
            return None
        return int(headcount)

    def _get_date_from_event(
        self, event: Component, key: str
    ) -> Optional[pd.Timestamp]:
        """Extracts the date from an event.

        Args:
            event (Component): Event to extract the date from.
            key (str): Key to extract the date from ('dtstart' or 'dtend').

        Returns:
            Optional[pd.Timestamp]: Date of the event or None if not found.
        """
        date = (
            pd.to_datetime(event.get(key).dt, errors="coerce")
            .tz_convert(geneva_tz)
            .tz_localize(None)
        )
        if pd.isnull(date):
            LOGGER.error(
                "⚠️ Missing or invalid %s date for event '%s'. Not writing it in calendar dataframe ⚠️",
                "start" if key == "dtstart" else "end",
                event.get("summary"),
            )
            return None
        return date

    def _get_date_start_from_event(self, event: Component) -> Optional[pd.Timestamp]:
        """Extracts the start date from an event.

        Args:
            event (Component): Event to extract the start date from.

        Returns:
            Optional[pd.Timestamp]: Start date of the event or None if not found.
        """
        return self._get_date_from_event(event, "dtstart")

    def _get_date_end_from_event(self, event: Component) -> Optional[pd.Timestamp]:
        """Extracts the end date from an event.

        Args:
            event (Component): Event to extract the end date from.

        Returns:
            Optional[pd.Timestamp]: End date of the event or None if not found.
        """
        return self._get_date_from_event(event, "dtend")

    def clean_event(self, event: Component) -> Optional[Dict[str, Any]]:
        """Cleans an event from the calendar.

        Args:
            event (Component): Event to clean.

        Returns:
            Dict[str, Any]: Cleaned event.
        """
        return {
            "name": self._get_name_from_event(event),
            "location": self._get_location_from_event(event),
            "headcount": self._get_headcount_from_event(event),
            "date_start": self._get_date_start_from_event(event),
            "date_end": self._get_date_end_from_event(event),
        }

    def fetch_raw_calendar_data(self) -> pd.DataFrame:
        """Fetch calendar data from URL and process it."""
        LOGGER.debug("Reading calendar from %s", self.url)

        response = requests.get(
            self.url, timeout=200  # pyright: ignore[reportArgumentType]
        )
        response.raise_for_status()
        cal = Calendar.from_ical(
            response.content  # pyright: ignore[reportArgumentType]
        )

        events_data = []

        for component in cal.walk():
            if component.name == "VEVENT":
                date_start = pd.to_datetime(
                    component.get("dtstart").dt, errors="coerce"
                ).tz_convert(geneva_tz)
                if date_start > pd.Timestamp.now(tz=geneva_tz):
                    clean_event = self.clean_event(component)
                    if clean_event is None:
                        LOGGER.error(
                            "Failed to clean event: %s", component.get("summary")
                        )
                        continue
                    if None not in clean_event.values():
                        events_data.append(clean_event)
                    else:
                        LOGGER.warning(
                            "Event '%s' has missing values and will be skipped.",
                            component.get("summary"),
                        )

        for event in events_data:
            event["uid"] = self._generate_unique_id(
                name=event["name"],
                location=event["location"],
                date_start=event["date_start"],
                date_end=event["date_end"],
            )

        df = pd.DataFrame(events_data)
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
        tmp_df = df.sort_values(by="date_start")
        counts = tmp_df.groupby(by="name").cumcount()
        names = tmp_df["name"].tolist()
        new_names = [
            f"{idx} {count+1}" if count > 0 else idx
            for idx, count in zip(names, counts)
        ]
        tmp_df["name"] = new_names
        return tmp_df

    def _generate_unique_id(
        self, date_end: pd.Timestamp, date_start: pd.Timestamp, name: str, location: str
    ) -> str:
        """Generate a unique identifier (UID) based on event details."""
        date_end_str = date_end.isoformat() if date_end else ""
        unique_string = f"{name}{location}{date_start.isoformat()}{date_end_str}"

        uid = hashlib.sha256(unique_string.encode()).hexdigest()
        return uid

    def convert_raw_to_fnd(self, df: pd.DataFrame = pd.DataFrame()) -> pd.DataFrame:
        """Convert raw dataframe to final dataframe with correct dtypes.

        Args:
            df (pd.DataFrame): Raw dataframe.

        Returns:
            pd.DataFrame: Final dataframe clean and ready to use for polls.
        """
        if df.empty:
            LOGGER.debug(
                "Empty calendar dataframe provided to convert_raw_to_fnd. Fetching raw data."
            )
            df = self.fetch_raw_calendar_data()
        df = self._handle_duplicate_names(df)
        df = self._remove_na(df)

        return df

    def sync_calendar_events(self) -> None:
        """Fetch calendar data and save it to Kdrive."""
        actual_df = self.convert_raw_to_fnd()
        db_df = self.load_dataframe("calendar")
        if db_df.empty:
            LOGGER.debug("No existing calendar in database. Saving current calendar.")
            self.save_dataframe(actual_df, "calendar")
            return None

        new_events = actual_df[~actual_df["uid"].isin(db_df["uid"])]
        if new_events.empty:
            LOGGER.debug("No new events in calendar.")
            return None
        df_updated = pd.concat([db_df, new_events], ignore_index=True)
        LOGGER.info(
            "New event(s) found and saved in calendar: %s",
            new_events[["name", "location", "date_start", "date_end"]].to_dict(
                orient="records"
            ),
        )
        self.save_dataframe(df_updated, "calendar")
        return None
