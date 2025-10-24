"""Unit tests for SapeurService."""

import unittest
from unittest.mock import Mock, patch

import pandas as pd  # type: ignore[import-untyped]

from gardebot.models.domain import Sapeur
from gardebot.services.sapeur import SapeurService


class TestSapeurService(unittest.TestCase):
    """Test SapeurService class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_repo = Mock()
        with patch("gardebot.services.sapeur.GroupService"):
            self.service = SapeurService(repository=self.mock_repo)

        self.mock_group_service = Mock()
        self.service.group_service = self.mock_group_service

        self.sample_df = pd.DataFrame(
            {
                "name": ["John Doe", "Jane Smith"],
                "phone": ["+41123456789", "+41987654321"],
                "uid": ["uid1", "uid2"],
                "joined_date": [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02")],
                "pushname": ["John", "Jane"],
                "group_id": ["group1", "group1"],
            }
        )

        self.sample_sapeurs = [
            Sapeur(
                name="John Doe",
                phone="+41123456789",
                uid="uid1",
                joined_date=pd.Timestamp("2025-01-01"),
                pushname="John",
                group_id="group1",
            ),
            Sapeur(
                name="Jane Smith",
                phone="+41987654321",
                uid="uid2",
                joined_date=pd.Timestamp("2025-01-02"),
                pushname="Jane",
                group_id="group1",
            ),
        ]

    def test_init_with_default_repository(self) -> None:
        """Test initialization with default repository."""
        with patch("gardebot.services.sapeur.GroupService"):
            service = SapeurService()
            self.assertIsNotNone(service.repo)
            self.assertIsNotNone(service.group_service)

    def test_init_with_custom_repository(self) -> None:
        """Test initialization with custom repository."""
        self.assertEqual(self.service.repo, self.mock_repo)

    def test_synchronize_sapeurs(self) -> None:
        """Test synchronize_sapeurs calls both insert and delete methods."""
        self.mock_group_service.fetch_group_participants_table.return_value = self.sample_df

        with (
            patch.object(self.service, "_insert_active_sapeurs") as mock_insert,
            patch.object(self.service, "_delete_sapeur_who_quit") as mock_delete,
        ):
            self.service.synchronize_sapeurs()

            mock_insert.assert_called_once_with(self.sample_df)
            mock_delete.assert_called_once_with(self.sample_df)

    def test_insert_active_sapeurs(self) -> None:
        """Test inserting active sapeurs from DataFrame."""
        self.mock_repo.bulk_upsert.return_value = None

        result = self.service._insert_active_sapeurs(self.sample_df)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "John Doe")
        self.assertEqual(result[1].name, "Jane Smith")
        self.mock_repo.bulk_upsert.assert_called_once()

        # Verify the sapeurs passed to bulk_upsert
        called_sapeurs = self.mock_repo.bulk_upsert.call_args[0][0]
        self.assertEqual(len(called_sapeurs), 2)
        self.assertIsInstance(called_sapeurs[0], Sapeur)
        self.assertIsInstance(called_sapeurs[1], Sapeur)

    def test_insert_active_sapeurs_empty_df(self) -> None:
        """Test inserting sapeurs with empty DataFrame."""
        empty_df = pd.DataFrame()

        result = self.service._insert_active_sapeurs(empty_df)

        self.assertEqual(len(result), 0)
        self.mock_repo.bulk_upsert.assert_called_once_with([])

    def test_delete_sapeur_who_quit_none_quit(self) -> None:
        """Test deleting sapeurs when none have quit."""
        # All sapeurs in repo are still in group
        current_uids = ["uid1", "uid2"]
        df = pd.DataFrame({"uid": current_uids})

        self.mock_repo.list_sapeurs.return_value = self.sample_sapeurs
        self.mock_repo.delete.return_value = None

        self.service._delete_sapeur_who_quit(df)

        self.mock_repo.delete.assert_not_called()

    def test_delete_sapeur_who_quit_some_quit(self) -> None:
        """Test deleting sapeurs when some have quit."""
        # Only uid1 is still in group, uid2 has quit
        current_uids = ["uid1"]
        df = pd.DataFrame({"uid": current_uids})

        self.mock_repo.list_sapeurs.return_value = self.sample_sapeurs
        self.mock_repo.delete.return_value = None

        self.service._delete_sapeur_who_quit(df)

        # Should delete the sapeur with uid2
        self.mock_repo.delete.assert_called_once()
        deleted_sapeur = self.mock_repo.delete.call_args[0][0]
        self.assertEqual(deleted_sapeur.uid, "uid2")
        self.assertEqual(deleted_sapeur.name, "Jane Smith")

    def test_delete_sapeur_who_quit_all_quit(self) -> None:
        """Test deleting sapeurs when all have quit."""
        # No one is in group anymore
        empty_df = pd.DataFrame({"uid": []})

        self.mock_repo.list_sapeurs.return_value = self.sample_sapeurs
        self.mock_repo.delete.return_value = None

        self.service._delete_sapeur_who_quit(empty_df)

        # Should delete both sapeurs
        self.assertEqual(self.mock_repo.delete.call_count, 2)

        # Verify both sapeurs were deleted
        delete_calls = [call[0][0] for call in self.mock_repo.delete.call_args_list]
        deleted_uids = [sapeur.uid for sapeur in delete_calls]
        self.assertIn("uid1", deleted_uids)
        self.assertIn("uid2", deleted_uids)


if __name__ == "__main__":
    unittest.main()
