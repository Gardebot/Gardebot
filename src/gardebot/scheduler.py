"""Scheduler to periodically do stuff."""

import logging

from apscheduler.schedulers.blocking import (  # type: ignore[import-untyped]
    BlockingScheduler,
)

from gardebot.gardebot import Gardebot
from gardebot.services.events import EventService
from gardebot.services.poll_service import PollService

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def sync_events() -> None:
    """Sync calendar events from Infomaniak."""
    LOGGER.info("Starting scheduled calendar sync...")
    event_service = EventService()
    event_service.synchronize_events()
    LOGGER.info("Scheduled calendar sync finished.")


def publish_polls() -> None:
    """Publish polls for upcoming events."""
    LOGGER.info("Starting scheduled poll publication...")
    poll_publisher = PollService()
    poll_publisher.publish_polls()
    LOGGER.info("Scheduled poll publication finished.")


def send_assignments() -> None:
    """Send on-duty assignments for events ready for assignment."""
    LOGGER.info("Starting scheduled on-duty assignments...")
    gardebot = Gardebot()
    gardebot.assign_on_duty_for_events()
    LOGGER.info("Scheduled on-duty assignments finished.")


# def send_polls_reminder() -> None: # TODO: reactivate when needed
#     """Check all polls for reminders."""
#     LOGGER.info("Starting scheduled poll reminders...")
#     gardebot = Gardebot()
#     on_duty_manager = OndutyManager()
#     gardebot.event_service.list_events()
#     gardes_list = gardebot.event_service.list_events()
#     for poll_string in gardes_list:
#         if on_duty_manager.test_assigned(poll_string=poll_string):
#             LOGGER.debug("Le poll %s a déjà été traité.", poll_string)
#             continue
#         gardebot.send_reminder(poll_string=poll_string)
#     LOGGER.info("Scheduled poll reminders finished.")


def warn_holidays() -> None:
    """Warn for upcoming holidays."""
    LOGGER.info("Starting scheduled holiday warning...")
    gardebot = Gardebot()
    gardebot.send_holiday_warning()
    LOGGER.info("Scheduled holiday warning finished.")


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="Europe/Zurich")
    scheduler.add_job(sync_events, "cron", hour=2)
    scheduler.add_job(warn_holidays, "cron", hour=12)
    scheduler.add_job(send_assignments, "cron", hour=12)
    # scheduler.add_job(send_polls_reminder, "cron", hour=10)
    scheduler.add_job(publish_polls, "cron", hour=9)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.error("Cron jobs stopped.")
