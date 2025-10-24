"""Unit tests for GroupService."""

import unittest
from unittest.mock import Mock, patch

import pandas as pd  # type: ignore[import-untyped]

from gardebot.services.group_service import GroupService


class TestGroupService(unittest.TestCase):
    """Test GroupService class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        with patch("gardebot.services.group_service.ContactAdapter"), patch("gardebot.services.group_service.GroupAdapter"):
            self.service = GroupService()

        self.mock_contact = Mock()
        self.mock_group = Mock()
        self.service.contact = self.mock_contact
        self.service.group = self.mock_group

        self.mock_group.group_id = "test-group-123"

    def test_fetch_group_participants_table_empty(self) -> None:
        """Test fetching participants table with no participants."""
        self.mock_group.get_group_participants.return_value = []

        result = self.service.fetch_group_participants_table()

        self.assertTrue(result.empty)
        self.mock_group.get_group_participants.assert_called_once()

    def test_fetch_group_participants_table_with_data(self) -> None:
        """Test fetching participants table with data."""
        participants = [{"PhoneNumber": "+41123456789"}, {"PhoneNumber": "+41987654321"}, {"PhoneNumber": "invalid-phone"}]
        contact_info = [
            {"id": "123456789", "name": "John Doe", "phone": "+41123456789"},
            {"id": "987654321", "name": "Jane Smith", "phone": "+41987654321"},
        ]

        self.mock_group.get_group_participants.return_value = participants
        self.mock_contact.get_contact_info.side_effect = [contact_info[0], contact_info[1], None]

        with patch("pandas.Timestamp.now") as mock_now:
            mock_timestamp = pd.Timestamp("2025-10-23 12:00:00+01:00")
            mock_now.return_value = mock_timestamp

            result = self.service.fetch_group_participants_table()

            self.assertFalse(result.empty)
            self.assertEqual(len(result), 2)
            self.assertIn("joined_date", result.columns)
            self.assertIn("group_id", result.columns)
            self.assertIn("uid", result.columns)
            self.assertEqual(result["group_id"].iloc[0], "test-group-123")
            self.assertEqual(result["joined_date"].iloc[0], mock_timestamp)

    def test_fetch_group_participants_table_no_contact_info(self) -> None:
        """Test fetching participants when no contact info available."""
        participants = [{"PhoneNumber": "+41123456789"}]
        self.mock_group.get_group_participants.return_value = participants
        self.mock_contact.get_contact_info.return_value = None

        result = self.service.fetch_group_participants_table()

        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
