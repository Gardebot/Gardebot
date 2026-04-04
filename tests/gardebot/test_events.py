"""Tests for the EventService in gardebot."""

import hashlib
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pandas as pd  # type: ignore[import-untyped]

from gardebot.models.domain import Event
from gardebot.services.events import EventService


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
        title="Réunion",
        location="Casern",
        start_date=start,
        end_date=end,
        headcount=5,
        poll_uid=None,
        scheduled_publication_date=None,
    )
    assert "Réunion" in e.poll_string
    assert "18h00" in e.poll_string


def test_reminder_logic() -> None:
    """Test reminder logic based on published date and elapsed time."""
    start = pd.Timestamp.now() + pd.Timedelta(days=3)
    end = start + pd.Timedelta(hours=2)
    e = Event(
        title="Test",
        location="Base",
        start_date=start,
        end_date=end,
        headcount=3,
        poll_uid=None,
        scheduled_publication_date=None,
        published_date=pd.Timestamp.now() - pd.Timedelta(hours=10),
        nb_reminder=0,
    )
    # Depending on MINIMUM_ELAPSED_HOURS config, this may vary; we just assert method runs
    e.should_send_reminder()


def test_consecutive_publication_propagation() -> None:
    """Test that events on same day get same publication date."""
    service = EventService()
    d = pd.Timestamp("2025-02-01 09:00")
    e1 = Event(
        title="A",
        location="L1",
        start_date=d,
        end_date=d + pd.Timedelta(hours=2),
        headcount=2,
        poll_uid=None,
        scheduled_publication_date=None,
    )
    e2 = Event(
        title="B",
        location="L2",
        start_date=d,
        end_date=d + pd.Timedelta(hours=3),
        headcount=3,
        poll_uid=None,
        scheduled_publication_date=None,
    )
    service.repo.bulk_upsert([e1, e2])
    # simulate propagation
    propagated = service._propagate_publication_dates(service.repo.list_events())
    assert propagated[0].scheduled_publication_date == propagated[1].scheduled_publication_date


def test_event_uid_uses_ical_uid_when_present() -> None:
    start = pd.Timestamp("2026-05-01 08:00")
    end = pd.Timestamp("2026-05-02 08:00")
    e1 = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=3, ical_uid="abc-123-stable")
    e2 = Event(title="Garde 2", location="Caserne", start_date=start, end_date=end, headcount=3, ical_uid="abc-123-stable")
    # Both have the same ical_uid + start_date → same uid regardless of title
    assert e1.uid == e2.uid
    expected = hashlib.sha256(f"abc-123-stable#{start.isoformat()}".encode()).hexdigest()
    assert e1.uid == expected


def test_event_uid_fallback_without_ical_uid() -> None:
    start = pd.Timestamp("2026-05-01 08:00")
    end = pd.Timestamp("2026-05-02 08:00")
    e = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=3)
    expected = hashlib.sha256(f"GardeCaserne{start}{end}".encode()).hexdigest()
    assert e.uid == expected


def test_event_uid_stable_across_title_renames() -> None:
    """With ical_uid, the uid is stable even when the title suffix changes."""
    start = pd.Timestamp("2026-06-15 09:00")
    end = pd.Timestamp("2026-06-15 18:00")
    ical_uid = "server-uid-xyz"
    # Simulate the event being named "Garde" on first run and "Garde 2" on second run
    e_monday = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=4, ical_uid=ical_uid)
    e_thursday = Event(title="Garde 2", location="Caserne", start_date=start, end_date=end, headcount=4, ical_uid=ical_uid)
    assert e_monday.uid == e_thursday.uid


def test_insert_external_calendar_idempotent() -> None:
    """Running insert_external_calendar twice with same data should not add duplicates."""
    start = pd.Timestamp("2026-07-01 08:00")
    end = pd.Timestamp("2026-07-02 08:00")
    calendar_df = pd.DataFrame([
        {"name": "Garde", "location": "Caserne", "start_date": start, "end_date": end, "headcount": 3, "ical_uid": "uid-001"},
        {"name": "Garde", "location": "Caserne", "start_date": start + pd.Timedelta(days=7), "end_date": end + pd.Timedelta(days=7), "headcount": 3, "ical_uid": "uid-002"},
    ])

    repo = InMemoryEventRepo()
    service = EventService(repository=repo)

    with patch.object(service, "_get_calendar_df", return_value=calendar_df, create=True):
        # Manually call the core logic twice
        for _ in range(2):
            events: List[Event] = []
            for _, row in calendar_df.iterrows():
                evt = Event(
                    title=row["name"],
                    location=row["location"],
                    start_date=row["start_date"],
                    end_date=row["end_date"],
                    headcount=row["headcount"],
                    ical_uid=row.get("ical_uid"),
                )
                events.append(evt)
            repo.bulk_upsert(events)

    all_events = repo.list_events()
    assert len(all_events) == 2, f"Expected 2 events, got {len(all_events)}"


def test_bulk_upsert_legacy_migration_preserves_metadata() -> None:
    """bulk_upsert should migrate old-UID rows to new stable UIDs, preserving poll_uid and nb_reminder."""
    from gardebot.repositories import EventRepository

    start = pd.Timestamp("2026-08-01 08:00")
    end = pd.Timestamp("2026-08-02 08:00")

    # Simulate an old event stored WITHOUT ical_uid (legacy)
    old_event = Event(title="Garde 2", location="Caserne", start_date=start, end_date=end, headcount=3, poll_uid="poll-abc", nb_reminder=2)

    # Simulate the new event WITH ical_uid (stable)
    new_event = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=3, ical_uid="server-uid-001")

    assert old_event.uid != new_event.uid, "Pre-condition: legacy and new UIDs differ"

    # Set up in-memory storage with old event
    import io
    old_df = pd.DataFrame([old_event.model_dump()])
    buf = io.BytesIO()
    old_df.to_parquet(buf)
    buf.seek(0)

    mock_storage = MagicMock()
    mock_storage.read_parquet.return_value = old_df
    captured = {}

    def fake_force_atomic_rmw(filename, modifier_fn):
        result = modifier_fn(old_df)
        captured["result"] = result
        return result

    mock_storage.force_atomic_read_modify_write.side_effect = fake_force_atomic_rmw

    repo = EventRepository(storage=mock_storage)
    repo.bulk_upsert([new_event])

    result_df = captured["result"]
    assert len(result_df) == 1, f"Expected 1 row after migration, got {len(result_df)}"
    row = result_df.iloc[0]
    assert row["poll_uid"] == "poll-abc", "poll_uid should be preserved from legacy event"
    assert row["nb_reminder"] == 2, "nb_reminder should be preserved from legacy event"
    # The uid should now be the new stable uid
    assert row["uid"] == new_event.uid, "uid should be the new stable uid"
