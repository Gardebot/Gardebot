"""Calendar class to manage the events recorded in the Infomaniak Calendar."""

import hashlib
import logging
import os

import pandas as pd  # type: ignore[import-untyped]
import pytz  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]
from icalendar import Calendar  # type: ignore[import-untyped]

from gardebot.datamanager import DataManager

LOGGER = logging.getLogger(__name__)
geneva_tz = pytz.timezone("Europe/Zurich")


class InfomaniakCalendar(DataManager):
    """Calendar class to manage the events recorded in the Infomaniak Calendar."""

    def __init__(self) -> None:
        """Initializes the Calendar class."""
        super().__init__()
        self.url = os.environ.get("CALENDAR_URL")

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
                    events_data.append(
                        {
                            "name": str(component.get("summary")),
                            "location": str(component.get("location")),
                            "headcount": int(component.get("description")),
                            "date_start": date_start.tz_localize(None),
                            "date_end": pd.to_datetime(
                                component.get("dtend").dt, errors="coerce"
                            )
                            .tz_convert(geneva_tz)
                            .tz_localize(None),
                        }
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

        return df.dropna(axis=0, how="any")

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
            LOGGER.warning(
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
            LOGGER.info("No existing calendar in database. Saving current calendar.")
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
