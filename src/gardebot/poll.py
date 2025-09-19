"""Module to handle poll interaction with WAHA."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging
from typing import Any, Dict, List

from gardebot.config import API_CONFIG
from gardebot.request import WahaRequest

LOGGER = logging.getLogger(__name__)


class PollRequest(WahaRequest):
    """Handles poll interactions with the WAHA API."""

    def __init__(self, base_url: str = API_CONFIG["base_url"]) -> None:
        """Initialize the PollRequest instance."""
        super().__init__(base_url=base_url)

    def process_vote(self, data: Dict[str, Any]) -> None:
        """Process incoming poll votes from WAHA."""
        try:
            payload = data.get("payload")
            if payload is None:
                LOGGER.info("No payload to process with data %s.", data)
                return
            voter = payload.get("voter")
            poll_id = payload.get("pollId")
            selected_options = payload.get("selectedOptions", [])
            LOGGER.info(
                "Processed vote from %s on poll %s: %s",
                voter,
                poll_id,
                selected_options,
            )
        except Exception as exc:
            LOGGER.exception("Error in process_vote: %s", exc)

    def send_poll(
        self,
        to_conv: str,
        poll_title: str,
        poll_options: List[str],
        multiple_answers: bool = False,
    ) -> None:
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
            else:
                LOGGER.error(
                    "Failed to send poll (%s): %s", response.status_code, response.text
                )
        except Exception as exc:
            LOGGER.exception("Error sending poll: %s", exc)
