# mypy: disable-error-code="method-assign, attr-defined"
"""Unit tests for repositories."""

import unittest
from unittest.mock import Mock

import pandas as pd  # type: ignore[import-untyped]

from gardebot.errors import NotFoundError
from gardebot.models.domain import Event, OnDutyAssignment, Sapeur, VoteRecord
from gardebot.repositories import EventRepository, OnDutyRepository, SapeurRepository, VoteRepository


class TestEventRepository(unittest.TestCase):
    """Test EventRepository class."""

    def setUp(self) -> None:
        """Set up test repository."""
        self.mock_storage = Mock()
        self.repo = EventRepository(storage=self.mock_storage)

        self.sample_event = Event(
            title="Test Event",
            location="Test Location",
            start_date=pd.Timestamp("2023-06-15 10:00:00", tz="Europe/Zurich"),
            end_date=pd.Timestamp("2023-06-15 18:00:00", tz="Europe/Zurich"),
            headcount=2,
        )

    def test_create_empty_storage(self) -> None:
        """Test creating empty storage."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        self.repo.create(overwrite=True)

        self.mock_storage.atomic_write.assert_called_once()
        args = self.mock_storage.atomic_write.call_args[0]
        self.assertIsInstance(args[0], pd.DataFrame)
        self.assertTrue(args[0].empty)

    def test_create_existing_storage(self) -> None:
        """Test creating storage when data exists."""
        existing_df = pd.DataFrame([{"uid": "test", "title": "Test"}])
        self.mock_storage.read_parquet.return_value = existing_df

        self.repo.create(overwrite=False)

        self.mock_storage.atomic_write.assert_not_called()

    def test_list_events_empty(self) -> None:
        """Test listing events when storage is empty."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        events = self.repo.list_events()

        self.assertEqual(events, [])

    def test_list_events_with_data(self) -> None:
        """Test listing events with data."""
        event_data = self.sample_event.model_dump()
        df = pd.DataFrame([event_data])
        self.mock_storage.read_parquet.return_value = df

        events = self.repo.list_events()

        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], Event)
        self.assertEqual(events[0].title, "Test Event")

    def test_upsert_event_new(self) -> None:
        """Test upserting a new event."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        self.repo.upsert_event(self.sample_event)

        self.mock_storage.atomic_write.assert_called_once()

    def test_upsert_event_existing(self) -> None:
        """Test upserting an existing event."""
        event_data = self.sample_event.model_dump()
        df = pd.DataFrame([event_data])
        self.mock_storage.read_parquet.return_value = df

        updated_event = self.sample_event.model_copy(update={"title": "Updated Title"})
        self.repo.upsert_event(updated_event)

        self.mock_storage.atomic_write.assert_called_once()

    def test_bulk_upsert_new_events(self) -> None:
        """Test bulk upsert with new events."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        events = [self.sample_event]
        self.repo.bulk_upsert(events)

        self.mock_storage.atomic_write.assert_called_once()

    def test_bulk_upsert_no_new_events(self) -> None:
        """Test bulk upsert with no new events."""
        event_data = self.sample_event.model_dump()
        df = pd.DataFrame([event_data])
        self.mock_storage.read_parquet.return_value = df

        events = [self.sample_event]  # Same event
        self.repo.bulk_upsert(events)

        self.mock_storage.atomic_write.assert_not_called()

    def test_find_by_uid_found(self) -> None:
        """Test finding event by UID when found."""
        event_data = self.sample_event.model_dump()
        df = pd.DataFrame([event_data])
        self.mock_storage.read_parquet.return_value = df

        found_event = self.repo.find_by_uid(self.sample_event.uid)

        self.assertEqual(found_event.uid, self.sample_event.uid)

    def test_find_by_uid_not_found(self) -> None:
        """Test finding event by UID when not found."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        with self.assertRaises(NotFoundError):
            self.repo.find_by_uid("nonexistent-uid")

    def test_find_by_poll_string_found(self) -> None:
        """Test finding event by poll string when found."""
        event_data = self.sample_event.model_dump()
        df = pd.DataFrame([event_data])
        self.mock_storage.read_parquet.return_value = df

        found_event = self.repo.find_by_poll_string(self.sample_event.poll_string)

        self.assertEqual(found_event.poll_string, self.sample_event.poll_string)

    def test_find_by_poll_string_not_found(self) -> None:
        """Test finding event by poll string when not found."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        with self.assertRaises(NotFoundError):
            self.repo.find_by_poll_string("nonexistent-poll")

    def test_find_by_poll_uid_found(self) -> None:
        """Test finding event by poll UID when found."""
        event_with_poll = self.sample_event.with_poll_uid("poll-123")
        event_data = event_with_poll.model_dump()
        df = pd.DataFrame([event_data])
        self.mock_storage.read_parquet.return_value = df

        found_event = self.repo.find_by_poll_uid("poll-123")

        self.assertEqual(found_event.poll_uid, "poll-123")

    def test_find_by_poll_uid_not_found(self) -> None:
        """Test finding event by poll UID when not found."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        with self.assertRaises(NotFoundError):
            self.repo.find_by_poll_uid("nonexistent-poll-uid")


class TestSapeurRepository(unittest.TestCase):
    """Test SapeurRepository class."""

    def setUp(self) -> None:
        """Set up test repository."""
        self.mock_storage = Mock()
        self.repo = SapeurRepository(storage=self.mock_storage)

        self.sample_sapeur = Sapeur(
            uid="test-uid",
            name="John Doe",
            pushname="Johnny",
            phone="+41123456789",
            joined_date=pd.Timestamp("2023-01-01"),
            group_id="group-123",
        )

    def test_list_sapeurs_empty(self) -> None:
        """Test listing sapeurs when storage is empty."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        sapeurs = self.repo.list_sapeurs()

        self.assertEqual(sapeurs, [])

    def test_list_sapeurs_with_data(self) -> None:
        """Test listing sapeurs with data."""
        sapeur_data = self.sample_sapeur.model_dump()
        df = pd.DataFrame([sapeur_data])
        self.mock_storage.read_parquet.return_value = df

        sapeurs = self.repo.list_sapeurs()

        self.assertEqual(len(sapeurs), 1)
        self.assertIsInstance(sapeurs[0], Sapeur)
        self.assertEqual(sapeurs[0].name, "John Doe")

    def test_upsert_new_sapeur(self) -> None:
        """Test upserting a new sapeur."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        self.repo.upsert(self.sample_sapeur)

        self.mock_storage.atomic_write.assert_called_once()

    def test_upsert_existing_sapeur(self) -> None:
        """Test upserting an existing sapeur."""
        sapeur_data = self.sample_sapeur.model_dump()
        df = pd.DataFrame([sapeur_data])
        self.mock_storage.read_parquet.return_value = df

        self.repo.upsert(self.sample_sapeur)

        self.mock_storage.atomic_write.assert_not_called()

    def test_bulk_upsert_new_sapeurs(self) -> None:
        """Test bulk upsert with new sapeurs."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        sapeurs = [self.sample_sapeur]
        self.repo.bulk_upsert(sapeurs)

        self.mock_storage.atomic_write.assert_called_once()

    def test_bulk_upsert_no_new_sapeurs(self) -> None:
        """Test bulk upsert with no new sapeurs."""
        sapeur_data = self.sample_sapeur.model_dump()
        df = pd.DataFrame([sapeur_data])
        self.mock_storage.read_parquet.return_value = df

        sapeurs = [self.sample_sapeur]  # Same sapeur
        self.repo.bulk_upsert(sapeurs)

        self.mock_storage.atomic_write.assert_not_called()

    def test_delete_sapeur(self) -> None:
        """Test deleting a sapeur."""
        sapeur_data = self.sample_sapeur.model_dump()
        df = pd.DataFrame([sapeur_data])
        self.mock_storage.read_parquet.return_value = df

        self.repo.delete(self.sample_sapeur)

        self.mock_storage.atomic_write.assert_called_once()

    def test_bulk_delete_sapeurs(self) -> None:
        """Test bulk delete sapeurs."""
        sapeur_data = self.sample_sapeur.model_dump()
        df = pd.DataFrame([sapeur_data])
        self.mock_storage.read_parquet.return_value = df

        sapeurs = [self.sample_sapeur]
        self.repo.bulk_delete(sapeurs)

        self.mock_storage.atomic_write.assert_called_once()

    def test_find_by_name_found(self) -> None:
        """Test finding sapeur by name when found."""
        sapeur_data = self.sample_sapeur.model_dump()
        df = pd.DataFrame([sapeur_data])
        self.mock_storage.read_parquet.return_value = df

        found_sapeur = self.repo.find_by_name("John Doe")

        self.assertEqual(found_sapeur.name, "John Doe")

    def test_find_by_name_not_found(self) -> None:
        """Test finding sapeur by name when not found."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        with self.assertRaises(NotFoundError):
            self.repo.find_by_name("Nonexistent Name")

    def test_find_by_uid_found(self) -> None:
        """Test finding sapeur by UID when found."""
        sapeur_data = self.sample_sapeur.model_dump()
        df = pd.DataFrame([sapeur_data])
        self.mock_storage.read_parquet.return_value = df

        found_sapeur = self.repo.find_by_uid("test-uid")

        self.assertEqual(found_sapeur.uid, "test-uid")

    def test_find_by_uid_not_found(self) -> None:
        """Test finding sapeur by UID when not found."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        with self.assertRaises(NotFoundError):
            self.repo.find_by_uid("nonexistent-uid")


class TestVoteRepository(unittest.TestCase):
    """Test VoteRepository class."""

    def setUp(self) -> None:
        """Set up test repository."""
        self.mock_storage = Mock()
        self.mock_sapeur_repo = Mock()
        self.mock_events_repo = Mock()

        self.repo = VoteRepository(storage=self.mock_storage)
        self.repo.sapeur_repository = self.mock_sapeur_repo
        self.repo.events_repository = self.mock_events_repo

        self.sample_sapeur = Sapeur(
            uid="test-uid",
            name="John Doe",
            pushname="Johnny",
            phone="+41123456789",
            joined_date=pd.Timestamp("2023-01-01"),
            group_id="group-123",
        )

        self.sample_event = Event(
            title="Test Event",
            location="Test Location",
            start_date=pd.Timestamp("2023-06-15 10:00:00", tz="Europe/Zurich"),
            end_date=pd.Timestamp("2023-06-15 18:00:00", tz="Europe/Zurich"),
            headcount=2,
        )

    def test_create_empty_storage(self) -> None:
        """Test creating empty vote storage."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()
        self.mock_events_repo.list_events.return_value = [self.sample_event]
        self.mock_sapeur_repo.list_sapeurs.return_value = [self.sample_sapeur]

        self.repo.create(overwrite=True)

        self.mock_storage.atomic_write.assert_called_once()

    def test_list_votes_empty(self) -> None:
        """Test listing votes when storage is empty."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        votes = self.repo.list_votes()

        self.assertEqual(votes, [])

    def test_list_votes_with_data(self) -> None:
        """Test listing votes with data."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [True]}, index=["John Doe"])
        self.mock_storage.read_parquet.return_value = df
        self.mock_events_repo.find_by_poll_string.return_value = self.sample_event
        self.mock_sapeur_repo.find_by_name.return_value = self.sample_sapeur

        votes = self.repo.list_votes()

        self.assertEqual(len(votes), 1)
        self.assertIsInstance(votes[0], VoteRecord)
        self.assertTrue(votes[0].value)

    def test_upsert_vote(self) -> None:
        """Test upserting a vote."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [None]}, index=["John Doe"])
        self.mock_storage.read_parquet.return_value = df

        vote = VoteRecord(event=self.sample_event, sapeur=self.sample_sapeur, value=True)
        self.repo.upsert(vote)

        self.mock_storage.atomic_write.assert_called_once()

    def test_list_by_poll(self) -> None:
        """Test listing votes by poll."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [True]}, index=["John Doe"])
        self.mock_storage.read_parquet.return_value = df
        self.mock_events_repo.find_by_poll_string.return_value = self.sample_event
        self.mock_sapeur_repo.find_by_name.return_value = self.sample_sapeur

        votes = self.repo.list_by_poll(self.sample_event)

        self.assertEqual(len(votes), 1)
        self.assertEqual(votes[0].event.poll_string, poll_string)

    def test_get_vote_df(self) -> None:
        """Test getting vote dataframe."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [True]}, index=["John Doe"])
        self.mock_storage.read_parquet.return_value = df

        result_df = self.repo.get_vote_df()

        self.assertIsInstance(result_df, pd.DataFrame)

    def test_get_vote_df_filtered(self) -> None:
        """Test getting filtered vote dataframe."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [True], "other_poll": [False]}, index=["John Doe", "Jane Smith"])
        self.mock_storage.read_parquet.return_value = df

        result_df = self.repo.get_vote_df(event_list=[self.sample_event], sapeur_list=[self.sample_sapeur])

        self.assertIsInstance(result_df, pd.DataFrame)


class TestOnDutyRepository(unittest.TestCase):
    """Test OnDutyRepository class."""

    def setUp(self) -> None:
        """Set up test repository."""
        self.mock_storage = Mock()
        self.mock_events_repo = Mock()
        self.mock_sapeur_repo = Mock()

        self.repo = OnDutyRepository(storage=self.mock_storage)
        self.repo.events_repository = self.mock_events_repo
        self.repo.sapeur_repository = self.mock_sapeur_repo

        self.sample_sapeur = Sapeur(
            uid="test-uid",
            name="John Doe",
            pushname="Johnny",
            phone="+41123456789",
            joined_date=pd.Timestamp("2023-01-01"),
            group_id="group-123",
        )

        self.sample_event = Event(
            title="Test Event",
            location="Test Location",
            start_date=pd.Timestamp("2023-06-15 10:00:00", tz="Europe/Zurich"),
            end_date=pd.Timestamp("2023-06-15 18:00:00", tz="Europe/Zurich"),
            headcount=2,
        )

    def test_create_empty_storage(self) -> None:
        """Test creating empty on-duty storage."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()
        self.mock_events_repo.list_events.return_value = [self.sample_event]
        self.mock_sapeur_repo.list_sapeurs.return_value = [self.sample_sapeur]

        self.repo.create(overwrite=True)

        self.mock_storage.atomic_write.assert_called_once()

    def test_list_assignments_empty(self) -> None:
        """Test listing assignments when storage is empty."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        assignments = self.repo.list_assignments()

        self.assertEqual(assignments, [])

    def test_list_assignments_with_data(self) -> None:
        """Test listing assignments with data."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [True, False]}, index=["John Doe", "Jane Smith"])
        self.mock_storage.read_parquet.return_value = df
        self.mock_sapeur_repo.find_by_name.return_value = self.sample_sapeur
        self.mock_events_repo.find_by_poll_string.return_value = self.sample_event

        assignments = self.repo.list_assignments()

        self.assertEqual(len(assignments), 1)
        self.assertIsInstance(assignments[0], OnDutyAssignment)

    def test_write_assignment(self) -> None:
        """Test writing an assignment."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [False]}, index=["John Doe"])
        self.mock_storage.read_parquet.return_value = df

        assignment = OnDutyAssignment(event=self.sample_event, sapeur_list=[self.sample_sapeur])
        self.repo.write_assignment(assignment)

        self.mock_storage.atomic_write.assert_called_once()

    def test_list_assigned_sapeur(self) -> None:
        """Test listing assigned sapeurs."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [True]}, index=["John Doe"])
        self.mock_storage.read_parquet.return_value = df
        self.mock_sapeur_repo.find_by_name.return_value = self.sample_sapeur

        assignment = OnDutyAssignment(event=self.sample_event, sapeur_list=[self.sample_sapeur])
        assigned = self.repo.list_assigned_sapeur(assignment)

        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned[0], self.sample_sapeur)

    def test_list_assigned_sapeur_missing_event(self) -> None:
        """Test listing assigned sapeurs for missing event."""
        df = pd.DataFrame({"other_poll": [True]}, index=["John Doe"])
        self.mock_storage.read_parquet.return_value = df

        assignment = OnDutyAssignment(event=self.sample_event, sapeur_list=[self.sample_sapeur])
        assigned = self.repo.list_assigned_sapeur(assignment)

        self.assertEqual(assigned, [])

    def test_is_assigned_true(self) -> None:
        """Test is_assigned returns True when headcount is met."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [True, True]}, index=["John Doe", "Jane Smith"])
        self.mock_storage.read_parquet.return_value = df

        result = self.repo.is_assigned(self.sample_event)

        self.assertTrue(result)

    def test_is_assigned_false(self) -> None:
        """Test is_assigned returns False when headcount is not met."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [True]}, index=["John Doe"])
        self.mock_storage.read_parquet.return_value = df

        result = self.repo.is_assigned(self.sample_event)

        self.assertFalse(result)

    def test_is_assigned_empty_storage(self) -> None:
        """Test is_assigned with empty storage."""
        self.mock_storage.read_parquet.return_value = pd.DataFrame()

        result = self.repo.is_assigned(self.sample_event)

        self.assertFalse(result)

    def test_get_onduty_df(self) -> None:
        """Test getting on-duty dataframe."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [True]}, index=["John Doe"])
        self.mock_storage.read_parquet.return_value = df

        result_df = self.repo.get_onduty_df()

        self.assertIsInstance(result_df, pd.DataFrame)

    def test_get_onduty_df_filtered(self) -> None:
        """Test getting filtered on-duty dataframe."""
        poll_string = self.sample_event.poll_string
        df = pd.DataFrame({poll_string: [True], "other_poll": [False]}, index=["John Doe", "Jane Smith"])
        self.mock_storage.read_parquet.return_value = df

        result_df = self.repo.get_onduty_df(event_list=[self.sample_event], sapeur_list=[self.sample_sapeur])

        self.assertIsInstance(result_df, pd.DataFrame)

    def test_list_sapeurs(self) -> None:
        """Test listing sapeurs wrapper."""
        self.mock_sapeur_repo.list_sapeurs.return_value = [self.sample_sapeur]

        sapeurs = self.repo.list_sapeurs()

        self.assertEqual(sapeurs, [self.sample_sapeur])
        self.mock_sapeur_repo.list_sapeurs.assert_called_once()


if __name__ == "__main__":
    unittest.main()
