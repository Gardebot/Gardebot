"""Module to create Bot and unify the various requests."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging
import threading

from gardebot.calendar import InfomaniakCalendar
from gardebot.config import API_CONFIG, GROUP_ID_GARDE_ET_PIQUET, SERVER_CONFIG
from gardebot.contact import ContactRequest
from gardebot.group import GroupRequest
from gardebot.message import MessageRequest
from gardebot.poll import PollRequest

LOGGER = logging.getLogger(__name__)


class Gardebot(GroupRequest, MessageRequest, PollRequest, ContactRequest):
    """Main Gardebot class combining group, message, contact and poll functionalities."""

    def __init__(
        self,
        base_url: str = API_CONFIG["base_url"],
        group_id: str = GROUP_ID_GARDE_ET_PIQUET,
    ) -> None:
        """Initialize the Gardebot instance."""
        GroupRequest.__init__(self, base_url=base_url, group_id=group_id)
        MessageRequest.__init__(self, base_url=base_url)
        PollRequest.__init__(self, base_url=base_url)
        ContactRequest.__init__(self, base_url=base_url)

    def initialize(self) -> None:
        """Initialize the bot by syncing group participants and synching the calendar data."""
        LOGGER.debug(
            "Initializing Gardebot. Syncing group participants in %ss.",
            SERVER_CONFIG["postpone_sync_time"],
        )
        threading.Timer(
            SERVER_CONFIG["postpone_sync_time"], self.sync_whatsapp_group_participants
        ).start()  # whatsapp need time to load data
        cal = InfomaniakCalendar()
        cal.sync_calendar_events()
