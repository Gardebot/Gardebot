"""Module to handle poll interaction with WAHA."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
# pyright: ignore[reportAttributeAccessIssue]
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]

from gardebot.config import (
    API_CONFIG,
    GROUP_ID_GARDE_ET_PIQUET,
    MONTHS_FR,
    TIME_BEFORE_PUBLICATION_DAY,
    WEEKDAYS_FR,
)
from gardebot.datamanager import DataManager
from gardebot.infomaniak_calendar import InfomaniakCalendar
from gardebot.request import WahaRequest
from gardebot.vote import VoteManager

LOGGER = logging.getLogger(__name__)


class PollRequest(WahaRequest):
    """Handles poll interactions with the WAHA API."""

    def __init__(self, base_url: str = API_CONFIG["base_url"]) -> None:
        """Initialize the PollRequest instance."""
        super().__init__(base_url=base_url)

    def process_vote(self, data: Dict[str, Any]) -> Optional[str]:
        """Process incoming poll votes from WAHA."""
        vote_manager = VoteManager()
        poll_df = vote_manager.load_dataframe("polls").set_index("poll_uid")
        sapeur_df = vote_manager.load_dataframe("sapeurs").set_index("id")

        try:
            payload = data.get("payload")
            if payload is None:
                LOGGER.info("No payload to process with data %s.", data)
                return None
            voter_id = payload.get("poll").get("to")
            voter = str(sapeur_df.loc[voter_id, "name"])
            poll_id = payload.get("poll").get("id")
            poll_string = str(poll_df.loc[poll_id, "poll_string"])
            selected_options = payload.get("vote").get("selectedOptions")
            if len(selected_options) > 0:
                vote_manager.update_votes(poll_string, voter, selected_options)
            else:
                vote_manager.update_votes(poll_string, voter, None)

            LOGGER.debug(
                "Processed vote from %s on poll %s: %s",
                voter,
                poll_id,
                selected_options,
            )
            return poll_string

        except Exception as exc:
            LOGGER.error("Error in process_vote: %s", exc)
            return None

    def send_poll(
        self,
        to_conv: str,
        poll_title: str,
        poll_options: List[str],
        multiple_answers: bool = False,
    ) -> Optional[requests.Response]:
        """Send a poll using WAHA."""
        try:
            payload = {
                "chatId": to_conv,
                "poll": {
                    "name": poll_title,
                    "options": poll_options,
                    "multipleAnswers": multiple_answers,
                },
                "session": self.session,
            }
            response = self.send_post_request(endpoint="/api/sendPoll", payload=payload)
            if self._is_success(response.status_code):
                LOGGER.info("Poll sent successfully to %s", to_conv)
                return response
            return None
        except Exception as exc:
            LOGGER.exception("Error sending poll: %s", exc)
            return None

    def publish_poll(self) -> None:
        """Publish polls based on poll table."""
        poll_manager = PollManager()
        poll_df = poll_manager.load_dataframe("polls")

        for index, row in poll_df.iterrows():
            if (
                not row["is_published"]
                and row["published_date"].date() <= datetime.now().date()
            ):
                response = self.send_poll(
                    to_conv=GROUP_ID_GARDE_ET_PIQUET,
                    poll_title=row["poll_string"],
                    poll_options=["Absent", "Présent"],
                    multiple_answers=False,
                )
                if response is not None and self._is_success(response.status_code):
                    poll_df.at[index, "poll_uid"] = response.json().get("id")
                    poll_df.loc[index, "is_published"] = True
                    poll_manager.save_dataframe(poll_df, "polls")
                    LOGGER.info("Poll published and marked as published in the table.")
                else:
                    LOGGER.error(
                        "Failed to publish poll for event: %s", row["poll_string"]
                    )


class PollManager(DataManager):
    """Manages poll data."""

    def _format_french_date(self, date: datetime) -> str:
        """Format a given datetime object into a French-style date string."""
        weekday = WEEKDAYS_FR[date.weekday()]
        month = MONTHS_FR[date.month]
        return f"{weekday} {date.day} {month} {date.year}"

    def _create_pollstring(
        self, name: str, date_start: datetime, date_end: datetime, location: str
    ) -> str:
        """Create a formatted string representing the event's date, time, location, and name."""
        date_start_str = self._format_french_date(date_start)
        time_start = f"{date_start.hour}h{date_start.minute:02d}"

        if date_end is None:
            time_part = f"dès {time_start}"
        elif date_start.date() == date_end.date():
            time_end = f"{date_end.hour}h{date_end.minute:02d}"
            time_part = f"de {time_start} à {time_end}"
        else:
            date_end_str = self._format_french_date(date_end)
            time_end = f"{date_end.hour}h{date_end.minute:02d}"
            time_part = f"{time_start} au {date_end_str} {time_end}"

        result = f"{name} : {date_start_str} {time_part}, {location}"
        return result[0].upper() + result[1:]

    def _consecutive_events(self, df: pd.DataFrame) -> pd.DataFrame:
        """Set the same publication date to consecutive events."""
        df = df.sort_values(by="date_start")
        for i in range(len(df) - 1):
            row = df.iloc[i]
            next_row = df.iloc[i + 1]
            if row["date_start"].date() == next_row["date_start"].date():
                df.at[df.index[i + 1], "published_date"] = row["published_date"]
        return df

    def _create_poll_table(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create a poll table from the calendar data."""
        poll_df = df.copy()
        poll_df["poll_string"] = poll_df.apply(
            lambda row: self._create_pollstring(
                row["name"], row["date_start"], row["date_end"], row["location"]
            ),
            axis=1,
        )
        poll_df["published_date"] = poll_df["date_start"] - pd.Timedelta(
            days=TIME_BEFORE_PUBLICATION_DAY
        )
        poll_df = self._consecutive_events(poll_df)
        poll_df.sort_values(by="date_start", inplace=True)
        poll_df["nb_reminder"] = 0
        poll_df["is_published"] = False
        poll_df["poll_uid"] = None
        poll_df.drop(
            columns=["name", "location", "date_start", "date_end"], inplace=True
        )
        return poll_df

    def synch_poll_table(self) -> None:
        """Sync the poll table based on new events."""
        calendar = InfomaniakCalendar()

        calendar_df = calendar.load_dataframe("calendar")
        poll_df = self.load_dataframe("polls")
        if poll_df.empty:
            LOGGER.info("No existing poll data. Creating new poll table.")
            poll_df = self._create_poll_table(calendar_df)
            self.save_dataframe(poll_df, "polls")
            return None

        new_poll_df = calendar_df[~poll_df["uid"].isin(calendar_df["uid"])]
        if new_poll_df.empty:
            LOGGER.info("No new events for poll creation.")
            return None
        new_poll_df = self._create_poll_table(new_poll_df)
        updated_poll_df = pd.concat([poll_df, new_poll_df], ignore_index=True)
        LOGGER.info(
            "New event(s) found for poll creation: %s",
            new_poll_df[["poll_string", "published_date"]].to_dict(orient="records"),
        )
        self.save_dataframe(updated_poll_df, "polls")
        return None
