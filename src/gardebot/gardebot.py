"""Main Gardebot class coordinating adapters and services."""

from __future__ import annotations

import os
from typing import Any, Dict

import holidays
import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.config import PREVENTION_DAY_BEFORE_HOLIDAY
from gardebot.services.events import EventService
from gardebot.services.message_service import MessageService
from gardebot.services.onduty import OnDutyService
from gardebot.services.poll_service import PollService
from gardebot.services.sapeur import SapeurService
from gardebot.services.votes import VoteService

LOGGER = get_logger(__name__)


class Gardebot:
    """Composition root for Gardebot."""

    def __init__(self) -> None:
        """Initialize Gardebot with adapters and services."""
        self.event_service = EventService()
        self.vote_service = VoteService()
        self.onduty_service = OnDutyService()
        self.sapeur_service = SapeurService()
        self.message_service = MessageService()
        self.poll_service = PollService()

    def handle_incoming_message(self, data: Dict[str, Any]) -> None:
        """Handle an incoming message event."""
        self.message_service.handle_webhook_payload(data)

    def handle_incoming_vote(self, data: Dict[str, Any]) -> None:
        """Handle an incoming vote event."""
        self.poll_service.handle_webhook_payload(data)

    def assign_on_duty_for_events(self) -> None:
        """Assign on-duty personnel for events ready for assignment."""
        event_list = self.event_service.list_events()
        for event in event_list:
            try:
                if self.vote_service.test_event_completion(event):
                    if not self.onduty_service.is_assigned(event):
                        assignment = self.onduty_service.process_assignment(event)
                        self.message_service.send_convocation(assignment=assignment)
                        LOGGER.info(
                            "onduty_assignment_completed",
                            poll_string=event.poll_string,
                            assigned_sapeurs=[s.name for s in assignment.sapeur_list],
                        )
            except Exception as exc:  # noqa: BLE001
                LOGGER.error(
                    "onduty_assignment_error",
                    poll_string=event.poll_string,
                    error=str(exc),
                )

    def initialize(self) -> None:
        """Initialize Gardebot by syncing events, sapeurs, votes, and on-duty data."""
        LOGGER.debug("gardebot_initialize_start")
        try:
            self.event_service.synchronize_events()
            self.sapeur_service.synchronize_sapeurs()
            self.vote_service.create(overwrite=False)
            self.onduty_service.create(overwrite=False)
            LOGGER.debug("gardebot_initialize_complete")
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("gardebot_initialize_error", error=str(exc))

    def _notify_admin(self, message: str) -> None:
        self.message_service.send_text(to_number=os.environ.get("ADMIN_NUMBER", ""), text=message)

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

    def reminders(self) -> None:
        """Send reminders for all polls that need it."""
        event_list = self.event_service.list_events()
        for event in event_list:
            if event.should_send_reminder() and not self.onduty_service.is_assigned(event):
                try:
                    self.message_service.send_vote_reminder(event=event)
                    update_evt = self.event_service.increment_reminder(event)
                    LOGGER.info(
                        "poll_reminder_sent",
                        poll_string=update_evt.poll_string,
                        nb_reminder=update_evt.nb_reminder,
                    )
                except Exception as exc:  # noqa: BLE001
                    LOGGER.error(
                        "poll_reminder_error",
                        poll_string=event.poll_string,
                        error=str(exc),
                    )
