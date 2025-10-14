"""High-level event logic (fetch, enrich, publish, reminders)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from gardebot.infomaniak import InfomaniakCalendar
from gardebot.models.domain import Event
from gardebot.repositories import EventRepository


class EventService:
    """High-level event logic (fetch, enrich, publish, reminders)."""

    def __init__(self, repository: Optional[EventRepository] = None) -> None:
        """Initialize with optional custom repository."""
        self.repo = repository or EventRepository()

    def fetch_and_sync_external_calendar(self) -> List[Event]:
        """Fetch events from external calendar and upsert into repository (idempotent)."""
        calendar_df = InfomaniakCalendar().fetch_calendar()
        events: List[Event] = []
        for _, row in calendar_df.iterrows():
            evt = Event(
                uid="",
                title=row["name"],
                location=row["location"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                headcount=row["headcount"],
                poll_uid=None,
                admin_poll_uid=None,
                poll_string="",
                scheduled_publication_date=None,
            )
            events.append(evt)
        # Align consecutive publication dates
        events = self._propagate_publication_dates(events)
        self.repo.bulk_upsert(events)
        return events

    def _propagate_publication_dates(self, events: List[Event]) -> List[Event]:
        """Ensure events on same start date share publication schedule like legacy behavior."""
        events_sorted = sorted(events, key=lambda e: e.start_date)
        previous_by_date: Dict[Any, Any] = {}
        updated: List[Event] = []
        for evt in events_sorted:
            date_key = evt.start_date.date()
            if date_key in previous_by_date:
                evt = evt.model_copy(update={"scheduled_publication_date": previous_by_date[date_key].scheduled_publication_date})  # noqa: PLW2901
            previous_by_date[date_key] = evt
            updated.append(evt)
        return updated

    def list_events(self) -> List[Event]:
        """Return all events."""
        return self.repo.list_events()

    def mark_published(self, poll_string: str) -> Event:
        """Set published date for event."""
        evt = self.repo.find_by_poll_string(poll_string)
        if not evt:
            raise ValueError(f"Event {poll_string} not found")
        updated = evt.mark_published()
        self.repo.upsert_event(updated)
        return updated

    def increment_reminder(self, poll_string: str) -> Event:
        """Increment reminder count for event."""
        evt = self.repo.find_by_poll_string(poll_string)
        if not evt:
            raise ValueError(f"Event {poll_string} not found")
        updated = evt.increment_reminder()
        self.repo.upsert_event(updated)
        return updated

    def events_needing_reminder(self) -> List[Event]:
        """Return events for which a reminder should be sent."""
        return [e for e in self.repo.list_events() if e.should_send_reminder()]
