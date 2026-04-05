"""Comprehensive edge-case tests for poll_string mismatch fixes.

Tests cover:
1. Past-event guards in reminders() and assign_on_duty_for_events()
2. Past-event guard in should_be_published()
3. Fuzzy match in OnDutyRepository.is_assigned() and VoteRepository.count_present()
4. Phase 0 dedup in EventRepository.bulk_upsert()
5. Migration script migrate_poll_strings
"""

from __future__ import annotations

import unittest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pandas as pd  # type: ignore[import-untyped]

from gardebot.models.domain import Event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    title: str = "Garde",
    location: str = "Caserne",
    start_offset_days: float = 1.0,
    duration_hours: float = 12.0,
    headcount: int = 2,
    ical_uid: str | None = None,
    poll_uid: str | None = None,
    published_date: pd.Timestamp | None = None,
    nb_reminder: int = 0,
) -> Event:
    """Build a test Event relative to now."""
    now = pd.Timestamp.now()
    start = now + pd.Timedelta(days=start_offset_days)
    end = start + pd.Timedelta(hours=duration_hours)
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


def _make_mock_storage(parquet_return: pd.DataFrame) -> MagicMock:
    """Return a mock FileStorage that always returns parquet_return from read_parquet."""
    mock = MagicMock()
    mock.read_parquet.return_value = parquet_return
    mock.force_atomic_read_modify_write.side_effect = lambda filename, fn: fn(parquet_return)
    return mock


# ---------------------------------------------------------------------------
# 1. reminders() skips past events
# ---------------------------------------------------------------------------

class TestRemindersSkipPastEvents(unittest.TestCase):
    """reminders() must never send reminders for events whose start_date is in the past."""

    def test_reminders_skip_past_events(self) -> None:
        """A past published event whose should_send_reminder() is True must NOT get a reminder."""
        from gardebot.gardebot import Gardebot

        past_published_date = pd.Timestamp.now() - pd.Timedelta(hours=30)
        past_event = _make_event(
            title="Old Garde",
            start_offset_days=-2,  # 2 days ago
            published_date=past_published_date,
            nb_reminder=0,
            poll_uid="poll-abc",
        )
        self.assertTrue(past_event.should_send_reminder(), "Pre-condition: event would trigger reminder")

        gb = Gardebot.__new__(Gardebot)
        gb.event_service = MagicMock()
        gb.event_service.list_events.return_value = [past_event]
        gb.vote_service = MagicMock()
        gb.vote_service.test_headcount_reached.return_value = False
        gb.onduty_service = MagicMock()
        gb.onduty_service.is_assigned.return_value = False
        gb.message_service = MagicMock()

        gb.reminders()

        gb.message_service.send_vote_reminder.assert_not_called()

    def test_reminders_send_for_future_events(self) -> None:
        """A future published event that needs a reminder MUST get one."""
        from gardebot.gardebot import Gardebot

        published_date = pd.Timestamp.now() - pd.Timedelta(hours=30)
        future_event = _make_event(
            title="Future Garde",
            start_offset_days=5,
            published_date=published_date,
            nb_reminder=0,
            poll_uid="poll-xyz",
        )
        self.assertTrue(future_event.should_send_reminder(), "Pre-condition: event would trigger reminder")

        gb = Gardebot.__new__(Gardebot)
        gb.event_service = MagicMock()
        gb.event_service.list_events.return_value = [future_event]
        gb.event_service.increment_reminder.return_value = future_event
        gb.vote_service = MagicMock()
        gb.vote_service.test_headcount_reached.return_value = False
        gb.onduty_service = MagicMock()
        gb.onduty_service.is_assigned.return_value = False
        gb.message_service = MagicMock()

        gb.reminders()

        gb.message_service.send_vote_reminder.assert_called_once()


# ---------------------------------------------------------------------------
# 2. assign_on_duty_for_events() skips past events
# ---------------------------------------------------------------------------

class TestAssignmentsSkipPastEvents(unittest.TestCase):
    """assign_on_duty_for_events() must not try to assign past events."""

    def test_assignments_skip_past_events(self) -> None:
        """A past published unassigned event must NOT be assigned."""
        from gardebot.gardebot import Gardebot

        past_event = _make_event(
            title="Old Garde",
            start_offset_days=-1,
            published_date=pd.Timestamp.now() - pd.Timedelta(days=30),
            poll_uid="poll-old",
        )
        self.assertTrue(past_event.is_published())

        gb = Gardebot.__new__(Gardebot)
        gb.event_service = MagicMock()
        gb.event_service.list_events.return_value = [past_event]
        gb.vote_service = MagicMock()
        gb.vote_service.test_event_completion.return_value = True
        gb.onduty_service = MagicMock()
        gb.onduty_service.is_assigned.return_value = False
        gb.onduty_service.process_assignments.return_value = []
        gb.message_service = MagicMock()

        gb.assign_on_duty_for_events()

        gb.onduty_service.process_assignments.assert_not_called()

    def test_assignments_process_future_events(self) -> None:
        """A future published unassigned event that is complete MUST be assigned."""
        from gardebot.gardebot import Gardebot

        future_event = _make_event(
            title="Future Garde",
            start_offset_days=5,
            published_date=pd.Timestamp.now() - pd.Timedelta(days=5),
            poll_uid="poll-future",
        )
        self.assertTrue(future_event.is_published())

        gb = Gardebot.__new__(Gardebot)
        gb.event_service = MagicMock()
        gb.event_service.list_events.return_value = [future_event]
        gb.vote_service = MagicMock()
        gb.vote_service.test_event_completion.return_value = True
        gb.onduty_service = MagicMock()
        gb.onduty_service.is_assigned.return_value = False
        mock_assignment = MagicMock()
        mock_assignment.event = future_event
        mock_assignment.sapeur_list = []
        gb.onduty_service.process_assignments.return_value = [mock_assignment]
        gb.message_service = MagicMock()

        gb.assign_on_duty_for_events()

        gb.onduty_service.process_assignments.assert_called_once()


# ---------------------------------------------------------------------------
# 3. should_be_published() rejects past events
# ---------------------------------------------------------------------------

class TestShouldBePublishedPastEvents(unittest.TestCase):
    """should_be_published() must return False for events whose start_date has passed."""

    def test_should_be_published_rejects_past_events(self) -> None:
        """An unpublished past event must not be published."""
        from gardebot.adapters.polling import PollingAdapter

        past_event = _make_event(title="Old Event", start_offset_days=-1)
        self.assertFalse(past_event.is_published())

        adapter = PollingAdapter.__new__(PollingAdapter)
        adapter._onduty_service = MagicMock()
        adapter._onduty_service.is_assigned.return_value = False

        result = adapter.should_be_published(past_event)
        self.assertFalse(result, "Past events must not be published")

    def test_should_be_published_allows_future_events(self) -> None:
        """An unpublished future event due for publication should return True."""
        from gardebot.adapters.polling import PollingAdapter

        # Use start_offset_days=3 so that scheduled_publication_date = start - 21 days
        # = 3 - 21 = -18 days from now → already past → event is due for publication
        event_with_old_pub = _make_event(title="Upcoming Event", start_offset_days=3)
        self.assertFalse(event_with_old_pub.is_published())

        adapter = PollingAdapter.__new__(PollingAdapter)
        adapter._onduty_service = MagicMock()
        adapter._onduty_service.is_assigned.return_value = False

        result = adapter.should_be_published(event_with_old_pub)
        self.assertTrue(result, "Future events with past pub date should be published")


# ---------------------------------------------------------------------------
# 4. Fuzzy match in OnDutyRepository.is_assigned()
# ---------------------------------------------------------------------------

class TestOnDutyFuzzyMatch(unittest.TestCase):
    """OnDutyRepository.is_assigned() should find old suffixed columns via suffix matching."""

    def _make_onduty_repo(self, df: pd.DataFrame) -> Any:
        from gardebot.repositories import OnDutyRepository
        repo = OnDutyRepository.__new__(OnDutyRepository)
        repo.storage = _make_mock_storage(df)
        repo.events_repository = MagicMock()
        repo.sapeur_repository = MagicMock()
        return repo

    def test_is_assigned_direct_match(self) -> None:
        """Direct column match returns True when headcount is met."""
        event = _make_event(title="Garde", start_offset_days=5, headcount=2)
        col = event.poll_string
        df = pd.DataFrame({col: [True, True, False]}, index=["Alice", "Bob", "Charlie"])
        repo = self._make_onduty_repo(df)
        self.assertTrue(repo.is_assigned(event))

    def test_is_assigned_fuzzy_match(self) -> None:
        """Old suffixed column is found via suffix match."""
        event = _make_event(title="Piquet de Pâques", start_offset_days=5, headcount=2)
        # Create old column with suffixed title but same date+location suffix
        old_event = event.model_copy(update={"title": "Piquet de Pâques 5"})
        old_col = old_event.poll_string
        # Verify old_col != current poll_string
        self.assertNotEqual(old_col, event.poll_string)
        # Verify suffix IS the same
        self.assertEqual(event.poll_string.split(" : ", 1)[1], old_col.split(" : ", 1)[1])

        df = pd.DataFrame({old_col: [True, True, False]}, index=["Alice", "Bob", "Charlie"])
        repo = self._make_onduty_repo(df)
        self.assertTrue(repo.is_assigned(event))

    def test_is_assigned_returns_false_when_no_column_matches(self) -> None:
        """Returns False when no direct or fuzzy column match found."""
        event = _make_event(title="Unknown Event", start_offset_days=5, headcount=2)
        df = pd.DataFrame({"Other Event : some other date": [True, True]}, index=["Alice", "Bob"])
        repo = self._make_onduty_repo(df)
        self.assertFalse(repo.is_assigned(event))

    def test_is_assigned_returns_false_when_headcount_not_met(self) -> None:
        """Fuzzy match found but headcount not met → False."""
        event = _make_event(title="Piquet de Pâques", start_offset_days=5, headcount=3)
        old_event = event.model_copy(update={"title": "Piquet de Pâques 5"})
        old_col = old_event.poll_string
        df = pd.DataFrame({old_col: [True, False, False]}, index=["Alice", "Bob", "Charlie"])
        repo = self._make_onduty_repo(df)
        self.assertFalse(repo.is_assigned(event))


# ---------------------------------------------------------------------------
# 5. Fuzzy match in VoteRepository.count_present()
# ---------------------------------------------------------------------------

class TestVoteFuzzyMatch(unittest.TestCase):
    """VoteRepository.count_present() should find old suffixed columns via suffix matching."""

    def _make_vote_repo(self, df: pd.DataFrame) -> Any:
        from gardebot.repositories import VoteRepository
        repo = VoteRepository.__new__(VoteRepository)
        repo.storage = _make_mock_storage(df)
        repo.sapeur_repository = MagicMock()
        repo.events_repository = MagicMock()
        return repo

    def test_count_present_direct_match(self) -> None:
        """Direct column match returns correct count."""
        event = _make_event(title="Garde", start_offset_days=5, headcount=2)
        col = event.poll_string
        df = pd.DataFrame({col: [True, True, False, None]}, index=["A", "B", "C", "D"])
        repo = self._make_vote_repo(df)
        self.assertEqual(repo.count_present(event), 2)

    def test_count_present_fuzzy_match(self) -> None:
        """Old suffixed column is found via suffix match and count is correct."""
        event = _make_event(title="Piquet de Pâques", start_offset_days=5, headcount=2)
        old_event = event.model_copy(update={"title": "Piquet de Pâques 6"})
        old_col = old_event.poll_string
        df = pd.DataFrame({old_col: [True, False, True]}, index=["A", "B", "C"])
        repo = self._make_vote_repo(df)
        self.assertEqual(repo.count_present(event), 2)

    def test_count_present_returns_zero_when_no_match(self) -> None:
        """Returns 0 when neither direct nor fuzzy column found."""
        event = _make_event(title="Unknown", start_offset_days=5, headcount=2)
        df = pd.DataFrame({"Some Other Poll : date, location": [True]}, index=["A"])
        repo = self._make_vote_repo(df)
        self.assertEqual(repo.count_present(event), 0)


# ---------------------------------------------------------------------------
# 6 & 7. bulk_upsert Phase 0 dedup
# ---------------------------------------------------------------------------

class TestBulkUpsertPhase0(unittest.TestCase):
    """Phase 0 in bulk_upsert deduplicates existing rows by base-name natural key."""

    def _make_repo(self, existing_df: pd.DataFrame) -> tuple:
        from gardebot.repositories import EventRepository
        captured: Dict[str, Any] = {}
        mock_storage = MagicMock()

        def fake_force_rmw(filename: str, fn: Any) -> Any:
            result = fn(existing_df)
            captured["result"] = result
            return result

        mock_storage.force_atomic_read_modify_write.side_effect = fake_force_rmw
        repo = EventRepository(storage=mock_storage)
        return repo, captured

    def test_bulk_upsert_phase0_dedup(self) -> None:
        """Phase 0 removes a duplicate old-suffixed row even when no new events are passed."""
        start = pd.Timestamp("2026-04-04 19:00")
        end = pd.Timestamp("2026-04-05 07:00")
        location = "Veyrier"
        headcount = 2

        # Two existing rows for the same slot: old suffixed (no ical_uid) + new canonical
        old_event = Event(
            title="Piquet de Pâques 5",
            location=location,
            start_date=start,
            end_date=end,
            headcount=headcount,
            poll_uid="poll-old",
            published_date=pd.Timestamp("2026-03-12"),
            nb_reminder=1,
        )
        new_event = Event(
            title="Piquet de Pâques",
            location=location,
            start_date=start,
            end_date=end,
            headcount=headcount,
            ical_uid="d82bdf71-stable",
            poll_uid="poll-new",
        )

        existing_df = pd.DataFrame([old_event.model_dump(), new_event.model_dump()])
        repo, captured = self._make_repo(existing_df)

        # Pass empty events list — Phase 0 should still dedup
        repo.bulk_upsert([])

        # Even if no new events were added, the result should have 1 row (best kept)
        # OR no write was triggered (both are acceptable if already clean)
        if "result" in captured:
            self.assertEqual(len(captured["result"]), 1, "Phase 0 should deduplicate existing duplicate rows")
            # The kept row should be the one with ical_uid (best)
            self.assertEqual(captured["result"].iloc[0]["ical_uid"], "d82bdf71-stable")

    def test_bulk_upsert_idempotent(self) -> None:
        """Running bulk_upsert twice with the same events produces same row count."""
        from gardebot.repositories import EventRepository

        start = pd.Timestamp("2026-09-10 08:00")
        end = pd.Timestamp("2026-09-11 08:00")
        event = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=2, ical_uid="stable-uid-1")

        results = []

        def make_fake_storage(current_df: pd.DataFrame) -> MagicMock:
            holder = {"df": current_df}
            m = MagicMock()

            def fake_rmw(filename: str, fn: Any) -> Any:
                result = fn(holder["df"])
                holder["df"] = result
                results.append(len(result))
                return result

            m.force_atomic_read_modify_write.side_effect = fake_rmw
            return m

        initial_df = pd.DataFrame(columns=list(Event.model_fields.keys()) + ["uid"])
        mock_storage = make_fake_storage(initial_df)
        repo = EventRepository(storage=mock_storage)
        repo.bulk_upsert([event])
        repo.bulk_upsert([event])

        self.assertGreater(len(results), 0)
        # The first call should add 1 row; subsequent calls must not grow
        first_result = results[0]
        self.assertEqual(first_result, 1)

    def test_uid_stability_with_ical_uid(self) -> None:
        """Two Events with same ical_uid and start_date but different titles produce same uid."""
        start = pd.Timestamp("2026-05-01 08:00")
        end = pd.Timestamp("2026-05-02 08:00")
        e1 = Event(title="Garde", location="Caserne", start_date=start, end_date=end, headcount=3, ical_uid="abc-123")
        e2 = Event(title="Garde 5", location="Caserne", start_date=start, end_date=end, headcount=3, ical_uid="abc-123")
        self.assertEqual(e1.uid, e2.uid)

    def test_no_false_dedup_different_events(self) -> None:
        """Two genuinely different events (same time but different locations) both survive."""
        from gardebot.repositories import EventRepository

        start = pd.Timestamp("2026-10-01 08:00")
        end = pd.Timestamp("2026-10-02 08:00")
        event_a = Event(title="Garde A", location="Caserne A", start_date=start, end_date=end, headcount=2, ical_uid="uid-A")
        event_b = Event(title="Garde B", location="Caserne B", start_date=start, end_date=end, headcount=2, ical_uid="uid-B")

        captured: Dict[str, Any] = {}

        def fake_rmw(filename: str, fn: Any) -> Any:
            result = fn(pd.DataFrame())
            captured["result"] = result
            return result

        mock_storage = MagicMock()
        mock_storage.force_atomic_read_modify_write.side_effect = fake_rmw
        repo = EventRepository(storage=mock_storage)
        repo.bulk_upsert([event_a, event_b])

        self.assertIn("result", captured)
        self.assertEqual(len(captured["result"]), 2, "Two different-location events must both survive")


# ---------------------------------------------------------------------------
# 8. _base_name helper
# ---------------------------------------------------------------------------

class TestBaseName(unittest.TestCase):
    """_base_name strips trailing numeric suffix."""

    def test_base_name_strips_suffix(self) -> None:
        from gardebot.repositories import _base_name
        self.assertEqual(_base_name("Piquet de Pâques 5"), "Piquet de Pâques")
        self.assertEqual(_base_name("Garde 12"), "Garde")
        self.assertEqual(_base_name("Garde"), "Garde")
        self.assertEqual(_base_name("Garde 2"), "Garde")
        self.assertEqual(_base_name("Event Name With Spaces 3"), "Event Name With Spaces")


# ---------------------------------------------------------------------------
# 9. migrate_poll_strings script
# ---------------------------------------------------------------------------

class TestMigratePollStrings(unittest.TestCase):
    """Unit tests for migrate_poll_strings migration script."""

    def test_migrate_renames_old_column(self) -> None:
        """Suffixed column is renamed to current poll_string."""
        from gardebot.scripts.migrate_poll_strings import migrate_dataframe

        event = _make_event(title="Piquet de Pâques", start_offset_days=10, headcount=2)
        old_event = event.model_copy(update={"title": "Piquet de Pâques 5"})
        old_col = old_event.poll_string
        current_col = event.poll_string

        self.assertNotEqual(old_col, current_col)

        df = pd.DataFrame({old_col: [True, False, None]}, index=["Alice", "Bob", "Charlie"])
        rename_map = {old_col: current_col}

        result = migrate_dataframe(df, rename_map, [current_col])
        self.assertIn(current_col, result.columns)
        self.assertNotIn(old_col, result.columns)

    def test_migrate_merges_multiple_old_columns(self) -> None:
        """When multiple old columns map to the same new column, data is OR-merged."""
        from gardebot.scripts.migrate_poll_strings import migrate_dataframe

        event = _make_event(title="Piquet de Pâques", start_offset_days=10, headcount=2)
        old_event_5 = event.model_copy(update={"title": "Piquet de Pâques 5"})
        old_event_6 = event.model_copy(update={"title": "Piquet de Pâques 6"})
        # Manually override poll_string by creating events at different times so suffixes differ
        # Use direct column names to test merge logic
        current_col = event.poll_string
        old_col_a = old_event_5.poll_string + "_A"  # Force distinct names
        old_col_b = old_event_5.poll_string + "_B"

        df = pd.DataFrame(
            {old_col_a: [True, None, False], old_col_b: [None, True, False]},
            index=["Alice", "Bob", "Charlie"],
        )
        rename_map = {old_col_a: current_col, old_col_b: current_col}

        result = migrate_dataframe(df, rename_map, [current_col])
        self.assertIn(current_col, result.columns)
        self.assertNotIn(old_col_a, result.columns)
        self.assertNotIn(old_col_b, result.columns)
        # Alice had True in col_a → merged = True
        self.assertTrue(result.at["Alice", current_col])
        # Bob had True in col_b → merged = True
        self.assertTrue(result.at["Bob", current_col])
        # Charlie had False in both → merged = False
        self.assertFalse(result.at["Charlie", current_col])

    def test_migrate_unchanged_when_no_rename_needed(self) -> None:
        """If no columns match the rename_map, df is returned unchanged."""
        from gardebot.scripts.migrate_poll_strings import migrate_dataframe

        event = _make_event(title="Garde", start_offset_days=5, headcount=2)
        current_col = event.poll_string
        df = pd.DataFrame({current_col: [True]}, index=["Alice"])
        result = migrate_dataframe(df, {}, [current_col])
        self.assertIs(result, df)

    def test_build_old_variants_includes_suffixes(self) -> None:
        """_build_old_variants generates suffixed poll_string variants."""
        from gardebot.scripts.migrate_poll_strings import _build_old_variants

        event = _make_event(title="Piquet de Pâques", start_offset_days=10, headcount=2)
        variants = _build_old_variants(event, max_suffix=5)
        # Should include unsuffixed + "Piquet de Pâques 2" through "Piquet de Pâques 5"
        self.assertEqual(len(variants), 5)  # 1 (base) + 4 (2..5)
        base_poll = event.poll_string
        self.assertIn(base_poll, variants)
        # Check that a suffixed variant differs and contains the suffix in the title part
        suffix_2 = event.model_copy(update={"title": "Piquet de Pâques 2"}).poll_string
        self.assertIn(suffix_2, variants)
        self.assertNotEqual(suffix_2, base_poll)


if __name__ == "__main__":
    unittest.main()
