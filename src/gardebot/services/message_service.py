"""Message service: parsing, command routing, echo behavior."""

from __future__ import annotations

from typing import Any, Dict

from gardebot.adapters.messaging import MessagingAdapter
from gardebot.common.logging_configuration import get_logger
from gardebot.errors import ExternalServiceError, NotFoundError

LOGGER = get_logger(__name__)


class MessageService:
    """Encapsulates MESSAGE domain logic (parsing, command routing, echo behavior).

    It delegates actual sending to a sender object (Gardebot or a Waha adapter)
    that exposes send_text(to_number: str, message_text: str).
    """

    def __init__(self, waha_client: Any) -> None:
        """Sender: object providing send_text(to_number: str, message_text: str) and (optionally later) other message-related operations."""
        self.messaging = MessagingAdapter(waha_client=waha_client)

    def handle_webhook_payload(self, data: Dict[str, Any]) -> None:
        """Public entry point to process an inbound message event."""
        payload = data.get("payload")
        if not payload:
            raise NotFoundError(detail={"resource": "payload", "data": data})

        try:
            body: str = payload.get("body", "")
            from_number: str = payload.get("from")
            timestamp = payload.get("timestamp")
            LOGGER.info("message_received", sender=from_number, body_excerpt=body[:60])
            self._echo(body, from_number, timestamp)
        except ExternalServiceError as exc:
            LOGGER.error("message_processing_error_external", error=str(exc), detail=exc.detail, raw=data)

    def _echo(self, body: str, from_number: str, timestamp: Any) -> None:
        """Echo the received message back to the sender."""
        self.messaging.send_text(
            to_number=from_number,
            text=f"Echoing, you sent : '{body}' at {timestamp}",
        )
        LOGGER.debug("message_echo_sent", sender=from_number, body=body)
