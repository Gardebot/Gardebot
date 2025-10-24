"""Poll service operations."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import pytz  # type: ignore[import-untyped]

from gardebot.adapters.polling import PollingAdapter
from gardebot.common.logging_configuration import get_logger
from gardebot.config import GROUP_ID_GARDE_ET_PIQUET, VOTE_OPTIONS
from gardebot.errors import ExternalServiceError, NotFoundError
from gardebot.services.message_service import MessageService

LOGGER = get_logger(__name__)
TZ = pytz.timezone("Europe/Zurich")


class PollService:
    """Encapsulates poll-related operations with shared services injection."""

    def __init__(self) -> None:
        """Initialize with shared WahaClient."""
        self.polling = PollingAdapter()
        self.message_service = MessageService()

    def handle_webhook_payload(self, data: Dict[str, Any]) -> None:
        """Public entry point to process an inbound poll event."""
        try:
            chat_id = self.polling._extract_chat_id_from_data(data)
            if chat_id == GROUP_ID_GARDE_ET_PIQUET:
                LOGGER.debug("vote_received_group")
                self.polling.process_vote_from_group(data)
                LOGGER.info("vote_processed", chat_id=chat_id)
            elif os.environ.get("ADMIN_NUMBER", "") in chat_id:
                LOGGER.debug("vote_received_admin")
                self.polling.process_vote_from_admin(data)
            else:
                LOGGER.info("vote_unknown_chat_id", chat_id=chat_id)
                self.message_service.send_text(
                    to_number=os.environ.get("ADMIN_NUMBER", ""), text=f"Vote received from unknown chat_id: {chat_id}"
                )
        except NotFoundError as nf:
            LOGGER.error("poll_processing_not_found_error", detail=nf.detail)
        except ExternalServiceError as exc:
            LOGGER.error("poll_processing_error_external", error=str(exc), detail=exc.detail, raw=data)

    def publish_polls(self) -> None:
        """Publish polls for upcoming events."""
        event_list = self.polling.list_events()
        to_be_published = [evt for evt in event_list if self.polling.should_be_published(evt)]
        LOGGER.debug("publishing_polls_start", count=len(to_be_published))
        for evt in to_be_published:
            LOGGER.debug("event_check", poll_string=evt.poll_string)
            try:
                poll_data = self.polling.send_poll(
                    to_conv=GROUP_ID_GARDE_ET_PIQUET,
                    poll_title=evt.poll_string,
                    poll_options=list(VOTE_OPTIONS.keys()),
                    multiple_answers=False,
                )
            except ExternalServiceError as exc:
                LOGGER.error("poll_publish_failed", poll_string=evt.poll_string, error=str(exc))
                continue
            poll_uid: Optional[str] = poll_data.get("id")
            if not poll_uid:
                raise NotFoundError(detail={"resource": "poll.id", "poll_data": poll_data})
            _ = self.polling.mark_published(event=evt, poll_uid=poll_uid)
            LOGGER.info("poll_published", poll_string=evt.poll_string, poll_id=poll_uid)
