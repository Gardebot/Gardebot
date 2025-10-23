"""Message service: parsing, command routing, echo behavior."""

from __future__ import annotations

import os
from typing import Any, Dict

from gardebot.adapters.messaging import MessagingAdapter
from gardebot.common.logging_configuration import get_logger
from gardebot.config import GROUP_ID_GARDE_ET_PIQUET
from gardebot.errors import ExternalServiceError, NotFoundError
from gardebot.models.domain import OnDutyAssignment

LOGGER = get_logger(__name__)


class MessageService:
    """Encapsulates MESSAGE domain logic (parsing, command routing, echo behavior).

    It delegates actual sending to a sender object (Gardebot or a Waha adapter)
    that exposes send_text(to_number: str, message_text: str).
    """

    def __init__(self) -> None:
        """Sender: object providing send_text(to_number: str, message_text: str) and (optionally later) other message-related operations."""
        self.messaging = MessagingAdapter()

    def handle_webhook_payload(self, data: Dict[str, Any]) -> None:
        """Public entry point to process an inbound message event."""
        payload = data.get("payload")
        if not payload:
            raise NotFoundError(detail={"resource": "payload", "data": data})

        try:
            body: str = payload.get("body", "")
            from_number: str = payload.get("from")
            timestamp = payload.get("timestamp")
            LOGGER.info("message_received", sender=from_number, text=body[:60])
            self._echo(body, from_number, timestamp)
        except ExternalServiceError as exc:
            LOGGER.error("message_processing_error_external", error=str(exc), detail=exc.detail, raw=data)

    def _echo(self, body: str, from_number: str, timestamp: Any) -> None:
        """Echo the received message back to the sender."""
        if os.environ.get("BOT_NUMBER", "") in from_number:
            LOGGER.debug("message_echo_skipped_bot", sender=from_number)
            return
        if GROUP_ID_GARDE_ET_PIQUET in from_number:
            LOGGER.debug("message_echo_skipped_group_chat", sender=from_number)
            return
        self.messaging.send_text(
            to_number=from_number,
            text=f"Echoing, you sent : '{body}' at {timestamp}",
        )
        LOGGER.debug("message_echo_sent", sender=from_number, body=body)

    def send_convocation(self, assignment: OnDutyAssignment) -> Dict[str, Any]:
        """Send convocation messages (group and private) to on-duty sapeurs."""
        if not assignment.event.poll_uid:
            raise NotFoundError("Missing poll ID for convocation", detail={"poll_string": assignment.event.poll_string})
        results: Dict[str, Any] = {"group": None, "private": []}
        results["group"] = self.messaging.send_group_convocation(to_number=GROUP_ID_GARDE_ET_PIQUET, assignment=assignment)
        for sap in assignment.sapeur_list:
            try:
                res = self.messaging.send_private_convocation(to_number=sap.uid, event=assignment.event)
                results["private"].append({"to": sap.uid, "result": res})
            except ExternalServiceError as exc:
                LOGGER.error(
                    "private_convocation_failed",
                    to=sap.uid,
                    poll_string=assignment.event.poll_string,
                    error=str(exc),
                )
                results["private"].append({"to": sap.uid, "error": str(exc)})
        LOGGER.info("convocation_complete", poll_string=assignment.event.poll_string, on_duty=[s.name for s in assignment.sapeur_list])
        return results

    def send_text(self, to_number: str, text: str) -> Dict[str, Any]:
        """Wrapper around send_text from MessagingAdapter."""
        return self.messaging.send_text(to_number=to_number, text=text)

    def send_vote_reminder(self, event: Any) -> Dict[str, Any]:
        """Wrapper around send_vote_reminder from MessagingAdapter."""
        return self.messaging.send_vote_reminder(event=event)
