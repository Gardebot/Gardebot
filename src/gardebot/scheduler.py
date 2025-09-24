"""Scheduler to periodically do stuff."""

import logging

from apscheduler.schedulers.blocking import (  # type: ignore[import-untyped]
    BlockingScheduler,
)

from gardebot.datamanager import DataManager
from gardebot.gardebot import Gardebot
from gardebot.infomaniak_calendar import InfomaniakCalendar
from gardebot.poll import PollRequest

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def sync_events() -> None:
    """Sync calendar events from Infomaniak."""
    LOGGER.info("Starting scheduled calendar sync...")
    cal = InfomaniakCalendar()
    cal.sync_calendar_events()
    LOGGER.info("Scheduled calendar sync finished.")


def publish_polls() -> None:
    """Publish polls for upcoming events."""
    LOGGER.info("Starting scheduled poll publication...")
    poll_publisher = PollRequest()
    poll_publisher.publish_poll()
    LOGGER.info("Scheduled poll publication finished.")


def check_polls_completion() -> None:
    """Check all polls for completion."""
    LOGGER.info("Starting scheduled poll completion check...")
    gardebot = Gardebot()
    data_manager = DataManager()
    poll_df = data_manager.load_dataframe("polls").set_index("poll_string")
    for poll_string in poll_df.index:
        poll_id = poll_df.loc[poll_string, "poll_uid"]
        if gardebot.test_has_to_be_reminded(poll_string=poll_string, poll_id=poll_id):
            LOGGER.info("Checking poll %s for completion.", poll_string)
            gardebot.check_poll_completion(poll_string)
    LOGGER.info("Scheduled poll completion check finished.")


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="Europe/Zurich")
    scheduler.add_job(sync_events, "cron", hour=2, minute=0)
    scheduler.add_job(check_polls_completion, "cron", hour=10, minute=0)
    scheduler.add_job(publish_polls, "cron", hour=9, minutes=0)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.error("Cron jobs stopped.")
