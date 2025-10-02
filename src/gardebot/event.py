"""Module for managing events and their synchronization with an external calendar."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union

import pandas as pd  # type: ignore[import-untyped]
import pytz  # type: ignore[import-untyped]

from gardebot.common.common import _format_french_date
from gardebot.config import (
    MAX_NB_REMINDER,
    MINIMUM_ELAPSED_HOURS,
    TIME_BEFORE_PUBLICATION_DAY,
)
from gardebot.datamanager import DataManager
from gardebot.infomaniak import InfomaniakCalendar

LOGGER = logging.getLogger(__name__)
geneva_tz = pytz.timezone("Europe/Zurich")


class Event:
    """Handles event object."""

    def __init__(  # noqa: PLR0913
        self,
        title: str,
        location: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        headcount: int,
        nb_reminder: int = 0,
        uid: Optional[str] = None,
        poll_uid: Optional[str] = None,
        admin_poll_uid: Optional[str] = None,
        poll_string: Optional[str] = None,
        published_date: Optional[pd.Timestamp] = None,
        scheduled_publication_date: Optional[pd.Timestamp] = None,
    ) -> None:
        """Initialize the Event instance."""
        self.title = title
        self.location = location
        self.start_date = start_date
        self.end_date = end_date
        self.headcount = headcount
        self.poll_uid = poll_uid
        self.admin_poll_uid = admin_poll_uid
        if uid is None:
            self.uid = self._init_uid()
        else:
            self.uid = uid
        if poll_string is None:
            self.poll_string = self._init_pollstring()
        else:
            self.poll_string = poll_string
        if scheduled_publication_date is None:
            self.scheduled_publication_date = self._init_scheduled_publication_date()
        else:
            self.scheduled_publication_date = scheduled_publication_date
        self.nb_reminder = nb_reminder
        self.published_date = published_date

    def _init_uid(self) -> str:
        """Generate a unique identifier (UID) based on event details."""
        end_date_str = self.end_date.isoformat()
        unique_string = f"{self.title}{self.location}{self.start_date.isoformat()}{end_date_str}"

        uid = hashlib.sha256(unique_string.encode()).hexdigest()
        return uid

    def _init_pollstring(self) -> str:
        """Generate a unique poll string based on event details."""
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

    def _init_scheduled_publication_date(self) -> pd.Timestamp:
        """Calculate the scheduled publication date based on the event's start date."""
        return self.start_date - pd.Timedelta(days=TIME_BEFORE_PUBLICATION_DAY)

    def get_attr(self, attr: str) -> Union[str, int, pd.Timestamp, None]:
        """Get an attribute of the event by name."""
        if not hasattr(self, attr):
            raise ValueError(f"Event has no attribute {attr}.")
        return getattr(self, attr)

    def get_published_date(self) -> Optional[pd.Timestamp]:
        """Get the published date of the event."""
        return self.published_date

    def get_poll_string(self) -> str:
        """Get the poll string of the event."""
        return self.poll_string

    def get_scheduled_publication_date(self) -> pd.Timestamp:
        """Get the scheduled publication date of the event."""
        return self.scheduled_publication_date

    def get_headcount(self) -> int:
        """Get the headcount of the event."""
        return self.headcount

    def get_nb_reminder(self) -> Optional[int]:
        """Get the number of reminders sent for the event."""
        return self.nb_reminder

    def get_poll_uid(self) -> Optional[str]:
        """Get the poll UID of the event."""
        return self.poll_uid

    def get_admin_poll_uid(self) -> Optional[str]:
        """Get the admin poll UID of the event."""
        return self.admin_poll_uid

    def get_title(self) -> str:
        """Get the title of the event."""
        return self.title

    def get_location(self) -> str:
        """Get the location of the event."""
        return self.location

    def get_start_date(self) -> pd.Timestamp:
        """Get the start date of the event."""
        return self.start_date

    def get_end_date(self) -> pd.Timestamp:
        """Get the end date of the event."""
        return self.end_date

    def set_attr(self, attr: str, value: Any) -> None:
        """Set an attribute of the event by name."""
        if not hasattr(self, attr):
            raise ValueError(f"Event has no attribute {attr}.")
        setattr(self, attr, value)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the Event instance to a dictionary."""
        return {
            "uid": self.uid,
            "title": self.title,
            "location": self.location,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "headcount": self.headcount,
            "poll_uid": self.poll_uid,
            "admin_poll_uid": self.admin_poll_uid,
            "poll_string": self.poll_string,
            "scheduled_publication_date": self.scheduled_publication_date,
            "published_date": self.published_date,
            "nb_reminder": self.nb_reminder,
        }

    def test_elapse_time(self) -> bool:
        """Check if enough time has elapsed since the poll was published."""
        if self.published_date is None:
            return False
        limit_elapsed = MINIMUM_ELAPSED_HOURS * (self.nb_reminder + 1)
        if self.published_date.tzinfo is None:
            timestamp = self.published_date.tz_localize(geneva_tz)
        else:
            timestamp = self.published_date
        if datetime.now(tz=geneva_tz) - timestamp >= timedelta(hours=limit_elapsed):
            LOGGER.debug(
                "Poll %s was sent more than %s hour ago.",
                self.poll_string,
                limit_elapsed,
            )
            return True
        LOGGER.debug(
            "Poll %s as was sent less than %s hour ago.",
            self.poll_string,
            limit_elapsed,
        )
        return False

    def test_max_reminder(self) -> bool:
        """Check if the maximum number of reminders has been reached."""
        if self.nb_reminder >= MAX_NB_REMINDER:
            LOGGER.debug(
                "The maximum number of reminders (%s) has been reached for %s.",
                MAX_NB_REMINDER,
                self.poll_string,
            )
            return True
        return False

    def check_reminder(self) -> bool:
        """Check if a reminder needs to be sent for the event."""
        if self.published_date is None:
            LOGGER.debug("The poll %s has not been published yet.", self.poll_string)
            return False
        if self.test_elapse_time():
            return True
        if self.test_max_reminder():
            return False
        return True

    def increment_nb_reminder(self) -> None:
        """Increment the number of reminders sent for the event."""
        self.nb_reminder += 1


class EventManager(DataManager):
    """Manages event data."""

    def __init__(self) -> None:
        """Initialize the EventManager instance."""
        super().__init__(filename="gardes")

    def _fetch_gardes(self) -> pd.DataFrame:
        """Initialize the gardes dataframe by fetching from Infomaniak."""
        infomaniak = InfomaniakCalendar()
        calendar_df = infomaniak.fetch_calendar()
        gardes_list = []
        for _, row in calendar_df.iterrows():
            event = Event(
                title=row["name"],
                location=row["location"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                headcount=row["headcount"],
            )
            gardes_list.append(event.to_dict())
        garde_df = pd.DataFrame(gardes_list)
        garde_df = self._consecutive_events(garde_df)
        return garde_df

    def save_gardes(self, garde_df: pd.DataFrame) -> None:
        """Save the gardes to the data storage."""
        self.save_dataframe(garde_df, self.filename)

    def load_gardes(self) -> pd.DataFrame:
        """Load the gardes from the data storage."""
        garde_df = self.load_dataframe(filename=self.filename)
        if garde_df.empty:
            LOGGER.warning("No existing gardes in database. Creating one.")
            garde_df = self._fetch_gardes()
            self.save_gardes(garde_df)
            LOGGER.debug("Created new gardes database with %d events.", len(garde_df))
        return garde_df

    def synch_gardes(self) -> None:
        """Update the gardes dataframe with new events."""
        garde_df = self.load_gardes()
        new_garde_df = self._fetch_gardes()
        self.synch_dataframe(garde_df, new_garde_df, key="uid")

    def update_gardes(self, garde: Event) -> None:
        """Update a single garde event in the data storage."""
        garde_df = self.load_gardes()
        garde_dict = garde.to_dict()
        for key, value in garde_dict.items():
            garde_df.loc[garde_df["uid"] == garde.uid, key] = value
        self.save_gardes(garde_df)

    def from_dict(self, data: Dict[str, Any]) -> Event:
        """Create an Event instance from a dictionary."""
        return Event(
            title=data["title"],
            location=data["location"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            headcount=data["headcount"],
            uid=data.get("uid"),
            poll_uid=data.get("poll_uid"),
            admin_poll_uid=data.get("admin_poll_uid"),
            poll_string=data.get("poll_string"),
            published_date=data.get("published_date"),
            scheduled_publication_date=data.get("scheduled_publication_date"),
            nb_reminder=data.get("nb_reminder", 0),
        )

    def get_garde_by_uid(self, uid: str) -> Event:
        """Get a garde by its unique identifier (UID)."""
        garde_ser = self.load_gardes().set_index("uid").loc[uid]
        if garde_ser.empty:
            raise ValueError(f"Garde with uid {uid} not found.")
        return self.from_dict(garde_ser.to_dict())  # pyright: ignore[reportArgumentType]

    def get_garde_by_pollstring(self, poll_string: str) -> Event:
        """Get a garde by its poll string."""
        garde_ser = self.load_gardes().set_index("poll_string").loc[poll_string]
        if garde_ser.empty:
            raise ValueError(f"Garde with poll_string {poll_string} not found.")
        return self.from_dict(garde_ser.to_dict())  # pyright: ignore[reportArgumentType]

    def get_gardes_by_polluid(self, poll_uid: str) -> Event:
        """Get gardes by its poll UID."""
        garde_ser = self.load_gardes().set_index("poll_uid").loc[poll_uid]
        if garde_ser.empty:
            raise ValueError(f"Garde with poll_uid {poll_uid} not found.")
        return self.from_dict(garde_ser.to_dict())  # pyright: ignore[reportArgumentType]

    def get_gardes_by_admin_poll_uid(self, admin_poll_uid: str) -> Event:
        """Get gardes by its admin poll UID."""
        garde_ser = self.load_gardes().set_index("admin_poll_uid").loc[admin_poll_uid]
        if garde_ser.empty:
            raise ValueError(f"Garde with admin_poll_uid {admin_poll_uid} not found.")
        return self.from_dict(garde_ser.to_dict())  # pyright: ignore[reportArgumentType]

    def _consecutive_events(self, df: pd.DataFrame) -> pd.DataFrame:
        """Set the same publication date to consecutive events."""
        df = df.sort_values(by="start_date")
        for i in range(len(df) - 1):
            row = df.iloc[i]
            next_row = df.iloc[i + 1]
            if row["start_date"].date() == next_row["start_date"].date():
                df.at[df.index[i + 1], "scheduled_publication_date"] = row["scheduled_publication_date"]
        return df

    def test_is_published(self, poll_string: str) -> bool:
        """Test if a poll is already published."""
        garde = self.get_garde_by_pollstring(poll_string)
        if pd.isna(garde.get_published_date()):
            return False
        return True
