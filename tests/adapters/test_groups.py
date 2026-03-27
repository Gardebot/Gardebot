# mypy: disable-error-code="method-assign, attr-defined"
"""Unit tests for GroupAdapter."""

import unittest
from unittest.mock import Mock, patch

from gardebot.adapters.groups import GroupAdapter
from gardebot.config import GROUP_ID_GARDE_ET_PIQUET
from gardebot.errors import ExternalServiceError


class TestGroupAdapter(unittest.TestCase):
    """Test cases for GroupAdapter."""

    @patch("gardebot.adapters.groups.WahaClient.__init__", return_value=None)
    def test_init_default_group_id(self, mock_waha_client_init: Mock) -> None:
        """Test initialization with default group ID."""
        adapter = GroupAdapter()
        self.assertEqual(adapter.group_id, GROUP_ID_GARDE_ET_PIQUET)
        mock_waha_client_init.assert_called_once()

    def test_init_custom_group_id(self) -> None:
        """Test initialization with custom group ID."""
        custom_group_id = "custom_group_123@g.us"
        adapter = GroupAdapter(group_id=custom_group_id)
        self.assertEqual(adapter.group_id, custom_group_id)

    def test_get_group_participants_success(self) -> None:
        """Test successful group participants retrieval."""
        expected_participants = [{"id": "user1@c.us", "name": "User 1"}, {"id": "user2@c.us", "name": "User 2"}]

        mock_response = Mock()
        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)
        adapter.extract_json = Mock(return_value=expected_participants)

        result = adapter.get_group_participants()

        expected_endpoint = f"/api/test_session/groups/{GROUP_ID_GARDE_ET_PIQUET}/participants"
        adapter.get.assert_called_once_with(expected_endpoint, raise_for_status=True)
        adapter.extract_json.assert_called_once_with(mock_response)
        self.assertEqual(result, expected_participants)

    @patch("gardebot.adapters.groups.LOGGER")
    def test_get_group_participants_logging(self, mock_logger: Mock) -> None:
        """Test that participants fetch is logged."""
        participants = [{"id": "user1@c.us"}]

        mock_response = Mock()
        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)
        adapter.extract_json = Mock(return_value=participants)

        adapter.get_group_participants()

        mock_logger.debug.assert_called_once_with("group_participants_fetched", extra={"group_id": GROUP_ID_GARDE_ET_PIQUET, "count": 1})

    def test_get_group_participants_wrong_data_type(self) -> None:
        """Test error handling when participants data is not a list."""
        mock_response = Mock()
        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)
        adapter.extract_json = Mock(return_value={"not": "a list"})  # Wrong type

        with self.assertRaises(ExternalServiceError) as context:
            adapter.get_group_participants()

        self.assertEqual(str(context.exception), "Unexpected participants data shape")
        self.assertEqual(context.exception.detail["type"], "dict")

    def test_get_group_participants_exception_handling(self) -> None:
        """Test generic exception handling in get_group_participants."""
        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(side_effect=Exception("Network error"))

        with self.assertRaises(ExternalServiceError) as context:
            adapter.get_group_participants()

        self.assertEqual(str(context.exception), "Failed to fetch group participants")
        self.assertEqual(context.exception.detail["error"], "Network error")

    def test_get_groups_list_response(self) -> None:
        """Test get_groups when response is a list."""
        expected_groups = [{"id": "group1@g.us", "subject": "Group 1"}, {"id": "group2@g.us", "subject": "Group 2"}]

        mock_response = Mock()
        mock_response.json.return_value = expected_groups

        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)
        adapter.extract_json_list = Mock(return_value=expected_groups)

        result = adapter.get_groups(limit=5, offset=0, sort_by="subject", sort_order="asc")

        expected_endpoint = "/api/test_session/groups"
        expected_params = {"limit": 5, "offset": 0, "sortBy": "subject", "sortOrder": "asc"}
        adapter.get.assert_called_once_with(expected_endpoint, params=expected_params, raise_for_status=True)
        adapter.extract_json_list.assert_called_once_with(mock_response)
        self.assertEqual(result, expected_groups)

    def test_get_groups_dict_response(self) -> None:
        """Test get_groups when response is a dict."""
        expected_groups = {"groups": [{"id": "group1@g.us"}], "total": 1, "hasMore": False}

        mock_response = Mock()
        mock_response.json.return_value = expected_groups

        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)
        adapter.extract_json_dict = Mock(return_value=expected_groups)

        result = adapter.get_groups()

        adapter.extract_json_dict.assert_called_once_with(mock_response)
        self.assertEqual(result, expected_groups)

    def test_get_groups_default_parameters(self) -> None:
        """Test get_groups with default parameters."""
        mock_response = Mock()
        mock_response.json.return_value = []

        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)
        adapter.extract_json_list = Mock(return_value=[])

        adapter.get_groups()

        expected_params = {"limit": 10, "offset": 0, "sortBy": "subject", "sortOrder": "desc"}
        adapter.get.assert_called_once_with("/api/test_session/groups", params=expected_params, raise_for_status=True)

    def test_get_groups_unexpected_response_type(self) -> None:
        """Test get_groups with unexpected response type."""
        mock_response = Mock()
        mock_response.json.return_value = "unexpected string"

        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)

        with self.assertRaises(ExternalServiceError) as context:
            adapter.get_groups()

        self.assertEqual(str(context.exception), "Unexpected groups response data shape")
        self.assertEqual(context.exception.detail["type"], "str")

    def test_get_groups_exception_handling(self) -> None:
        """Test generic exception handling in get_groups."""
        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(side_effect=Exception("API error"))

        with self.assertRaises(ExternalServiceError) as context:
            adapter.get_groups()

        self.assertEqual(str(context.exception), "Failed to fetch groups")
        self.assertEqual(context.exception.detail["error"], "API error")

    def test_get_groups_external_service_error_passthrough(self) -> None:
        """Test that ExternalServiceError is passed through without wrapping."""
        original_error = ExternalServiceError("Original error")

        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(side_effect=original_error)

        with self.assertRaises(ExternalServiceError) as context:
            adapter.get_groups()

        # Should be the same error object, not wrapped
        self.assertIs(context.exception, original_error)

    def test_get_group_participants_external_service_error_passthrough(self) -> None:
        """Test that ExternalServiceError is passed through without wrapping."""
        original_error = ExternalServiceError("Original error")

        adapter = GroupAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(side_effect=original_error)

        with self.assertRaises(ExternalServiceError) as context:
            adapter.get_group_participants()

        # Should be the same error object, not wrapped
        self.assertIs(context.exception, original_error)

    def test_custom_group_id_usage(self) -> None:
        """Test that custom group ID is used in API calls."""
        custom_group_id = "custom123@g.us"
        mock_response = Mock()

        adapter = GroupAdapter(group_id=custom_group_id)
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)
        adapter.extract_json = Mock(return_value=[])

        adapter.get_group_participants()

        expected_endpoint = f"/api/test_session/groups/{custom_group_id}/participants"
        adapter.get.assert_called_once_with(expected_endpoint, raise_for_status=True)


if __name__ == "__main__":
    unittest.main()
