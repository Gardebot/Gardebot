# mypy: disable-error-code="method-assign, index"
"""Unit tests for ContactAdapter."""

import unittest
from typing import Any
from unittest.mock import Mock, patch

from gardebot.adapters.contacts import ContactAdapter
from gardebot.errors import ExternalServiceError


class TestContactAdapter(unittest.TestCase):
    """Test cases for ContactAdapter."""

    @patch("gardebot.adapters.contacts.WahaClient.__init__", return_value=None)
    def test_init(self, mock_waha_client_init: Any) -> None:
        """Test ContactAdapter initialization."""
        adapter = ContactAdapter()
        self.assertIsNotNone(adapter)
        mock_waha_client_init.assert_called_once()

    def test_get_contact_info_success(self) -> None:
        """Test successful contact info retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": "1234567890@c.us", "name": "Test User", "pushname": "TestUser"}

        adapter = ContactAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)

        result = adapter.get_contact_info("1234567890@c.us")

        expected_endpoint = "/api/contacts?contactId=1234567890@c.us&session=test_session"
        adapter.get.assert_called_once_with(expected_endpoint, raise_for_status=True)

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "1234567890@c.us")
        self.assertEqual(result["phone"], "+1234567890")  # Phone number added by quick fix

    def test_get_contact_info_with_phone_extraction(self) -> None:
        """Test that phone number is correctly extracted from contact_id."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": "41123456789@c.us"}

        adapter = ContactAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)

        result = adapter.get_contact_info("41123456789@c.us")

        self.assertEqual(result["phone"], "+41123456789")

    def test_get_contact_info_with_complex_contact_id(self) -> None:
        """Test phone extraction with complex contact ID containing non-digits."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": "test123@c.us"}

        adapter = ContactAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)

        result = adapter.get_contact_info("test123@c.us")

        # Should extract only digits: "123"
        self.assertEqual(result["phone"], "+123")

    def test_get_contact_info_exception_handling(self) -> None:
        """Test that exceptions are properly wrapped in ExternalServiceError."""
        adapter = ContactAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(side_effect=Exception("Network error"))

        with self.assertRaises(ExternalServiceError) as context:
            adapter.get_contact_info("1234567890@c.us")

        self.assertEqual(str(context.exception), "Failed to fetch contact info")
        self.assertEqual(context.exception.detail["error"], "Network error")

    @patch("gardebot.adapters.contacts.LOGGER")
    def test_get_contact_info_logging(self, mock_logger: Any) -> None:
        """Test that successful contact fetch is logged."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": "1234567890@c.us"}

        adapter = ContactAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)

        adapter.get_contact_info("1234567890@c.us")

        mock_logger.debug.assert_called_once_with("Contact info fetched successfully for contact %s", "1234567890@c.us")

    def test_get_contact_info_no_digits_in_contact_id(self) -> None:
        """Test phone extraction when contact ID has no digits."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": "test@c.us"}

        adapter = ContactAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)

        result = adapter.get_contact_info("test@c.us")

        # Should result in just "+"
        self.assertEqual(result["phone"], "+")

    def test_get_contact_info_endpoint_construction(self) -> None:
        """Test that the API endpoint is correctly constructed."""
        adapter = ContactAdapter()
        adapter.session = "test_session_123"
        adapter.get = Mock()

        mock_response = Mock()
        mock_response.json.return_value = {"id": "contact123@c.us"}
        adapter.get.return_value = mock_response

        adapter.get_contact_info("contact123@c.us")

        expected_endpoint = "/api/contacts?contactId=contact123@c.us&session=test_session_123"
        adapter.get.assert_called_once_with(expected_endpoint, raise_for_status=True)

    def test_get_contact_info_returns_original_plus_phone(self) -> None:
        """Test that the method returns original contact info plus phone number."""
        original_contact_info = {"id": "1234567890@c.us", "name": "Test User", "pushname": "TestUser", "extra_field": "extra_value"}

        mock_response = Mock()
        mock_response.json.return_value = original_contact_info

        adapter = ContactAdapter()
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)

        result = adapter.get_contact_info("1234567890@c.us")

        # Should contain all original fields plus phone
        self.assertEqual(result["id"], "1234567890@c.us")
        self.assertEqual(result["name"], "Test User")
        self.assertEqual(result["pushname"], "TestUser")
        self.assertEqual(result["extra_field"], "extra_value")
        self.assertEqual(result["phone"], "+1234567890")


if __name__ == "__main__":
    unittest.main()
