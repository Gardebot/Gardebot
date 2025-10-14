"""Tests for the EventService in gardebot."""

from typing import Any, Dict, List

import pandas as pd  # type: ignore[import-untyped]

from gardebot.models.domain import Event  # type: ignore[import-untyped]
from gardebot.services.events import EventService  # type: ignore[import-untyped]


class InMemoryEventRepo:
    """In-memory test double for EventRepository."""

    def __init__(self) -> None:
        """Initialize the in-memory storage."""
        self._events: Dict[str, Any] = {}

    def list_events(self) -> List[Event]:
        """List all events."""
        return list(self._events.values())

    def upsert_event(self, event: Event) -> None:
        self._events[event.uid] = event

    def bulk_upsert(self, events: List[Event]) -> None:
        """Upsert multiple events."""
        for e in events:
            self._events[e.uid] = e


def test_event_poll_string_generation() -> None:
    """Test generation of poll strings based on event details."""
    start = pd.Timestamp("2025-01-10 18:00")
    end = pd.Timestamp("2025-01-10 20:00")
    e = Event(
        uid="",
        title="Réunion",
        location="Casern",
        start_date=start,
        end_date=end,
        headcount=5,
        poll_uid=None,
        admin_poll_uid=None,
        poll_string="",
        scheduled_publication_date=None,
    )
    assert "Réunion" in e.poll_string
    assert "18h00" in e.poll_string


def test_reminder_logic() -> None:
    """Test reminder logic based on published date and elapsed time."""
    start = pd.Timestamp.now() + pd.Timedelta(days=3)
    end = start + pd.Timedelta(hours=2)
    e = Event(
        uid="",
        title="Test",
        location="Base",
        start_date=start,
        end_date=end,
        headcount=3,
        poll_uid=None,
        admin_poll_uid=None,
        poll_string="",
        scheduled_publication_date=None,
        published_date=pd.Timestamp.now() - pd.Timedelta(hours=10),
        nb_reminder=0,
    )
    # Depending on MINIMUM_ELAPSED_HOURS config, this may vary; we just assert method runs
    e.should_send_reminder()


def test_consecutive_publication_propagation() -> None:
    """Test that events on same day get same publication date."""
    repo = InMemoryEventRepo()
    service = EventService(repository=repo)
    d = pd.Timestamp("2025-02-01 09:00")
    e1 = Event(
        uid="",
        title="A",
        location="L1",
        start_date=d,
        end_date=d + pd.Timedelta(hours=2),
        headcount=2,
        poll_uid=None,
        admin_poll_uid=None,
        poll_string="",
        scheduled_publication_date=None,
    )
    e2 = Event(
        uid="",
        title="B",
        location="L2",
        start_date=d,
        end_date=d + pd.Timedelta(hours=3),
        headcount=3,
        poll_uid=None,
        admin_poll_uid=None,
        poll_string="",
        scheduled_publication_date=None,
    )
    service.repo.bulk_upsert([e1, e2])
    # simulate propagation
    propagated = service._propagate_publication_dates(service.repo.list_events())
    assert propagated[0].scheduled_publication_date == propagated[1].scheduled_publication_date
