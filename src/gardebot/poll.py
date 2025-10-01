"""Module to handle poll interaction with WAHA."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
# pyright: ignore[reportAttributeAccessIssue]
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]

from gardebot.config import API_CONFIG, GROUP_ID_GARDE_ET_PIQUET
from gardebot.event import EventManager
from gardebot.on_duty import OndutyManager
from gardebot.request import WahaRequest
from gardebot.sapeur import SapeurManager
from gardebot.vote import Vote, VoteManager

LOGGER = logging.getLogger(__name__)


class PollRequest(WahaRequest):
    """Handles poll interactions with the WAHA API."""

    def __init__(self, base_url: str = API_CONFIG["base_url"]) -> None:
        """Initialize the PollRequest instance."""
        super().__init__(base_url=base_url)

    def process_vote_from_group(self, data: Dict[str, Any]) -> Optional[str]:
        """Process incoming poll votes from WAHA."""
        vote_manager = VoteManager()
        event_manager = EventManager()
        sapeur_manager = SapeurManager()
        on_duty_manager = OndutyManager()

        try:
            payload = data.get("payload")
            if payload is None:
                LOGGER.info("No payload to process with data %s.", data)
                return None
            tmp_voter_id = payload.get("_data").get("Info").get("SenderAlt")
            voter_id = tmp_voter_id.split("@")[0] + "@c.us"
            voter = sapeur_manager.get_sapeur_by_uid(voter_id).get_name()
            poll_string: str = event_manager.get_gardes_by_polluid(
                payload.get("poll").get("id")
            ).get_poll_string()
            if on_duty_manager.test_assigned(poll_string=poll_string):
                LOGGER.debug("Le poll %s a déjà été traité.", poll_string)
                return None
            tmp_vote = payload.get("vote").get("selectedOptions")
            if len(tmp_vote) == 0:
                vote = None
            else:
                vote = tmp_vote[0]
            vote_obj = Vote(poll_string=poll_string, voter_name=voter, vote=vote)
            vote_manager.update_votes(vote_obj)

            LOGGER.info(
                "Processed vote from %s on poll %s: %s",
                voter,
                poll_string,
                vote,
            )
            return poll_string

        except Exception as exc:
            LOGGER.error("Error in process_vote_from_group: %s", exc)
            LOGGER.info("Data received: %s", data)
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
        event_manager = EventManager()
        garde_df = event_manager.load_gardes()
        on_duty_manager = OndutyManager()

        for _, row in garde_df.iterrows():
            garde = event_manager.from_dict(row.to_dict())

            if on_duty_manager.test_assigned(poll_string=garde.get_poll_string()):
                LOGGER.debug("Le poll %s a déjà été traité.", row["poll_string"])
                continue

            if (
                pd.isna(garde.get_published_date())
                and garde.get_scheduled_publication_date().date()
                <= datetime.now().date()
            ):
                response = self.send_poll(
                    to_conv=GROUP_ID_GARDE_ET_PIQUET,
                    poll_title=garde.get_title(),
                    poll_options=["Absent", "Présent"],
                    multiple_answers=False,
                )
                if response is not None and self._is_success(response.status_code):
                    garde.set_attr("poll_uid", response.json().get("id"))
                    garde.set_attr("published_date", pd.Timestamp.now())
                    event_manager.update_gardes(garde)
                    LOGGER.info("Poll published and marked as published in the table.")
                else:
                    LOGGER.error(
                        "Failed to publish poll for event: %s", row["poll_string"]
                    )
