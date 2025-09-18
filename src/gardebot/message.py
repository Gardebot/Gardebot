"""Module to handle incoming messages to/from WAHA."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging
from typing import Any, Dict

from gardebot.request import WahaRequest

LOGGER = logging.getLogger(__name__)


class MessageRequest(WahaRequest):
    """Handles message interactions with the WAHA API."""

    def __init__(self) -> None:
        """Initialize the MessageRequest instance."""
        super().__init__()

    def process_messages(self, data: Dict[str, Any]) -> None:
        """Process incoming messages from WAHA."""
        try:
            payload = data.get("payload")
            if payload is None:
                LOGGER.info("No payload to process with data %s.", data)
                return
            if not payload.get("fromMe"):
                body = payload.get("body")
                timestamp = payload.get("timestamp")
                from_number = payload.get("from")

                self.send_text(
                    to_number=from_number,
                    message_text=f"Echoing, you sent : '{body}' at {timestamp}",
                )
                LOGGER.info(
                    "Processed message from %s at %s: %s", from_number, timestamp, body
                )
            else:
                LOGGER.debug("Ignoring message sent from myself with data %s.", data)
        except Exception as exc:
            LOGGER.exception("Error in process_messages: %s", exc)

    def send_text(self, to_number: str, message_text: str) -> None:
        """Send a reply using WAHA."""
        try:
            payload = {
                "session": self.session,
                "chatId": to_number,
                "text": message_text,
            }
            response = self.send_post_request(endpoint="/api/sendText", payload=payload)
            if self._is_success(response.status_code):
                LOGGER.info("Message sent successfully to %s", to_number)
            else:
                LOGGER.error(
                    "Failed to send message (%s): %s",
                    response.status_code,
                    response.text,
                )
        except Exception as exc:
            LOGGER.exception("Error sending message: %s", exc)
