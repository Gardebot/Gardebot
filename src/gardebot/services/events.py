"""High-level event logic (fetch, enrich, publish, reminders)."""

from __future__ import annotations

from typing import List, Optional

from gardebot.common.logging_configuration import get_logger
from gardebot.integrations.infomaniak import InfomaniakCalendar
from gardebot.models.domain import Event
from gardebot.repositories import EventRepository

LOGGER = get_logger(__name__)


class EventService:
    """High-level event logic (fetch, enrich, publish, reminders)."""

    def __init__(self, repository: Optional[EventRepository] = None) -> None:
        """Initialize with optional custom repository."""
        self.repo = repository or EventRepository()

    def synchronize_events(self) -> None:
        """Synchronize events from external calendar."""
        _ = self.insert_external_calendar()

    def insert_external_calendar(self) -> List[Event]:
        """Fetch events from external calendar and upsert into repository (idempotent)."""
        calendar_df = InfomaniakCalendar().fetch_calendar()
        events: List[Event] = []
        for _, row in calendar_df.iterrows():
            evt = Event(
                title=row["name"],
                location=row["location"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                headcount=row["headcount"],
            )
            events.append(evt)
        events = self._propagate_publication_dates(events)
        self.repo.bulk_upsert(events)
        return events

    def _propagate_publication_dates(self, events: List[Event]) -> List[Event]:
        """Ensure events on same start date share publication schedule like legacy behavior."""
        events.sort(key=lambda e: e.start_date)
        for i in range(len(events) - 1):
            if events[i].end_date.date() == events[i + 1].start_date.date():
                events[i + 1].scheduled_publication_date = events[i].scheduled_publication_date

        return events

    def list_events(self) -> List[Event]:
        """Return all events."""
        return self.repo.list_events()

    def assign_poll_published_date(self, event: Event) -> Event:
        """Set published date for event."""
        updated = event.set_published_date()
        self.repo.upsert_event(updated)
        return updated

    def increment_reminder(self, event: Event) -> Event:
        """Increment reminder count for event."""
        updated = event.increment_reminder()
        self.repo.upsert_event(updated)
        return updated

    def assign_poll_uid(self, event: Event, poll_uid: str) -> Event:
        """Assign poll_uid to event."""
        updated = event.with_poll_uid(poll_uid)
        self.repo.upsert_event(updated)
        return updated

    def find_by_poll_uid(self, poll_id: str) -> Event:
        """Wrapper around find_by_poll_uid from repository."""
        return self.repo.find_by_poll_uid(poll_id)

    def mark_published(self, event: Event, poll_uid: str) -> Event:
        """Mark event as published."""
        tmp_event = self.assign_poll_published_date(event)
        return self.assign_poll_uid(tmp_event, poll_uid=poll_uid)
