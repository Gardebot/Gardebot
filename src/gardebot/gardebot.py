"""Module to create Bot and unify the various requests."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value, singleton-comparison
import logging
import os
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
        if poll_string is None:
            LOGGER.error("No poll_string returned from poll.process_vote.")
            return None
        # we delay the check to let you the time to change your mind
        threading.Timer(180, self.check_poll_completion, args=poll_string).start()
        return None

    def check_poll_completion(self, poll_string: str) -> None:
        """Check if a poll is complete and send on_duty to admin."""
        vote_manager = VoteManager()
        vote_df = vote_manager.load_dataframe("votes")
        poll_df = vote_manager.load_dataframe("polls").set_index("poll_string")
        headcount = int(
            poll_df.loc[poll_string, "headcount"]
        )  # pyright: ignore[reportArgumentType]
        on_duty = vote_df[vote_df[poll_string] == True].index.tolist()
        nb_to_nominate = headcount - len(on_duty)
        if vote_manager.test_poll_completion(poll_string, vote_df):
            message = f"Le poll {poll_string} est complet. Tu peux convoquer les sapeurs: {on_duty}"
            vote_manager.update_on_duty(poll_string, on_duty)
        elif self.test_all_voted(poll_string):
            sapeur_list = vote_df[vote_df[poll_string] == False].index.tolist()

            on_duty_by_force = vote_manager.force_nomination(
                poll_string=poll_string,
                nb_to_nominate=nb_to_nominate,
                sapeur_list_name=sapeur_list,
            )
            on_duty.extend(on_duty_by_force)  # pyright: ignore[reportArgumentType]
            vote_manager.update_on_duty(poll_string, on_duty)
            message = f"Le poll {poll_string} a reçu des réponses de tout le monde mais n'est pas complet. Nomination forcée {on_duty}"
        elif self.test_nb_reminder(poll_string):
            sapeur_list = vote_df[vote_df[poll_string].isna()].index.tolist()
            on_duty_by_force = vote_manager.force_nomination(
                poll_string=poll_string,
                nb_to_nominate=nb_to_nominate,
                sapeur_list_name=sapeur_list,
            )
            on_duty += on_duty_by_force  # pyright: ignore[reportOperatorIssue]
            vote_manager.update_on_duty(poll_string, on_duty)
            message = f"Le poll {poll_string} n'est pas complet après {MAX_NB_REMINDER} Rappel. Nomination forcée {on_duty}"
        else:
            message = f"Le poll {poll_string} n'est pas encore complet. Sapeurs déjà Pré-nommé: {on_duty}"
        self.send_text(
            to_number=os.environ.get("ADMIN_NUMBER", ""), message_text=message
        )
