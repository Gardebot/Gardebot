# mypy: disable-error-code="method-assign, attr-defined"
"""Unit tests for OnDutyService."""

import unittest
from unittest.mock import Mock, patch

import pandas as pd  # type: ignore[import-untyped]

from gardebot.errors import AlreadyAssignedError
from gardebot.models.domain import Event, OnDutyAssignment, Sapeur
from gardebot.services.onduty import OnDutyService


class TestOnDutyService(unittest.TestCase):
    """Test OnDutyService class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_repo = Mock()
        self.mock_vote_service = Mock()
        self.service = OnDutyService(on_duty_repos=self.mock_repo, vote_service=self.mock_vote_service)

        self.sample_event = Event(
            title="Test Event",
            location="Test Location",
            start_date=pd.Timestamp("2025-10-24 10:00:00+01:00"),
            end_date=pd.Timestamp("2025-10-24 18:00:00+01:00"),
            headcount=2,
        )

        self.sample_sapeurs = [
            Sapeur(uid="uid1", name="John", pushname="John", phone="+41123", joined_date=pd.Timestamp("2025-01-01"), group_id="group1"),
            Sapeur(uid="uid2", name="Jane", pushname="Jane", phone="+41456", joined_date=pd.Timestamp("2025-01-01"), group_id="group1"),
        ]

    def test_init_with_defaults(self) -> None:
        """Test initialization with default repositories."""
        service = OnDutyService()
        self.assertIsNotNone(service.on_duty_repos)
        self.assertIsNotNone(service.vote_service)

    def test_is_assigned_true(self) -> None:
        """Test is_assigned returns True when assignment exists."""
        self.mock_repo.is_assigned.return_value = True
        result = self.service.is_assigned(self.sample_event)
        self.assertTrue(result)
        self.mock_repo.is_assigned.assert_called_once_with(self.sample_event)

    def test_is_assigned_false(self) -> None:
        """Test is_assigned returns False when no assignment exists."""
        self.mock_repo.is_assigned.return_value = False
        result = self.service.is_assigned(self.sample_event)
        self.assertFalse(result)

    def test_list_assigned_events(self) -> None:
        """Test listing assigned events."""
        assigned = OnDutyAssignment(event=self.sample_event, sapeur_list=self.sample_sapeurs, assigned=True)
        unassigned = OnDutyAssignment(event=self.sample_event, sapeur_list=[], assigned=False)
        self.mock_repo.list_assignments.return_value = [assigned, unassigned]

        result = self.service.list_assigned_events()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], assigned)

    def test_assign(self) -> None:
        """Test private _assign method."""
        self.mock_repo.write_assignment.return_value = None

        result = self.service._assign(self.sample_event, self.sample_sapeurs)

        self.assertIsInstance(result, OnDutyAssignment)
        self.assertEqual(result.event, self.sample_event)
        self.assertEqual(result.sapeur_list, self.sample_sapeurs)
        self.assertTrue(result.assigned)
        self.mock_repo.write_assignment.assert_called_once()

    def test_vote_score_pro_sapeur(self) -> None:
        """Test vote scoring for sapeurs."""
        poll_string = self.sample_event.poll_string
        vote_df = pd.DataFrame({poll_string: [True, False, None]}, index=["John", "Jane", "Bob"])
        self.mock_vote_service.get_vote_df.return_value = vote_df

        result = self.service._vote_score_pro_sapeur(self.sample_event)

        expected = pd.Series([1, 1, 0], index=["John", "Jane", "Bob"], name=poll_string)
        pd.testing.assert_series_equal(result, expected)

    def test_assignment_score_pro_sapeur_no_events(self) -> None:
        """Test assignment scoring with no previous events."""
        self.service.list_assigned_events = Mock(return_value=[])
        onduty_df = pd.DataFrame(index=["John", "Jane"])
        self.mock_repo.get_onduty_df.return_value = onduty_df

        result = self.service._assignment_score_pro_sapeur()

        expected = pd.Series([0, 0], index=["John", "Jane"])
        pd.testing.assert_series_equal(result, expected)

    def test_assignment_score_pro_sapeur_with_events(self) -> None:
        """Test assignment scoring with previous events."""
        self.service.list_assigned_events = Mock(return_value=[Mock()])
        onduty_df = pd.DataFrame({"event1": [1, 0], "event2": [0, 1]}, index=["John", "Jane"])
        self.mock_repo.get_onduty_df.return_value = onduty_df

        result = self.service._assignment_score_pro_sapeur()

        expected = pd.Series([0.5, 0.5], index=["John", "Jane"])
        pd.testing.assert_series_equal(result, expected)

    def test_score_pro_sapeur(self) -> None:
        """Test overall scoring for sapeurs."""
        with (
            patch.object(self.service, "_vote_score_pro_sapeur") as mock_vote,
            patch.object(self.service, "_assignment_score_pro_sapeur") as mock_assign,
        ):
            mock_vote.return_value = pd.Series([1, 0], index=["John", "Jane"])
            mock_assign.return_value = pd.Series([0, 1], index=["John", "Jane"])

            result = self.service._score_pro_sapeur(self.sample_event)

            expected = pd.Series([0.5, 0.5], index=["John", "Jane"])
            pd.testing.assert_series_equal(result, expected)

    def test_process_assignment_already_assigned(self) -> None:
        """Test process assignment when event already assigned."""
        with patch.object(self.service, "is_assigned", return_value=True):
            with self.assertRaises(AlreadyAssignedError):
                self.service.process_assignment(self.sample_event)

    def test_process_assignment_headcount_reached(self) -> None:
        """Test process assignment when headcount is reached."""
        with (
            patch.object(self.service, "is_assigned", return_value=False),
            patch.object(self.service, "_assign_within_volunteers") as mock_assign,
        ):
            assignment = OnDutyAssignment(event=self.sample_event, sapeur_list=self.sample_sapeurs, assigned=True)
            self.mock_vote_service.test_headcount_reached.return_value = True
            mock_assign.return_value = assignment

            result = self.service.process_assignment(self.sample_event)

            mock_assign.assert_called_once_with(self.sample_event)
            self.assertEqual(result, assignment)

    def test_process_assignment_headcount_not_reached(self) -> None:
        """Test process assignment when headcount not reached."""
        with patch.object(self.service, "is_assigned", return_value=False), patch.object(self.service, "_assign_among_all") as mock_assign:
            assignment = OnDutyAssignment(event=self.sample_event, sapeur_list=self.sample_sapeurs, assigned=True)
            self.mock_vote_service.test_headcount_reached.return_value = False
            mock_assign.return_value = assignment

            result = self.service.process_assignment(self.sample_event)

            mock_assign.assert_called_once_with(self.sample_event)
            self.assertEqual(result, assignment)

    def test_assign_within_volunteers_no_present(self) -> None:
        """Test assignment within volunteers when none present."""
        self.mock_vote_service.list_present.return_value = []

        result = self.service._assign_within_volunteers(self.sample_event)

        self.assertFalse(result.assigned)
        self.assertEqual(len(result.sapeur_list), 0)

    def test_assign_within_volunteers_exact_headcount(self) -> None:
        """Test assignment when present sapeurs equal headcount."""
        self.mock_vote_service.list_present.return_value = self.sample_sapeurs

        with patch.object(self.service, "_assign") as mock_assign:
            mock_assign.return_value = Mock()
            # Call the method to trigger the assignment
            self.service._assign_within_volunteers(self.sample_event)
            mock_assign.assert_called_once_with(event=self.sample_event, sapeurs=self.sample_sapeurs)

    def test_assign_within_volunteers_more_than_needed(self) -> None:
        """Test assignment when more sapeurs present than needed."""
        extra_sapeur = Sapeur(
            uid="uid3", name="Bob", pushname="Bob", phone="+41789", joined_date=pd.Timestamp("2025-01-01"), group_id="group1"
        )
        all_present = self.sample_sapeurs + [extra_sapeur]
        self.mock_vote_service.list_present.return_value = all_present

        with patch.object(self.service, "_assignment_score_pro_sapeur") as mock_score, patch.object(self.service, "_assign") as mock_assign:
            # Lower scores get selected first
            mock_score.return_value = pd.Series([0.1, 0.3, 0.2], index=["John", "Jane", "Bob"])
            mock_assign.return_value = Mock()
            # Call the method to trigger the assignment
            self.service._assign_within_volunteers(self.sample_event)
            # Should select John (0.1) and Bob (0.2)
            called_sapeurs = mock_assign.call_args.kwargs["sapeurs"]
            called_names = [s.name for s in called_sapeurs]
            self.assertIn("John", called_names)
            self.assertIn("Bob", called_names)
            self.assertEqual(len(called_sapeurs), 2)

    @patch("gardebot.services.onduty.EM_NAME", ["EM"])
    def test_assign_among_all(self) -> None:
        """Test assignment among all sapeurs."""
        present_sapeurs = [self.sample_sapeurs[0]]  # John is present
        all_sapeurs = self.sample_sapeurs + [
            Sapeur(uid="uid3", name="Bob", pushname="Bob", phone="+41789", joined_date=pd.Timestamp("2025-01-01"), group_id="group1")
        ]

        self.mock_vote_service.list_present.return_value = present_sapeurs
        self.mock_repo.list_sapeurs.return_value = all_sapeurs

        with patch.object(self.service, "_score_pro_sapeur") as mock_score, patch.object(self.service, "_assign") as mock_assign:
            assignment = OnDutyAssignment(event=self.sample_event, sapeur_list=present_sapeurs + [self.sample_sapeurs[1]], assigned=True)
            # Bob has lowest score, should be selected (Jane is index 1, Bob is the added one)
            mock_score.return_value = pd.Series([0.1], index=["Bob"])  # Only Bob is pending
            mock_assign.return_value = assignment
            # Call the method to trigger the assignment
            self.service._assign_among_all(self.sample_event)
            # Should assign John (present) + Bob (lowest score among pending)
            called_sapeurs = mock_assign.call_args.kwargs["sapeurs"]
            called_names = [s.name for s in called_sapeurs]
            self.assertIn("John", called_names)
            self.assertEqual(len(called_sapeurs), 2)
            self.assertIn("John", called_names)
            self.assertEqual(len(called_sapeurs), 2)

    def test_create(self) -> None:
        """Test create method wrapper."""
        self.service.create(overwrite=True)
        self.mock_repo.create.assert_called_once_with(overwrite=True)


if __name__ == "__main__":
    unittest.main()
