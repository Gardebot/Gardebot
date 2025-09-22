"""Module to create Bot and unify the various requests."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging
import threading
from typing import Any, Dict

from gardebot.config import (
    API_CONFIG,
    GROUP_ID_GARDE_ET_PIQUET,
    MAX_NB_REMINDER,
    SERVER_CONFIG,
)
from gardebot.contact import ContactRequest
from gardebot.group import GroupRequest
from gardebot.infomaniak_calendar import InfomaniakCalendar
from gardebot.message import MessageRequest
from gardebot.poll import PollManager, PollRequest
from gardebot.vote import VoteManager

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
        poll_manager = PollManager()
        poll_manager.synch_poll_table()

    def process_vote(self, data: Dict[str, Any]) -> None:
        """Process incoming poll votes from WAHA and check for poll completion."""
        poll_string = super().process_vote(data)
        if not poll_string:
            return
        vote_manager = VoteManager()
        vote_df = vote_manager.load_dataframe("votes")
        if vote_manager._test_poll_completion(poll_string, vote_df):
            on_duty = vote_df[vote_df[poll_string] is True].index.tolist()
            message = f"Le poll {poll_string} est complet. Tu peux convoquer les sapeurs: {on_duty}"
            self.send_text(to_number="41782611429", message_text=message)
        elif self._test_all_voted(poll_string):
            message = f"Le poll {poll_string} a reçu toutes les réponses mais n'est pas complet. Nomination forcée"
            self.send_text(to_number="41782611429", message_text=message)
        elif self._test_nb_reminder(poll_string):
            message = f"Le poll {poll_string} n'est pas complet après {MAX_NB_REMINDER} Rappel. Nomination forcée"
            self.send_text(to_number="41782611429", message_text=message)
