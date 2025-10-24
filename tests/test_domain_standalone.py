"""Standalone test for domain models."""

import hashlib
import sys
import unittest
from typing import Any
from unittest.mock import patch

# Mock problematic dependencies
sys.modules["dopplersdk"] = type(sys)("dopplersdk")
sys.modules["dopplersdk.DopplerSDK"] = type(sys)("DopplerSDK")

import pandas as pd  # type: ignore[import-untyped]


# Mock common module to avoid doppler dependency
class MockCommon:
    @staticmethod
    def _format_french_date(date: Any) -> Any:
        return date.strftime("%d/%m/%Y")


sys.modules["gardebot.common.common"] = MockCommon()  # type: ignore[assignment]

from gardebot.models.domain import Event, Sapeur


class TestSapeur(unittest.TestCase):
    """Test Sapeur model."""

    def setUp(self) -> None:
        """Set up test data."""
        self.sapeur_data = {
            "uid": "test-uid",
            "name": "John Doe",
            "pushname": "Johnny",
            "phone": "+41123456789",
            "joined_date": pd.Timestamp("2023-01-01"),
            "group_id": "group-123",
        }

    def test_sapeur_creation(self) -> None:
        """Test Sapeur model creation."""
        sapeur = Sapeur(**self.sapeur_data)
        self.assertEqual(sapeur.uid, "test-uid")
        self.assertEqual(sapeur.name, "John Doe")
        self.assertEqual(sapeur.pushname, "Johnny")
        self.assertEqual(sapeur.phone, "+41123456789")
        self.assertEqual(sapeur.group_id, "group-123")
        self.assertIsInstance(sapeur.joined_date, pd.Timestamp)

    def test_sapeur_timestamp_validation(self) -> None:
        """Test timestamp field validation."""
        data = self.sapeur_data.copy()
        data["joined_date"] = "2023-01-01"
        sapeur = Sapeur(**data)
        self.assertIsInstance(sapeur.joined_date, pd.Timestamp)


class TestEvent(unittest.TestCase):
    """Test Event model."""

    def setUp(self) -> None:
        """Set up test data."""
        self.event_data = {
            "title": "Emergency Response",
            "location": "Station A",
            "start_date": pd.Timestamp("2023-06-15 10:00:00", tz="Europe/Zurich"),
            "end_date": pd.Timestamp("2023-06-15 18:00:00", tz="Europe/Zurich"),
            "headcount": 3,
        }

    def test_event_creation(self) -> None:
        """Test Event model creation."""
        event = Event(**self.event_data)
        self.assertEqual(event.title, "Emergency Response")
        self.assertEqual(event.location, "Station A")
        self.assertEqual(event.headcount, 3)
        self.assertIsNone(event.poll_uid)
        self.assertIsNone(event.published_date)
        self.assertEqual(event.nb_reminder, 0)

    def test_event_uid_generation(self) -> None:
        """Test UID generation."""
        event = Event(**self.event_data)
        expected_base = f"{event.title}{event.location}{event.start_date}{event.end_date}"
        expected_uid = hashlib.sha256(expected_base.encode()).hexdigest()
        self.assertEqual(event.uid, expected_uid)

    def test_event_poll_string_same_day(self) -> None:
        """Test poll string generation for same day event."""
        with patch("gardebot.common.common._format_french_date", return_value="15/06/2023"):
            event = Event(**self.event_data)
            poll_string = event.poll_string
            self.assertIn("Emergency Response", poll_string)
            self.assertIn("Station A", poll_string)
            self.assertIn("10h00", poll_string)
            self.assertIn("18h00", poll_string)

    def test_event_increment_reminder(self) -> None:
        """Test reminder increment."""
        event = Event(**self.event_data)
        incremented = event.increment_reminder()
        self.assertEqual(incremented.nb_reminder, 1)
        self.assertEqual(event.nb_reminder, 0)

    def test_event_mark_published(self) -> None:
        """Test marking event as published."""
        event = Event(**self.event_data)
        published = event.set_published_date()
        self.assertIsNotNone(published.published_date)
        self.assertIsNone(event.published_date)

    def test_event_is_published(self) -> None:
        """Test published status check."""
        event = Event(**self.event_data)
        self.assertFalse(event.is_published())
        published = event.set_published_date()
        published = published.with_poll_uid("poll-123")
        self.assertTrue(published.is_published())

    def test_event_with_poll_uid(self) -> None:
        """Test setting poll UID."""
        event = Event(**self.event_data)
        with_uid = event.with_poll_uid("poll-123")
        self.assertEqual(with_uid.poll_uid, "poll-123")

    def test_event_with_poll_uid_already_set_different(self) -> None:
        """Test setting poll UID when already set with different value."""
        data = self.event_data.copy()
        data["poll_uid"] = "existing-uid"
        event = Event(**data)
        with self.assertRaises(ValueError):
            event.with_poll_uid("different-uid")


if __name__ == "__main__":
    unittest.main()
