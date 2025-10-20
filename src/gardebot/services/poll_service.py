"""Poll service: parsing, command routing, echo behavior."""

from __future__ import annotations

import os
from typing import Any, Dict

import pytz  # type: ignore[import-untyped]

from gardebot.adapters.polling import PollingAdapter
from gardebot.common.logging_configuration import get_logger
from gardebot.config import GROUP_ID_GARDE_ET_PIQUET
from gardebot.errors import ExternalServiceError, NotFoundError
from gardebot.services.message_service import MessageService

LOGGER = get_logger(__name__)
TZ = pytz.timezone("Europe/Zurich")


class PollService:
    """Encapsulates POLL domain logic (parsing, command routing, vote behavior)."""

    def __init__(self, waha_client: Any) -> None:
        """Sender: object providing send_text(to_number: str, message_text: str) and (optionally later) other message-related operations."""
        self.polling = PollingAdapter(waha_client=waha_client)
        self.messaging = MessageService(waha_client=waha_client)

    def handle_webhook_payload(self, data: Dict[str, Any]) -> None:
        """Public entry point to process an inbound poll event."""
        try:
            chat_id = self.polling._extract_from_number(data)
            if chat_id == GROUP_ID_GARDE_ET_PIQUET:
                LOGGER.debug("vote_received_group")
                self.polling.process_vote_from_group(data)
            elif os.environ.get("ADMIN_NUMBER", "") in chat_id:
                LOGGER.debug("vote_received_admin")
                self.polling.process_vote_from_admin(data)
            else:
                LOGGER.info("vote_unknown_chat_id", chat_id=chat_id)
                self.messaging.messaging.send_text(
                    to_number=os.environ.get("ADMIN_NUMBER", ""), text=f"Vote received from unknown chat_id: {chat_id}"
                )
        except NotFoundError as nf:
            LOGGER.error("poll_processing_not_found_error", detail=nf.detail)
        except ExternalServiceError as exc:
            LOGGER.error("poll_processing_error_external", error=str(exc), detail=exc.detail, raw=data)
