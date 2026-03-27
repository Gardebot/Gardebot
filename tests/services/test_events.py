"""Unit tests for EventService."""

import unittest
from typing import Any
from unittest.mock import Mock, patch

import pandas as pd  # type: ignore[import-untyped]

from gardebot.models.domain import Event
from gardebot.services.events import EventService


class TestEventService(unittest.TestCase):
    """Test EventService class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_repo = Mock()
        self.service = EventService(repository=self.mock_repo)
        self.sample_event = Event(
            title="Test Event",
            location="Test Location",
            start_date=pd.Timestamp("2025-10-24 10:00:00+01:00"),
            end_date=pd.Timestamp("2025-10-24 18:00:00+01:00"),
            headcount=3,
        )

    def test_init_with_default_repository(self) -> None:
        """Test initialization with default repository."""
        service = EventService()
        self.assertIsNotNone(service.repo)

    def test_init_with_custom_repository(self) -> None:
        """Test initialization with custom repository."""
        self.assertEqual(self.service.repo, self.mock_repo)

    def test_synchronize_events(self) -> None:
        """Test synchronize_events calls insert_external_calendar."""
        with patch.object(self.service, "insert_external_calendar", return_value=[]) as mock_insert:
            self.service.synchronize_events()
            mock_insert.assert_called_once()

    @patch("gardebot.services.events.InfomaniakCalendar")
    def test_insert_external_calendar(self, mock_calendar_class: Any) -> None:
        """Test inserting events from external calendar."""
        mock_calendar = mock_calendar_class.return_value
        mock_df = pd.DataFrame(
            {
                "name": ["Event 1", "Event 2"],
                "location": ["Loc 1", "Loc 2"],
                "start_date": [pd.Timestamp("2025-10-24 10:00:00+01:00"), pd.Timestamp("2025-10-25 10:00:00+01:00")],
                "end_date": [pd.Timestamp("2025-10-24 18:00:00+01:00"), pd.Timestamp("2025-10-25 18:00:00+01:00")],
                "headcount": [3, 4],
            }
        )
        mock_calendar.fetch_calendar.return_value = mock_df
        self.mock_repo.bulk_upsert.return_value = None

        with patch.object(self.service, "_propagate_publication_dates", side_effect=lambda x: x) as mock_propagate:
            result = self.service.insert_external_calendar()

            self.assertEqual(len(result), 2)
            self.assertEqual(result[0].title, "Event 1")
            self.assertEqual(result[1].title, "Event 2")
            mock_propagate.assert_called_once()
            self.mock_repo.bulk_upsert.assert_called_once()

    def test_propagate_publication_dates(self) -> None:
        """Test publication date propagation for consecutive events."""
        event1 = Event(
            title="Event 1",
            location="Location",
            start_date=pd.Timestamp("2025-10-24 10:00:00+01:00"),
            end_date=pd.Timestamp("2025-10-24 18:00:00+01:00"),
            headcount=3,
        )
        event2 = Event(
            title="Event 2",
            location="Location",
            start_date=pd.Timestamp("2025-10-24 20:00:00+01:00"),
            end_date=pd.Timestamp("2025-10-25 02:00:00+01:00"),
            headcount=3,
        )
        events = [event1, event2]

        result = self.service._propagate_publication_dates(events)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[1].scheduled_publication_date, result[0].scheduled_publication_date)

    def test_list_events(self) -> None:
        """Test listing all events."""
        expected_events = [self.sample_event]
        self.mock_repo.list_events.return_value = expected_events

        result = self.service.list_events()

        self.assertEqual(result, expected_events)
        self.mock_repo.list_events.assert_called_once()

    def test_mark_published(self) -> None:
        """Test marking event as published."""
        result = self.service.mark_published(self.sample_event, poll_uid="test-poll-123")

        # The service should call upsert_event twice
        self.assertEqual(self.mock_repo.upsert_event.call_count, 2)
        # Optionally, check the arguments for both calls (not used here)
        # Verify the result has published_date set
        self.assertIsNotNone(result.published_date)
        self.assertEqual(result.title, self.sample_event.title)

    def test_increment_reminder(self) -> None:
        """Test incrementing reminder count."""
        result = self.service.increment_reminder(self.sample_event)

        # The service should call increment_reminder on the event and upsert the result
        self.mock_repo.upsert_event.assert_called_once()
        # Verify the result has incremented reminder count
        self.assertEqual(result.nb_reminder, self.sample_event.nb_reminder + 1)
        self.assertEqual(result.title, self.sample_event.title)

    def test_assign_poll_uid(self) -> None:
        """Test assigning poll UID to event."""
        poll_uid = "test-poll-123"
        result = self.service.assign_poll_uid(self.sample_event, poll_uid)

        # The service should call with_poll_uid on the event and upsert the result
        self.mock_repo.upsert_event.assert_called_once()
        # Verify the result has the poll_uid set
        self.assertEqual(result.poll_uid, poll_uid)
        self.assertEqual(result.title, self.sample_event.title)

    def test_find_by_poll_uid(self) -> None:
        """Test finding event by poll UID."""
        poll_id = "test-poll-123"
        self.mock_repo.find_by_poll_uid.return_value = self.sample_event

        result = self.service.find_by_poll_uid(poll_id)

        self.assertEqual(result, self.sample_event)
        self.mock_repo.find_by_poll_uid.assert_called_once_with(poll_id)


if __name__ == "__main__":
    unittest.main()
