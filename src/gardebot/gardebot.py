"""Main Gardebot class coordinating adapters and services."""

from __future__ import annotations

import os
from typing import Any, Dict

import holidays
import pandas as pd  # type: ignore[import-untyped]

from gardebot.adapters.polling import PollingAdapter
from gardebot.common.logging_configuration import get_logger
from gardebot.config import GROUP_ID_GARDE_ET_PIQUET, PREVENTION_DAY_BEFORE_HOLIDAY
from gardebot.integrations.waha_client import WahaClient
from gardebot.metrics import record_initialize, record_vote_processed
from gardebot.services.events import EventService
from gardebot.services.message_service import MessageService
from gardebot.services.onduty import OnDutyService
from gardebot.services.sapeur import SapeurService
from gardebot.services.votes import VoteService
from gardebot.settings import settings

LOGGER = get_logger(__name__)


class Gardebot:
    """Composition root for Gardebot."""

    def __init__(self) -> None:
        """Initialize Gardebot with adapters and services."""
        self.waha_client = WahaClient(
            api_key=settings.api.api_key,
            base_url=settings.api.base_url,
            session=settings.api.session,
            timeout=settings.api.timeout_seconds,
            retries=settings.api.retry_attempts,
        )

        # Adapters (shared)
        self.polling = PollingAdapter(waha_client=self.waha_client)

        # Services (shared)
        self.event_service = EventService()
        self.vote_service = VoteService()
        self.onduty_service = OnDutyService()
        self.sapeur_service = SapeurService()
        self.message_service = MessageService(waha_client=self.waha_client)

    # Inbound message
    def handle_incoming_message(self, data: Dict[str, Any]) -> None:
        """Handle an incoming message event."""
        self.message_service.handle_webhook_payload(data)

    def initialize(self) -> None:
        """Initialize Gardebot by syncing events, sapeurs, votes, and on-duty data."""
        LOGGER.debug("gardebot_initialize_start")
        try:
            self.event_service.synchronize_events()
            self.sapeur_service.synchronize_sapeurs()
            self.vote_service.repo.create(overwrite=False)
            self.onduty_service.repo.create(overwrite=False)
            record_initialize()
            LOGGER.debug("gardebot_initialize_complete")
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("gardebot_initialize_error", error=str(exc))

    def process_vote(self, data: Dict[str, Any]) -> None:
        """Process an incoming vote event."""
        payload = data.get("payload")
        _data = payload.get("_data") if payload else None
        info = _data.get("Info") if _data else None
        chat_id = info.get("Chat") if info else None
        try:
            if chat_id is None:
                LOGGER.info("vote_missing_chat_id")
            elif chat_id == GROUP_ID_GARDE_ET_PIQUET:
                LOGGER.debug("vote_received_group")
                poll_string = self.polling.process_vote_from_group(data)
                if poll_string:
                    record_vote_processed("success")
            elif os.environ.get("ADMIN_NUMBER") in chat_id:
                LOGGER.debug("vote_received_admin")
                self.process_vote_from_admin(data)
                record_vote_processed("success")
            else:
                LOGGER.info("vote_unknown_chat_id", chat_id=chat_id)
        except Exception as exc:  # noqa: BLE001
            record_vote_processed("error")
            LOGGER.error("vote_processing_error_root", error=str(exc))

    def process_vote_from_admin(self, data: Dict[str, Any]) -> None:
        """Process a vote event from the admin chat."""
        # TODO: Implement admin vote logic
        pass

    def _notify_admin(self, message: str) -> None:
        self.message_service.messaging.send_text(to_number=os.environ.get("ADMIN_NUMBER", ""), text=message)

    def send_holiday_warning(self) -> None:
        """Send a warning message for upcoming holidays."""
        today = pd.Timestamp.now(tz="Europe/Zurich")
        geneva_holidays = holidays.country_holidays("CH", subdiv="GE", years=[today.year, today.year + 1])
        upcoming = {d: n for d, n in geneva_holidays.items() if d >= today.date()}
        for date, name in sorted(upcoming.items()):
            timedelta = date - today.date()
            if timedelta.days == PREVENTION_DAY_BEFORE_HOLIDAY:
                message = f"Prochain jour férié: {name} le {date.strftime('%A %d %B %Y')}."
                self._notify_admin(message=message)
