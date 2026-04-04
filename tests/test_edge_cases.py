"""Edge-case tests for Gardebot – covers past-event guards, bulk_upsert dedup, and UID stability."""

from __future__ import annotations

import hashlib
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pandas as pd  # type: ignore[import-untyped]

from gardebot.models.domain import Event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    title: str = "Garde",
    location: str = "Caserne",
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
    headcount: int = 3,
    ical_uid: str | None = None,
    poll_uid: str | None = None,
    published_date: pd.Timestamp | None = None,
    nb_reminder: int = 0,
) -> Event:
    """Return an Event with sensible defaults."""
    if start is None:
        start = pd.Timestamp("2026-06-01 08:00")
    if end is None:
        end = start + pd.Timedelta(hours=12)
    return Event(
        title=title,
        location=location,
        start_date=start,
        end_date=end,
        headcount=headcount,
        ical_uid=ical_uid,
        poll_uid=poll_uid,
        published_date=published_date,
        nb_reminder=nb_reminder,
    )


def _make_mock_storage(existing_df: pd.DataFrame):
    """Return (mock_storage, captured) where captured['result'] is set after modifier runs."""
    mock_storage = MagicMock()
    captured: Dict[str, Any] = {}

    def fake_force_atomic_rmw(filename: str, modifier_fn: Any) -> pd.DataFrame:
        result = modifier_fn(existing_df)
        captured["result"] = result
        return result

    mock_storage.force_atomic_read_modify_write.side_effect = fake_force_atomic_rmw
    return mock_storage, captured


# ---------------------------------------------------------------------------
# Test 1: bulk_upsert idempotency
# ---------------------------------------------------------------------------


class TestBulkUpsertIdempotent(unittest.TestCase):
    """Test 1: Running bulk_upsert twice with same events leaves row count unchanged."""

    def test_bulk_upsert_idempotent(self) -> None:
        from gardebot.repositories import EventRepository

        ev = _make_event(ical_uid="uid-01")
        first_df = pd.DataFrame([ev.model_dump()])

        mock_storage, captured = _make_mock_storage(first_df)
        repo = EventRepository(storage=mock_storage)

        # Second call with same event — should be a no-op (same uid already stored)
        repo.bulk_upsert([ev])

        # When no changes occur the modifier may return the original df or skip write
        if "result" in captured:
            self.assertEqual(len(captured["result"]), 1, "Row count must not grow on second call")


# ---------------------------------------------------------------------------
# Test 2: Phase 0 dedup of existing rows
# ---------------------------------------------------------------------------


class TestBulkUpsertPhase0Dedup(unittest.TestCase):
    """Test 2: Phase 0 deduplicates existing rows sharing the same natural key."""

    def test_bulk_upsert_phase0_dedup(self) -> None:
        from gardebot.repositories import EventRepository

        start = pd.Timestamp("2026-05-10 06:00")
        end = pd.Timestamp("2026-05-10 18:00")

        # Two existing rows with the same natural key: one has ical_uid, one doesn't
        e_legacy = _make_event(title="Piquet", location="Veyrier", start=start, end=end, poll_uid="poll-legacy", nb_reminder=2)
        e_canonical = _make_event(title="Piquet", location="Veyrier", start=start, end=end, ical_uid="uid-canon")

        self.assertNotEqual(e_legacy.uid, e_canonical.uid, "Pre-condition: different uids before dedup")

        existing_df = pd.DataFrame([e_legacy.model_dump(), e_canonical.model_dump()])
        mock_storage, captured = _make_mock_storage(existing_df)
        repo = EventRepository(storage=mock_storage)

        # Call bulk_upsert with empty list to trigger Phase 0 only
        repo.bulk_upsert([])

        self.assertIn("result", captured, "Phase 0 should have triggered a write")
        result_df = captured["result"]
        self.assertEqual(len(result_df), 1, "Phase 0 should collapse duplicates to one row")
        row = result_df.iloc[0]
        self.assertEqual(row["ical_uid"], "uid-canon", "Should keep the row with ical_uid")
        self.assertEqual(row["poll_uid"], "poll-legacy", "Should migrate poll_uid from dropped row")
        self.assertEqual(row["nb_reminder"], 2, "Should migrate nb_reminder from dropped row")


# ---------------------------------------------------------------------------
# Test 3: Stale legacy row cleaned up when canonical arrives
# ---------------------------------------------------------------------------


class TestBulkUpsertStaleCleanup(unittest.TestCase):
    """Test 3: Legacy row (no ical_uid) is removed when canonical event arrives."""

    def test_bulk_upsert_stale_cleanup(self) -> None:
        from gardebot.repositories import EventRepository

        start = pd.Timestamp("2026-05-20 07:00")
        end = pd.Timestamp("2026-05-20 19:00")

        legacy = _make_event(
            title="Piquet de Pâques 5",
            location="Veyrier",
            start=start,
            end=end,
            poll_uid="poll-stale",
            nb_reminder=1,
            published_date=pd.Timestamp("2026-03-12"),
        )
        canonical = _make_event(title="Piquet de Pâques", location="Veyrier", start=start, end=end, ical_uid="uid-stable")

        self.assertNotEqual(legacy.uid, canonical.uid)

        existing_df = pd.DataFrame([legacy.model_dump()])
        mock_storage, captured = _make_mock_storage(existing_df)
        repo = EventRepository(storage=mock_storage)

        repo.bulk_upsert([canonical])

        result_df = captured["result"]
        self.assertEqual(len(result_df), 1, "Legacy row should be removed after stale cleanup")
        row = result_df.iloc[0]
        self.assertEqual(row["uid"], canonical.uid, "Canonical uid should be the surviving row")
        self.assertEqual(row["poll_uid"], "poll-stale", "poll_uid migrated from legacy")
        self.assertEqual(row["nb_reminder"], 1, "nb_reminder migrated from legacy")
        self.assertEqual(row["published_date"], pd.Timestamp("2026-03-12"), "published_date migrated from legacy")


# ---------------------------------------------------------------------------
# Test 4: Stale cleanup when canonical already exists
# ---------------------------------------------------------------------------


class TestBulkUpsertStaleCleanupCanonicalExists(unittest.TestCase):
    """Test 4: Legacy row removed and canonical retains metadata when both pre-exist."""

    def test_bulk_upsert_stale_cleanup_when_canonical_exists(self) -> None:
        from gardebot.repositories import EventRepository

        start = pd.Timestamp("2026-05-25 08:00")
        end = pd.Timestamp("2026-05-25 20:00")

        legacy = _make_event(title="Piquet 3", location="Veyrier", start=start, end=end, poll_uid="poll-from-legacy", nb_reminder=2)
        canonical = _make_event(
            title="Piquet",
            location="Veyrier",
            start=start,
            end=end,
            ical_uid="uid-canon",
            poll_uid="poll-canon",
            nb_reminder=1,
            published_date=pd.Timestamp("2026-04-01"),
        )

        self.assertNotEqual(legacy.uid, canonical.uid)

        existing_df = pd.DataFrame([legacy.model_dump(), canonical.model_dump()])
        mock_storage, captured = _make_mock_storage(existing_df)
        repo = EventRepository(storage=mock_storage)

        # Call with canonical again (incoming ICS)
        canonical_incoming = _make_event(title="Piquet", location="Veyrier", start=start, end=end, ical_uid="uid-canon")
        repo.bulk_upsert([canonical_incoming])

        self.assertIn("result", captured, "Should write after removing legacy row")
        result_df = captured["result"]
        self.assertEqual(len(result_df), 1, "Only canonical row should remain")
        row = result_df.iloc[0]
        self.assertEqual(row["uid"], canonical.uid)
        # poll_uid from canonical (already set, higher priority)
        self.assertEqual(row["poll_uid"], "poll-canon")
        # nb_reminder: max(2, 1) = 2 from legacy
        self.assertEqual(row["nb_reminder"], 2)


# ---------------------------------------------------------------------------
# Test 5: reminders() skips past events
# ---------------------------------------------------------------------------


class TestRemindersSkipPastEvents(unittest.TestCase):
    """Test 5: reminders() must not send reminders for events whose start_date has passed."""

    def test_reminders_skip_past_events(self) -> None:
        from gardebot.gardebot import Gardebot

        past_start = pd.Timestamp.now() - pd.Timedelta(days=1)
        past_end = past_start + pd.Timedelta(hours=12)
        past_event = Event(
            title="Garde passée",
            location="Caserne",
            start_date=past_start,
            end_date=past_end,
            headcount=3,
            published_date=pd.Timestamp.now() - pd.Timedelta(days=30),
            nb_reminder=1,
        )

        bot = Gardebot.__new__(Gardebot)
        bot.event_service = MagicMock()
        bot.event_service.list_events.return_value = [past_event]
        bot.vote_service = MagicMock()
        bot.vote_service.test_headcount_reached.return_value = False
        bot.onduty_service = MagicMock()
        bot.onduty_service.is_assigned.return_value = False
        bot.message_service = MagicMock()

        bot.reminders()

        bot.message_service.send_vote_reminder.assert_not_called()
        bot.event_service.increment_reminder.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: assign_on_duty_for_events() skips past events
# ---------------------------------------------------------------------------


class TestAssignmentsSkipPastEvents(unittest.TestCase):
    """Test 6: assign_on_duty_for_events() must not process past events."""

    def test_assignments_skip_past_events(self) -> None:
        from gardebot.gardebot import Gardebot

        past_start = pd.Timestamp.now() - pd.Timedelta(hours=2)
        past_end = past_start + pd.Timedelta(hours=12)
        past_event = Event(
            title="Garde passée",
            location="Caserne",
            start_date=past_start,
            end_date=past_end,
            headcount=3,
            poll_uid="poll-x",
            published_date=pd.Timestamp.now() - pd.Timedelta(days=5),
        )

        bot = Gardebot.__new__(Gardebot)
        bot.event_service = MagicMock()
        bot.event_service.list_events.return_value = [past_event]
        bot.vote_service = MagicMock()
        bot.vote_service.test_event_completion.return_value = True
        bot.onduty_service = MagicMock()
        bot.onduty_service.is_assigned.return_value = False
        bot.message_service = MagicMock()

        bot.assign_on_duty_for_events()

        bot.onduty_service.process_assignments.assert_not_called()
        bot.message_service.send_convocation.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7: should_be_published() rejects past events
# ---------------------------------------------------------------------------


class TestShouldBePublishedRejectsPastEvents(unittest.TestCase):
    """Test 7: should_be_published() returns False for events whose start_date is in the past."""

    def test_should_be_published_rejects_past_events(self) -> None:
        from gardebot.adapters.polling import PollingAdapter

        past_start = pd.Timestamp.now() - pd.Timedelta(days=1)
        past_end = past_start + pd.Timedelta(hours=12)
        event = Event(
            title="Garde passée",
            location="Caserne",
            start_date=past_start,
            end_date=past_end,
            headcount=3,
        )

        adapter = PollingAdapter.__new__(PollingAdapter)
        adapter._event_service = MagicMock()
        adapter._vote_service = MagicMock()
        adapter._onduty_service = MagicMock()
        adapter._onduty_service.is_assigned.return_value = False
        adapter._sapeur_repo = MagicMock()

        result = adapter.should_be_published(event)
        self.assertFalse(result, "should_be_published() must return False for past events")


# ---------------------------------------------------------------------------
# Test 8: UID stability with ical_uid
# ---------------------------------------------------------------------------


class TestUidStabilityWithIcalUid(unittest.TestCase):
    """Test 8: Two events sharing ical_uid + start_date produce the same uid regardless of title."""

    def test_uid_stability_with_ical_uid(self) -> None:
        start = pd.Timestamp("2026-07-01 08:00")
        end = pd.Timestamp("2026-07-01 20:00")
        e1 = _make_event(title="Garde", start=start, end=end, ical_uid="server-uid-abc")
        e2 = _make_event(title="Garde 3", start=start, end=end, ical_uid="server-uid-abc")

        self.assertEqual(e1.uid, e2.uid, "ical_uid must dominate title when computing uid")
        expected = hashlib.sha256(f"server-uid-abc#{start.isoformat()}".encode()).hexdigest()
        self.assertEqual(e1.uid, expected)


# ---------------------------------------------------------------------------
# Test 9: UID stability without ical_uid
# ---------------------------------------------------------------------------


class TestUidStabilityWithoutIcalUid(unittest.TestCase):
    """Test 9: Two events without ical_uid sharing title/location/dates produce the same uid."""

    def test_uid_stability_without_ical_uid(self) -> None:
        start = pd.Timestamp("2026-07-05 09:00")
        end = pd.Timestamp("2026-07-05 21:00")
        e1 = _make_event(title="Piquet", location="Veyrier", start=start, end=end)
        e2 = _make_event(title="Piquet", location="Veyrier", start=start, end=end)

        self.assertEqual(e1.uid, e2.uid)
        expected = hashlib.sha256(f"PiquetVeyrier{start}{end}".encode()).hexdigest()
        self.assertEqual(e1.uid, expected)


# ---------------------------------------------------------------------------
# Test 10: No false dedup for genuinely different events
# ---------------------------------------------------------------------------


class TestBulkUpsertNoFalseDedupDifferentEvents(unittest.TestCase):
    """Test 10: Two different events at the same time/location with different names survive dedup."""

    def test_bulk_upsert_does_not_false_dedup_different_events(self) -> None:
        from gardebot.repositories import EventRepository

        start = pd.Timestamp("2026-08-10 08:00")
        end = pd.Timestamp("2026-08-10 20:00")

        # Different names with no trailing numeric suffix → different base names
        ev_a = _make_event(title="Garde A", location="Caserne", start=start, end=end, ical_uid="uid-a")
        ev_b = _make_event(title="Garde B", location="Caserne", start=start, end=end, ical_uid="uid-b")

        self.assertNotEqual(ev_a.uid, ev_b.uid)

        existing_df = pd.DataFrame([ev_a.model_dump(), ev_b.model_dump()])
        mock_storage, captured = _make_mock_storage(existing_df)
        repo = EventRepository(storage=mock_storage)

        # Call with both events again — no dedup should happen
        repo.bulk_upsert([ev_a, ev_b])

        # Either no write (no changes) or still 2 rows
        if "result" in captured:
            self.assertEqual(len(captured["result"]), 2, "Genuinely different events must not be merged")


if __name__ == "__main__":
    unittest.main()
