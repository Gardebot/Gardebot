"""Unit tests for domain models."""

import hashlib
import unittest

import pandas as pd  # type: ignore[import-untyped]

from gardebot.models.domain import Event, OnDutyAssignment, Sapeur, VoteRecord


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

    def test_sapeur_already_timestamp(self) -> None:
        """Test when joined_date is already a timestamp."""
        sapeur = Sapeur(**self.sapeur_data)
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
        event = Event(**self.event_data)
        poll_string = event.poll_string
        self.assertIn("Emergency Response", poll_string)
        self.assertIn("Station A", poll_string)
        self.assertIn("10h00", poll_string)
        self.assertIn("18h00", poll_string)

    def test_event_poll_string_different_days(self) -> None:
        """Test poll string generation for multi-day event."""
        data = self.event_data.copy()
        data["end_date"] = pd.Timestamp("2023-06-16 18:00:00", tz="Europe/Zurich")
        event = Event(**data)
        poll_string = event.poll_string
        self.assertIn("Emergency Response", poll_string)
        self.assertIn("Station A", poll_string)

    def test_event_timestamp_validation(self) -> None:
        """Test timestamp field validation."""
        data = self.event_data.copy()
        data["start_date"] = "2023-06-15 10:00:00"
        data["end_date"] = "2023-06-15 18:00:00"
        event = Event(**data)
        self.assertIsInstance(event.start_date, pd.Timestamp)
        self.assertIsInstance(event.end_date, pd.Timestamp)

    def test_event_scheduled_publication_date(self) -> None:
        """Test default scheduled publication date."""
        event = Event(**self.event_data)
        self.assertIsNotNone(event.scheduled_publication_date)

    def test_event_should_send_reminder_not_published(self) -> None:
        """Test reminder logic when not published."""
        event = Event(**self.event_data)
        self.assertFalse(event.should_send_reminder())

    def test_event_should_send_reminder_max_reached(self) -> None:
        """Test reminder logic when max reminders reached."""
        data = self.event_data.copy()
        data["nb_reminder"] = 3  # MAX_NB_REMINDER
        data["published_date"] = pd.Timestamp.now(tz="Europe/Zurich")
        event = Event(**data)
        self.assertFalse(event.should_send_reminder())

    def test_event_increment_reminder(self) -> None:
        """Test reminder increment."""
        event = Event(**self.event_data)
        incremented = event.increment_reminder()
        self.assertEqual(incremented.nb_reminder, 1)
        self.assertEqual(event.nb_reminder, 0)  # Original unchanged

    def test_event_mark_published(self) -> None:
        """Test marking event as published."""
        event = Event(**self.event_data)
        published = event.set_published_date()
        self.assertIsNotNone(published.published_date)
        self.assertIsNone(event.published_date)  # Original unchanged

    def test_event_mark_published_with_time(self) -> None:
        """Test marking event as published with specific time."""
        event = Event(**self.event_data)
        specific_time = pd.Timestamp("2023-06-01 12:00:00", tz="Europe/Zurich")
        published = event.set_published_date(specific_time)
        self.assertEqual(published.published_date, specific_time)

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

    def test_event_with_poll_uid_already_set(self) -> None:
        """Test setting poll UID when already set with different value."""
        data = self.event_data.copy()
        data["poll_uid"] = "existing-uid"
        event = Event(**data)
        with self.assertRaises(ValueError):
            event.with_poll_uid("different-uid")

    def test_event_with_poll_uid_same_value(self) -> None:
        """Test setting poll UID when already set with same value."""
        data = self.event_data.copy()
        data["poll_uid"] = "same-uid"
        event = Event(**data)
        with_uid = event.with_poll_uid("same-uid")
        self.assertEqual(with_uid.poll_uid, "same-uid")


class TestVoteRecord(unittest.TestCase):
    """Test VoteRecord model."""

    def setUp(self) -> None:
        """Set up test data."""
        self.sapeur = Sapeur(
            uid="test-uid",
            name="John Doe",
            pushname="Johnny",
            phone="+41123456789",
            joined_date=pd.Timestamp("2023-01-01"),
            group_id="group-123",
        )
        self.event = Event(
            title="Emergency Response",
            location="Station A",
            start_date=pd.Timestamp("2023-06-15 10:00:00", tz="Europe/Zurich"),
            end_date=pd.Timestamp("2023-06-15 18:00:00", tz="Europe/Zurich"),
            headcount=3,
        )

    def test_vote_record_creation(self) -> None:
        """Test VoteRecord creation."""
        vote = VoteRecord(event=self.event, sapeur=self.sapeur, value=True)
        self.assertEqual(vote.event, self.event)
        self.assertEqual(vote.sapeur, self.sapeur)
        self.assertTrue(vote.value)

    def test_vote_record_none_value(self) -> None:
        """Test VoteRecord with None value."""
        vote = VoteRecord(event=self.event, sapeur=self.sapeur, value=None)
        self.assertIsNone(vote.value)

    def test_vote_record_false_value(self) -> None:
        """Test VoteRecord with False value."""
        vote = VoteRecord(event=self.event, sapeur=self.sapeur, value=False)
        self.assertFalse(vote.value)


class TestOnDutyAssignment(unittest.TestCase):
    """Test OnDutyAssignment model."""

    def setUp(self) -> None:
        """Set up test data."""
        self.sapeur1 = Sapeur(
            uid="test-uid-1",
            name="John Doe",
            pushname="Johnny",
            phone="+41123456789",
            joined_date=pd.Timestamp("2023-01-01"),
            group_id="group-123",
        )
        self.sapeur2 = Sapeur(
            uid="test-uid-2",
            name="Jane Smith",
            pushname="Jane",
            phone="+41987654321",
            joined_date=pd.Timestamp("2023-01-01"),
            group_id="group-123",
        )
        self.event = Event(
            title="Emergency Response",
            location="Station A",
            start_date=pd.Timestamp("2023-06-15 10:00:00", tz="Europe/Zurich"),
            end_date=pd.Timestamp("2023-06-15 18:00:00", tz="Europe/Zurich"),
            headcount=2,
        )

    def test_onduty_assignment_creation(self) -> None:
        """Test OnDutyAssignment creation."""
        assignment = OnDutyAssignment(event=self.event, sapeur_list=[self.sapeur1, self.sapeur2], assigned=True)
        self.assertEqual(assignment.event, self.event)
        self.assertEqual(len(assignment.sapeur_list), 2)
        self.assertTrue(assignment.assigned)

    def test_onduty_assignment_default_assigned(self) -> None:
        """Test OnDutyAssignment default assigned value."""
        assignment = OnDutyAssignment(event=self.event, sapeur_list=[self.sapeur1])
        self.assertTrue(assignment.assigned)


if __name__ == "__main__":
    unittest.main()
