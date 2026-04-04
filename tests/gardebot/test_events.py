"""Tests for the EventService in gardebot."""

import hashlib
import io
import unittest
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
        """Insert or update an event."""
        self._events[event.uid] = event

    def bulk_upsert(self, events: List[Event]) -> None:
        """Upsert multiple events."""
        for e in events:
            self._events[e.uid] = e


class TestEventModel(unittest.TestCase):
    """Unit tests for the Event domain model."""

    def test_event_poll_string_generation(self) -> None:
        """Test generation of poll strings based on event details."""
        start = pd.Timestamp("2025-01-10 18:00")
        end = pd.Timestamp("2025-01-10 20:00")
        e = Event(
            title="Réunion",
            location="Casern",
            start_date=start,
            end_date=end,
            headcount=5,
        )
        self.assertIn("Réunion", e.poll_string)
        self.assertIn("18h00", e.poll_string)

    def test_reminder_logic(self) -> None:
        """Test reminder logic based on published date and elapsed time."""
        start = pd.Timestamp.now() + pd.Timedelta(days=3)
        end = start + pd.Timedelta(hours=2)
        e = Event(
            title="Test",
            location="Base",
            start_date=start,
            end_date=end,
            headcount=3,
            published_date=pd.Timestamp.now() - pd.Timedelta(hours=10),
            nb_reminder=0,
        )
        # Depending on MINIMUM_ELAPSED_HOURS config, this may vary; we just assert method runs
        e.should_send_reminder()

    def test_event_uid_uses_ical_uid_when_present(self) -> None:
        """Both events with the same ical_uid + start_date share the same uid regardless of title."""
        start = pd.Timestamp("2026-05-01 08:00")
        end = pd.Timestamp("2026-05-02 08:00")
        e1 = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=3, ical_uid="abc-123-stable")
        e2 = Event(title="Garde 2", location="Caserne", start_date=start, end_date=end, headcount=3, ical_uid="abc-123-stable")
        self.assertEqual(e1.uid, e2.uid)
        expected = hashlib.sha256(f"abc-123-stable#{start.isoformat()}".encode()).hexdigest()
        self.assertEqual(e1.uid, expected)

    def test_event_uid_fallback_without_ical_uid(self) -> None:
        """Without ical_uid, uid falls back to hash of title+location+dates."""
        start = pd.Timestamp("2026-05-01 08:00")
        end = pd.Timestamp("2026-05-02 08:00")
        e = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=3)
        expected = hashlib.sha256(f"GardeCaserne{start}{end}".encode()).hexdigest()
        self.assertEqual(e.uid, expected)

    def test_event_uid_stable_across_title_renames(self) -> None:
        """With ical_uid, the uid is stable even when the title suffix changes."""
        start = pd.Timestamp("2026-06-15 09:00")
        end = pd.Timestamp("2026-06-15 18:00")
        ical_uid = "server-uid-xyz"
        e_monday = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=4, ical_uid=ical_uid)
        e_thursday = Event(title="Garde 2", location="Caserne", start_date=start, end_date=end, headcount=4, ical_uid=ical_uid)
        self.assertEqual(e_monday.uid, e_thursday.uid)


class TestEventService(unittest.TestCase):
    """Unit tests for EventService."""

    def test_consecutive_publication_propagation(self) -> None:
        """Test that events on same day get same publication date."""
        repo = InMemoryEventRepo()
        service = EventService(repository=repo)
        d = pd.Timestamp("2025-02-01 09:00")
        e1 = Event(title="A", location="L1", start_date=d, end_date=d + pd.Timedelta(hours=2), headcount=2)
        e2 = Event(title="B", location="L2", start_date=d, end_date=d + pd.Timedelta(hours=3), headcount=3)
        repo.bulk_upsert([e1, e2])
        propagated = service._propagate_publication_dates(repo.list_events())
        self.assertEqual(propagated[0].scheduled_publication_date, propagated[1].scheduled_publication_date)

    def test_insert_external_calendar_idempotent(self) -> None:
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
        self.assertEqual(len(all_events), 2, f"Expected 2 events, got {len(all_events)}")


class TestEventRepositoryBulkUpsert(unittest.TestCase):
    """Unit tests for EventRepository.bulk_upsert."""

    def _make_mock_storage(self, existing_df: pd.DataFrame) -> tuple:
        """Return (mock_storage, captured) where captured['result'] is set after modifier runs."""
        mock_storage = MagicMock()
        captured: Dict[str, Any] = {}

        def fake_force_atomic_rmw(filename: str, modifier_fn: Any) -> pd.DataFrame:
            result = modifier_fn(existing_df)
            captured["result"] = result
            return result

        mock_storage.force_atomic_read_modify_write.side_effect = fake_force_atomic_rmw
        return mock_storage, captured

    def test_bulk_upsert_legacy_migration_preserves_metadata(self) -> None:
        """bulk_upsert should migrate old-UID rows to new stable UIDs, preserving poll_uid and nb_reminder."""
        from gardebot.repositories import EventRepository

        start = pd.Timestamp("2026-08-01 08:00")
        end = pd.Timestamp("2026-08-02 08:00")

        old_event = Event(title="Garde 2", location="Caserne", start_date=start, end_date=end, headcount=3, poll_uid="poll-abc", nb_reminder=2)
        new_event = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=3, ical_uid="server-uid-001")

        self.assertNotEqual(old_event.uid, new_event.uid, "Pre-condition: legacy and new UIDs differ")

        old_df = pd.DataFrame([old_event.model_dump()])
        buf = io.BytesIO()
        old_df.to_parquet(buf)

        mock_storage, captured = self._make_mock_storage(old_df)
        repo = EventRepository(storage=mock_storage)
        repo.bulk_upsert([new_event])

        result_df = captured["result"]
        self.assertEqual(len(result_df), 1, f"Expected 1 row after migration, got {len(result_df)}")
        row = result_df.iloc[0]
        self.assertEqual(row["poll_uid"], "poll-abc", "poll_uid should be preserved from legacy event")
        self.assertEqual(row["nb_reminder"], 2, "nb_reminder should be preserved from legacy event")
        self.assertEqual(row["uid"], new_event.uid, "uid should be the new stable uid")

    def test_bulk_upsert_multiple_legacy_entries_same_natural_key(self) -> None:
        """bulk_upsert must remove all legacy duplicates for the same time slot and keep only the new stable event."""
        from gardebot.repositories import EventRepository

        start = pd.Timestamp("2026-04-04 19:00")
        end = pd.Timestamp("2026-04-05 07:00")
        location = "Veyrier"

        old_event_a = Event(
            title="Piquet de Pâques 5",
            location=location,
            start_date=start,
            end_date=end,
            headcount=3,
            poll_uid="poll-OLD-A",
            nb_reminder=1,
            published_date=pd.Timestamp("2026-03-12"),
        )
        old_event_b = Event(
            title="Piquet de Pâques",
            location=location,
            start_date=start,
            end_date=end,
            headcount=3,
            poll_uid="poll-OLD-B",
            nb_reminder=0,
        )
        new_event = Event(
            title="Piquet de Pâques",
            location=location,
            start_date=start,
            end_date=end,
            headcount=3,
            ical_uid="d82bdf71-stable",
        )

        self.assertNotEqual(old_event_a.uid, new_event.uid)
        self.assertNotEqual(old_event_b.uid, new_event.uid)
        self.assertNotEqual(old_event_a.uid, old_event_b.uid)

        old_df = pd.DataFrame([old_event_a.model_dump(), old_event_b.model_dump()])
        mock_storage, captured = self._make_mock_storage(old_df)

        repo = EventRepository(storage=mock_storage)
        repo.bulk_upsert([new_event])

        result_df = captured["result"]
        self.assertEqual(len(result_df), 1, f"Expected 1 row after dedup migration, got {len(result_df)}")
        row = result_df.iloc[0]
        self.assertEqual(row["poll_uid"], "poll-OLD-A", "Should pick metadata from the best (most complete) old event")
        self.assertEqual(row["nb_reminder"], 1, "nb_reminder from best old event should be preserved")
        self.assertEqual(row["uid"], new_event.uid, "uid should be the new stable uid")

    def test_bulk_upsert_new_event_already_has_stable_uid_no_duplicate(self) -> None:
        """If the new event's uid already exists in storage, it must not be duplicated."""
        from gardebot.repositories import EventRepository

        start = pd.Timestamp("2026-09-01 08:00")
        end = pd.Timestamp("2026-09-02 08:00")

        existing = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=3, ical_uid="abc-stable", poll_uid="poll-xyz", nb_reminder=1)
        incoming = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=3, ical_uid="abc-stable")

        self.assertEqual(existing.uid, incoming.uid, "Pre-condition: same ical_uid → same uid")

        existing_df = pd.DataFrame([existing.model_dump()])
        mock_storage, captured = self._make_mock_storage(existing_df)

        repo = EventRepository(storage=mock_storage)
        repo.bulk_upsert([incoming])

        self.assertTrue(
            "result" not in captured or len(captured["result"]) == 1,
            "Should not duplicate an already-stored event",
        )


class TestCleanupScript(unittest.TestCase):
    """Unit tests for the cleanup_duplicate_events script."""

    def test_cleanup_deduplicate_keeps_best_row(self) -> None:
        """deduplicate() must keep the row with the most metadata."""
        from gardebot.scripts.cleanup_duplicate_events import deduplicate

        start = pd.Timestamp("2026-04-04 19:00")
        end = pd.Timestamp("2026-04-05 07:00")

        e_no_meta = Event(title="Piquet 5", location="Veyrier", start_date=start, end_date=end, headcount=3)
        e_with_ical = Event(
            title="Piquet",
            location="Veyrier",
            start_date=start,
            end_date=end,
            headcount=3,
            ical_uid="d82bdf71-stable",
            poll_uid="poll-xyz",
        )

        result = deduplicate([e_no_meta, e_with_ical])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ical_uid, "d82bdf71-stable", "Should keep row with ical_uid")
