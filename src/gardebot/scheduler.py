"""Scheduler to periodically do stuff."""

import logging

from apscheduler.schedulers.blocking import (  # type: ignore[import-untyped]
    BlockingScheduler,
)

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


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="Europe/Zurich")
    scheduler.add_job(sync_events, "cron", hour=2, minute=0)
    scheduler.add_job(publish_polls, "interval", minutes=2)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.error("Cron jobs stopped.")
