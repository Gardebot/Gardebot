"""Module to create Bot and unify the various requests."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value, singleton-comparison
import logging
import os
import threading
from typing import Any, Dict, List, Optional

import holidays
import pandas as pd  # type: ignore[import-untyped]

from gardebot.config import (
    API_CONFIG,
    GROUP_ID_GARDE_ET_PIQUET,
    MAX_NB_REMINDER,
    MINIMUM_ELAPSED_HOURS,
    PREVENTION_DAY_BEFORE_HOLIDAY,
)
from gardebot.contact import ContactRequest
from gardebot.event import EventManager
from gardebot.group import GroupRequest
from gardebot.message import MessageRequest
from gardebot.on_duty import OndutyManager
from gardebot.poll import PollRequest
from gardebot.sapeur import SapeurManager
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
        self.update_gardes()
        self.update_sapeurs()
        self.initialize_vote_table()
        self.initilize_onduty_table()

    def initialize_vote_table(self) -> None:
        """Initialize the vote table if it does not exist."""
        vote_manager = VoteManager()
        _ = vote_manager.load_votes()

    def initilize_onduty_table(self) -> None:
        """Initialize the on_duty table if it does not exist."""
        onduty_manager = OndutyManager()
        _ = onduty_manager.load_onduty()

    def update_sapeurs(self) -> None:
        """Update the sapeur list by syncing WhatsApp group participants."""
        sapeur_manager = SapeurManager()
        sapeur_manager.update_sapeurs()

    def update_gardes(self) -> None:
        """Update the events list by syncing the calendar."""
        event_manager = EventManager()
        event_manager.synch_gardes()

    def process_vote(self, data: Dict[str, Any]) -> None:
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
                self.process_vote_from_group(data)
            elif os.environ.get("ADMIN_NUMBER") in chat_id:
                LOGGER.debug("Vote received from admin, processing.")
                self.process_vote_from_admin(data)
            else:
                LOGGER.info("Vote received from unknown chat_id %s, ignoring.", chat_id)
        except Exception as exc:
            LOGGER.error("Error in process_vote: %s", exc)

    def process_vote_from_admin(self, data: Dict[str, Any]) -> None:
        """Process poll votes from admin."""
        payload = data.get("payload")
        if payload is None:
            LOGGER.info("No payload to process with data %s.", data)
            return None
        admin_poll_id = (
            payload.get("poll", {}).get("id") if payload.get("poll") else None
        )
        garde = EventManager().get_gardes_by_admin_poll_uid(admin_poll_id)
        on_duty_manager = OndutyManager()
        poll_string = garde.get_poll_string()
        if on_duty_manager.test_assigned(poll_string=poll_string):
            LOGGER.debug("Le poll %s a déjà été traité.", poll_string)
            return None
        vote = payload.get("vote") if payload else None
        tmp_on_duty_list: Optional[List[str]] = (
            vote.get("selectedOptions") if vote else None
        )
        on_duty_list: Optional[List[str]] = (
            [name.split(" : ")[0] for name in tmp_on_duty_list]
            if tmp_on_duty_list
            else None
        )
        if on_duty_list is None:
            LOGGER.error("No on_duty_list found in admin vote payload %s", payload)
            return None
        if len(on_duty_list) != garde.get_headcount():
            LOGGER.error(
                "Admin selected %s sapeurs but headcount is %s for poll %s. Ignoring.",
                len(on_duty_list),
                garde.get_headcount(),
                poll_string,
            )
            return None
        if len(on_duty_list) == 0:
            LOGGER.error("Admin selected no sapeur for poll %s. Ignoring.", poll_string)
            return None

        on_duty_manager.update_on_duty(
            poll_string=poll_string, on_duty_name=on_duty_list
        )
        self.send_convocation(poll_string=poll_string, on_duty_name=on_duty_list)
        LOGGER.info(
            "Admin confirmed on-duty for poll %s: %s", poll_string, on_duty_list
        )
        return None

    def process_vote_from_group(self, data: Dict[str, Any]) -> None:
        """Process incoming poll votes from WAHA and check for poll completion."""
        poll_string = super().process_vote_from_group(data)
        if poll_string is None:
            LOGGER.error("No poll_string returned from poll.process_vote.")
            return None
        # we delay the check to let you the time to change your mind
        threading.Timer(180, self.check_poll_status, args=(poll_string,)).start()
        return None

    def check_poll_status(self, poll_string: str) -> bool:
        """Check if a poll is complete and proceed accordingly."""
        vote_manager = VoteManager()
        on_duty_manager = OndutyManager()

        if on_duty_manager.test_assigned(poll_string=poll_string):
            LOGGER.info("Le poll %s a déjà été traité.", poll_string)
            return True
        if vote_manager.test_garde_completion(poll_string=poll_string):
            LOGGER.info("Le poll %s est complet.", poll_string)
            self._process_poll_complete(poll_string)
            return True
        if vote_manager.test_all_voted(poll_string=poll_string):
            LOGGER.info(
                "Le poll %s a reçu des réponses de tout le monde mais n'est pas complet.",
                poll_string,
            )
            self._process_all_voted_case(poll_string=poll_string)
            return True
        return False

    def _process_poll_complete(self, poll_string: str) -> None:
        """Process actions to take when a poll is complete."""
        vote_manager = VoteManager()
        event_manager = EventManager()
        on_duty = dict.fromkeys(
            vote_manager.get_present_list(poll_string=poll_string), 1.0
        )
        if vote_manager.test_garde_completion(poll_string=poll_string):
            message = f"Le poll {poll_string} est complet avec {len(on_duty)} sapeurs: {on_duty}"
            LOGGER.info(message)
            self._ask_confirmation_to_admin(
                headcount=event_manager.get_garde_by_pollstring(
                    poll_string
                ).get_headcount(),
                poll_string=poll_string,
                potential_on_duty=on_duty,
            )

    def _process_all_voted_case(self, poll_string: str) -> None:
        """Handle the case where all have voted but the poll is not complete."""
        vote_manager = VoteManager()
        event_manager = EventManager()
        on_duty_manager = OndutyManager()

        garde = event_manager.get_garde_by_pollstring(poll_string)
        tmp_on_duty = dict.fromkeys(
            vote_manager.get_present_list(poll_string=poll_string), 1.0
        )
        nb_to_nominate = garde.get_headcount() - len(tmp_on_duty)

        forced_on_duty = on_duty_manager.force_nomination(
            nb_to_nominate=nb_to_nominate,
            poll_string=poll_string,
        )
        tmp_on_duty.update(forced_on_duty)
        self._ask_confirmation_to_admin(
            headcount=garde.get_headcount(),
            poll_string=poll_string,
            potential_on_duty=tmp_on_duty,
        )

    def _process_max_reminder_case(self, poll_string: str) -> None:
        """Handle the case where the maximum number of reminders has been reached."""
        vote_manager = VoteManager()
        event_manager = EventManager()
        on_duty_manager = OndutyManager()

        garde = event_manager.get_garde_by_pollstring(poll_string)
        tmp_on_duty = dict.fromkeys(
            vote_manager.get_present_list(poll_string=poll_string), 1.0
        )
        nb_to_nominate = garde.get_headcount() - len(tmp_on_duty)
        forced_on_duty = on_duty_manager.force_nomination(
            nb_to_nominate=nb_to_nominate,
            poll_string=poll_string,
        )
        tmp_on_duty.update(forced_on_duty)

        self._ask_confirmation_to_admin(
            headcount=garde.get_headcount(),
            poll_string=poll_string,
            potential_on_duty=tmp_on_duty,
        )

    def _ask_confirmation_to_admin(
        self, headcount: int, poll_string: str, potential_on_duty: Dict[str, float]
    ) -> None:
        """Ask the admin to confirm the on-duty nominations."""
        event_manager = EventManager()
        garde = event_manager.get_garde_by_pollstring(poll_string)
        poll_options = [
            f"{name} : {score:.2f}" for name, score in potential_on_duty.items()
        ]
        LOGGER.info("Poll options for admin confirmation: %s", poll_options)
        if len(poll_options) < 2:
            LOGGER.error("Not enough options to ask for confirmation to admin.")
            return None
        response = self.send_poll(
            to_conv=os.environ.get("ADMIN_NUMBER", ""),
            poll_title=f"Choose {headcount} | {poll_string}",
            poll_options=poll_options,
            multiple_answers=True,
        )
        if response is None:
            LOGGER.error("Failed to send poll to admin for confirmation.")
            return None
        if self._is_success(response.status_code):
            garde.set_attr("admin_poll_uid", response.json().get("id"))
            event_manager.update_gardes(garde)
            LOGGER.info(
                "Asked admin for confirmation on poll %s: %s", poll_string, poll_options
            )
        else:
            LOGGER.error(
                "Failed to send poll to admin (%s): %s",
                response.status_code,
                response.text,
            )
        return None

    def _notify_admin(self, message: str) -> None:
        self.send_text(
            to_number=os.environ.get("ADMIN_NUMBER", ""), message_text=message
        )

    def send_holiday_warning(self) -> None:
        """Send a warning message for upcoming holidays."""
        today = pd.Timestamp.now(tz="Europe/Zurich")
        geneva_holidays = holidays.country_holidays(
            "CH", subdiv="GE", years=[today.year, today.year + 1]
        )
        upcoming_holidays = {
            date: name for date, name in geneva_holidays.items() if date >= today.date()
        }
        for date, name in sorted(upcoming_holidays.items()):
            timedelta = date - today.date()
            if timedelta.days == PREVENTION_DAY_BEFORE_HOLIDAY:
                message = f"Prochain jour férié: {name} le {date.strftime('%A %d %B %Y')}. Tu dois peut-être prévoir des piquets!"
                self._notify_admin(message=message)

    def send_reminder(self, poll_string: str) -> None:
        """Send a reminder for a given poll."""
        event_manager = EventManager()
        garde = event_manager.get_garde_by_pollstring(poll_string)
        if pd.isna(garde.get_published_date()):
            LOGGER.info("Le poll %s n'a pas encore été publié.", poll_string)
        elif not garde.test_elapse_time():
            LOGGER.info(
                "Le poll %s a été rappelé il y a moins de %s heures.",
                poll_string,
                MINIMUM_ELAPSED_HOURS,
            )
        elif garde.test_max_reminder():
            LOGGER.info(
                "Le poll %s a atteint le nombre maximum de rappels (%s).",
                poll_string,
                MAX_NB_REMINDER,
            )
            self._process_max_reminder_case(poll_string=poll_string)
        else:
            self.send_vote_reminder(poll_string=poll_string)
            garde.increment_nb_reminder()
            event_manager.update_gardes(garde)
