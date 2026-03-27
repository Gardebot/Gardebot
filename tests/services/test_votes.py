"""Unit tests for VoteService."""

import unittest
from unittest.mock import Mock, patch

import pandas as pd  # type: ignore[import-untyped]

from gardebot.models.domain import Event, Sapeur, VoteRecord
from gardebot.services.votes import VoteService


class TestVoteService(unittest.TestCase):
    """Test VoteService class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_repo = Mock()
        self.service = VoteService(repository=self.mock_repo)

        self.sample_event = Event(
            title="Test Event",
            location="Test Location",
            start_date=pd.Timestamp("2025-10-24 10:00:00+01:00"),
            end_date=pd.Timestamp("2025-10-24 18:00:00+01:00"),
            headcount=2,
            nb_reminder=0,
        )

        self.sample_sapeurs = [
            Sapeur(uid="uid1", name="John", pushname="John", phone="+41123", joined_date=pd.Timestamp("2025-01-01"), group_id="group1"),
            Sapeur(uid="uid2", name="Jane", pushname="Jane", phone="+41456", joined_date=pd.Timestamp("2025-01-01"), group_id="group1"),
            Sapeur(uid="uid3", name="Bob", pushname="Bob", phone="+41789", joined_date=pd.Timestamp("2025-01-01"), group_id="group1"),
        ]

        self.sample_votes = [
            VoteRecord(event=self.sample_event, sapeur=self.sample_sapeurs[0], value=True),
            VoteRecord(event=self.sample_event, sapeur=self.sample_sapeurs[1], value=False),
            VoteRecord(event=self.sample_event, sapeur=self.sample_sapeurs[2], value=None),
        ]

    def test_init_with_default_repository(self) -> None:
        """Test initialization with default repository."""
        service = VoteService()
        self.assertIsNotNone(service.repo)

    def test_init_with_custom_repository(self) -> None:
        """Test initialization with custom repository."""
        self.assertEqual(self.service.repo, self.mock_repo)

    def test_record_vote(self) -> None:
        """Test recording a vote."""
        vote = self.sample_votes[0]
        self.mock_repo.upsert.return_value = None

        result = self.service.record_vote(vote)

        self.assertEqual(result, vote)
        self.mock_repo.upsert.assert_called_once_with(vote)

    def test_list_present(self) -> None:
        """Test listing sapeurs who voted present."""
        self.mock_repo.list_by_poll.return_value = self.sample_votes

        result = self.service.list_present(self.sample_event)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], self.sample_sapeurs[0])
        self.mock_repo.list_by_poll.assert_called_once_with(self.sample_event)

    def test_list_absent(self) -> None:
        """Test listing sapeurs who voted absent."""
        self.mock_repo.list_by_poll.return_value = self.sample_votes

        result = self.service.list_absent(self.sample_event)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], self.sample_sapeurs[1])
        self.mock_repo.list_by_poll.assert_called_once_with(self.sample_event)

    @patch("gardebot.services.votes.EM_NAME", ["EM"])
    def test_list_non_responding_exclude_em(self) -> None:
        """Test listing non-responding sapeurs excluding EM."""
        # Add EM sapeur to test exclusion
        em_sapeur = Sapeur(
            uid="em_uid", name="EM", pushname="EM", phone="+41000", joined_date=pd.Timestamp("2025-01-01"), group_id="group1"
        )
        votes_with_em = self.sample_votes + [VoteRecord(event=self.sample_event, sapeur=em_sapeur, value=None)]

        self.mock_repo.list_by_poll.return_value = votes_with_em

        result = self.service.list_non_responding(self.sample_event, include_em=False)

        # Should only return Bob (not EM)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], self.sample_sapeurs[2])

    @patch("gardebot.services.votes.EM_NAME", ["EM"])
    def test_list_non_responding_include_em(self) -> None:
        """Test listing non-responding sapeurs including EM."""
        em_sapeur = Sapeur(
            uid="em_uid", name="EM", pushname="EM", phone="+41000", joined_date=pd.Timestamp("2025-01-01"), group_id="group1"
        )
        votes_with_em = self.sample_votes + [VoteRecord(event=self.sample_event, sapeur=em_sapeur, value=None)]

        self.mock_repo.list_by_poll.return_value = votes_with_em

        result = self.service.list_non_responding(self.sample_event, include_em=True)

        # Should return both Bob and EM
        self.assertEqual(len(result), 2)
        names = [s.name for s in result]
        self.assertIn("Bob", names)
        self.assertIn("EM", names)

    def test_test_headcount_reached_true(self) -> None:
        """Test headcount reached returns True."""
        with patch.object(self.service, "list_present", return_value=self.sample_sapeurs[:2]):
            result = self.service.test_headcount_reached(self.sample_event)
            self.assertTrue(result)

    def test_test_headcount_reached_false(self) -> None:
        """Test headcount reached returns False."""
        with patch.object(self.service, "list_present", return_value=self.sample_sapeurs[:1]):
            result = self.service.test_headcount_reached(self.sample_event)
            self.assertFalse(result)

    def test_test_all_responded_true(self) -> None:
        """Test all responded returns True."""
        with patch.object(self.service, "list_non_responding", return_value=[]):
            result = self.service.test_all_responded(self.sample_event)
            self.assertTrue(result)

    def test_test_all_responded_false(self) -> None:
        """Test all responded returns False."""
        with patch.object(self.service, "list_non_responding", return_value=[self.sample_sapeurs[0]]):
            result = self.service.test_all_responded(self.sample_event)
            self.assertFalse(result)

    @patch("gardebot.services.votes.MAX_NB_REMINDER", 3)
    def test_test_max_reminders_true(self) -> None:
        """Test max reminders reached returns True."""
        event_with_max_reminders = Event(
            title="Test Event",
            location="Test Location",
            start_date=pd.Timestamp("2025-10-24 10:00:00+01:00"),
            end_date=pd.Timestamp("2025-10-24 18:00:00+01:00"),
            headcount=2,
            nb_reminder=3,
        )

        result = self.service.test_max_reminders(event_with_max_reminders)
        self.assertTrue(result)

    @patch("gardebot.services.votes.MAX_NB_REMINDER", 3)
    def test_test_max_reminders_false(self) -> None:
        """Test max reminders reached returns False."""
        result = self.service.test_max_reminders(self.sample_event)
        self.assertFalse(result)

    def test_test_event_completion_headcount_reached(self) -> None:
        """Test event completion when headcount is reached."""
        with (
            patch.object(self.service, "test_headcount_reached", return_value=True),
            patch.object(self.service, "test_all_responded", return_value=False),
            patch.object(self.service, "test_max_reminders", return_value=False),
        ):
            result = self.service.test_event_completion(self.sample_event)
            self.assertTrue(result)

    def test_test_event_completion_all_responded(self) -> None:
        """Test event completion when all responded."""
        with (
            patch.object(self.service, "test_headcount_reached", return_value=False),
            patch.object(self.service, "test_all_responded", return_value=True),
            patch.object(self.service, "test_max_reminders", return_value=False),
        ):
            result = self.service.test_event_completion(self.sample_event)
            self.assertTrue(result)

    def test_test_event_completion_max_reminders(self) -> None:
        """Test event completion when max reminders reached."""
        with (
            patch.object(self.service, "test_headcount_reached", return_value=False),
            patch.object(self.service, "test_all_responded", return_value=False),
            patch.object(self.service, "test_max_reminders", return_value=True),
        ):
            result = self.service.test_event_completion(self.sample_event)
            self.assertTrue(result)

    def test_test_event_completion_false(self) -> None:
        """Test event completion returns False when no conditions met."""
        with (
            patch.object(self.service, "test_headcount_reached", return_value=False),
            patch.object(self.service, "test_all_responded", return_value=False),
            patch.object(self.service, "test_max_reminders", return_value=False),
        ):
            result = self.service.test_event_completion(self.sample_event)
            self.assertFalse(result)

    def test_get_vote_df(self) -> None:
        """Test get_vote_df wrapper."""
        expected_df = pd.DataFrame({"test": [1, 2, 3]})
        self.mock_repo.get_vote_df.return_value = expected_df

        result = self.service.get_vote_df(event_list=[self.sample_event], sapeur_list=self.sample_sapeurs)

        pd.testing.assert_frame_equal(result, expected_df)
        self.mock_repo.get_vote_df.assert_called_once_with(event_list=[self.sample_event], sapeur_list=self.sample_sapeurs)

    def test_create(self) -> None:
        """Test create method wrapper."""
        self.service.create(overwrite=True)
        self.mock_repo.create.assert_called_once_with(overwrite=True)


if __name__ == "__main__":
    unittest.main()
