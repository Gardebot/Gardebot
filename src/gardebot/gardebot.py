"""Module to create Bot and unify the various requests."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import holidays
import pandas as pd  # type: ignore[import-untyped]

from gardebot.adapters.contacts import ContactAdapter
from gardebot.adapters.groups import GroupAdapter
from gardebot.adapters.messaging import MessagingAdapter
from gardebot.adapters.polling import PollingAdapter
from gardebot.config import (
    GROUP_ID_GARDE_ET_PIQUET,
    PREVENTION_DAY_BEFORE_HOLIDAY,
)
from gardebot.integrations.waha_client import WahaClient
from gardebot.services.events import EventService
from gardebot.services.message_service import MessageService
from gardebot.services.onduty import OnDutyService
from gardebot.services.sapeur import SapeurService
from gardebot.services.votes import VoteService
from gardebot.settings import settings

LOGGER = logging.getLogger(__name__)


class Gardebot:
    """Main Gardebot class combining group, message, contact and poll functionalities."""

    def __init__(
        self,
        group_id: str = GROUP_ID_GARDE_ET_PIQUET,
    ) -> None:
        """Initialize the Gardebot instance."""
        self.waha_client = WahaClient(
            api_key=settings.api.api_key,
            base_url=settings.api.base_url,
            session=settings.api.session,
            timeout=settings.api.timeout_seconds,
            retries=settings.api.retry_attempts,
        )

        # Composition adapters
        self.messaging = MessagingAdapter(waha_client=self.waha_client)
        self.polling = PollingAdapter(waha_client=self.waha_client)
        self.groups = GroupAdapter(group_id=group_id, waha_client=self.waha_client)
        self.contact = ContactAdapter(waha_client=self.waha_client)

        # Inbound service
        self.message_service = MessageService(sender=self)
        self.event_service = EventService()
        self.vote_service = VoteService()
        self.onduty_service = OnDutyService()
        self.sapeur_service = SapeurService()

    # ------------------------------------------------------------------ #
    # Wrapper methods (backward compatibility during refactor)
    # ------------------------------------------------------------------ #

    def process_vote_from_group(self, data: Dict[str, Any]) -> Optional[str]:  # TODO : Duplicate + has to be debouneced
        """Process poll votes from group."""
        return self.polling.process_vote_from_group(data)

    # ------------------------------------------------------------------ #
    # Inbound Message Handling
    # ------------------------------------------------------------------ #
    def handle_incoming_message(self, data: Dict[str, Any]) -> None:  # OK
        """Delegate inbound message event to the MessageService."""
        self.message_service.handle_webhook_payload(data)

    def initialize(self) -> None:  # OK
        """Initialize the bot by syncing group participants and synching the calendar data."""
        LOGGER.debug("============== Initializing Gardebot... ==============")
        self.event_service.synchronize_events()
        self.sapeur_service.synchronize_sapeurs()
        self.vote_service.repo.create(overwrite=False)
        self.onduty_service.repo.create(overwrite=False)
        LOGGER.debug("============== Gardebot initialized. ==============")

    def update_sapeurs(self) -> None:  # OK
        """Update the sapeur list by syncing WhatsApp group participants."""
        self.sapeur_service.synchronize_sapeurs()

    def process_vote(self, data: Dict[str, Any]) -> None:  # OK
        """Process incoming poll votes from WAHA and decide the process."""
        payload = data.get("payload")
        _data = payload.get("_data") if payload else None
        info = _data.get("Info") if _data else None
        chat_id = info.get("Chat") if info else None
        try:
            if chat_id is None:
                LOGGER.info("No chat_id to process with data %s.", data)
            elif chat_id == GROUP_ID_GARDE_ET_PIQUET:
                LOGGER.debug("Vote received from group, processing.")
                self.polling.process_vote_from_group(data)
            elif os.environ.get("ADMIN_NUMBER") in chat_id:
                LOGGER.debug("Vote received from admin, processing.")
                self.process_vote_from_admin(data)
            else:
                LOGGER.info("Vote received from unknown chat_id %s, ignoring.", chat_id)
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Error in process_vote: %s", exc)

    def process_vote_from_admin(self, data: Dict[str, Any]) -> None:
        """Process poll votes from admin."""
        pass  # TODO implement

    def _notify_admin(self, message: str) -> None:
        self.messaging.send_text(to_number=os.environ.get("ADMIN_NUMBER", ""), message_text=message)

    def send_holiday_warning(self) -> None:
        """Send a warning message for upcoming holidays."""
        today = pd.Timestamp.now(tz="Europe/Zurich")
        geneva_holidays = holidays.country_holidays("CH", subdiv="GE", years=[today.year, today.year + 1])
        upcoming_holidays = {date: name for date, name in geneva_holidays.items() if date >= today.date()}
        for date, name in sorted(upcoming_holidays.items()):
            timedelta = date - today.date()
            if timedelta.days == PREVENTION_DAY_BEFORE_HOLIDAY:
                message = f"Prochain jour férié: {name} le {date.strftime('%A %d %B %Y')}. Tu dois peut-être prévoir des piquets!"
                self._notify_admin(message=message)

    # def send_reminder(self, poll_string: str) -> None:
    #     """Send a reminder for a given poll."""
    #     return None  # TODO implement
