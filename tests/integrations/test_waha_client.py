"""Unit tests for WAHA client."""

import unittest
from unittest.mock import Mock, patch

from gardebot.errors import ExternalServiceError
from gardebot.integrations.waha_client import WahaClient


class TestWahaClient(unittest.TestCase):
    """Test WahaClient class."""

    def setUp(self) -> None:
        """Set up test client."""
        with patch("gardebot.settings.settings") as mock_settings:
            mock_settings.api.api_key = "test-key"
            mock_settings.api.base_url = "https://api.waha.com"
            mock_settings.api.session = "test-session"
            mock_settings.api.timeout_seconds = 30
            mock_settings.api.retry_attempts = 2

            self.client = WahaClient(
                api_key=mock_settings.api.api_key,
                base_url=mock_settings.api.base_url,
                session=mock_settings.api.session,
                timeout=mock_settings.api.timeout_seconds,
                retries=mock_settings.api.retry_attempts,
            )

    def test_client_initialization(self) -> None:
        """Test client initialization."""
        self.assertEqual(self.client.session, "test-session")
        self.assertIsNotNone(self.client._http)

    def test_client_custom_parameters(self) -> None:
        """Test client with custom parameters."""
        client = WahaClient(api_key="custom-key", base_url="https://custom.com", session="custom-session", timeout=60, retries=5)
        self.assertEqual(client.session, "custom-session")

    def test_extract_json_dict(self) -> None:
        """Test JSON dict extraction."""
        mock_response = Mock()
        mock_response.json.return_value = {"key": "value", "number": 123}

        result = self.client.extract_json(mock_response)

        self.assertEqual(result, {"key": "value", "number": 123})
        self.assertIsInstance(result, dict)

    def test_extract_json_list(self) -> None:
        """Test JSON list extraction."""
        mock_response = Mock()
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]

        result = self.client.extract_json(mock_response)

        self.assertEqual(result, [{"id": 1}, {"id": 2}])
        self.assertIsInstance(result, list)

    def test_extract_json_unexpected_type(self) -> None:
        """Test JSON extraction with unexpected type."""
        mock_response = Mock()
        mock_response.json.return_value = "string_response"

        with self.assertRaises(ExternalServiceError) as cm:
            self.client.extract_json(mock_response)

        self.assertIn("Unexpected JSON response type", str(cm.exception))

    def test_extract_json_dict_static(self) -> None:
        """Test static JSON dict extraction."""
        mock_response = Mock()
        mock_response.json.return_value = {"test": "data"}

        result = WahaClient.extract_json_dict(mock_response)

        self.assertEqual(result, {"test": "data"})

    def test_extract_json_dict_exception(self) -> None:
        """Test static JSON dict extraction with exception."""
        mock_response = Mock()
        mock_response.json.side_effect = Exception("JSON error")
        mock_response.text = "error text"

        with self.assertRaises(ExternalServiceError) as cm:
            WahaClient.extract_json_dict(mock_response)

        self.assertIn("Invalid JSON response", str(cm.exception))

    def test_extract_json_list_static(self) -> None:
        """Test static JSON list extraction."""
        mock_response = Mock()
        mock_response.json.return_value = [{"id": 1}]

        result = WahaClient.extract_json_list(mock_response)

        self.assertEqual(result, [{"id": 1}])

    def test_extract_json_list_not_list(self) -> None:
        """Test static JSON list extraction when response is not a list."""
        mock_response = Mock()
        mock_response.json.return_value = {"not": "a_list"}

        with self.assertRaises(ExternalServiceError) as cm:
            WahaClient.extract_json_list(mock_response)

        self.assertIn("Invalid JSON response", str(cm.exception))

    def test_extract_json_list_exception(self) -> None:
        """Test static JSON list extraction with exception."""
        mock_response = Mock()
        mock_response.json.side_effect = Exception("JSON error")
        mock_response.text = "error text"

        with self.assertRaises(ExternalServiceError) as cm:
            WahaClient.extract_json_list(mock_response)

        self.assertIn("Invalid JSON response", str(cm.exception))

    def test_ensure_success_success_status(self) -> None:
        """Test ensure success with success status."""
        mock_response = Mock()
        mock_response.status_code = 200

        # Should not raise
        self.client._ensure_success(mock_response, "Test error")

    def test_ensure_success_failure_status(self) -> None:
        """Test ensure success with failure status."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"

        with patch.object(self.client._http, "is_success", return_value=False):
            with self.assertRaises(ExternalServiceError) as cm:
                self.client._ensure_success(mock_response, "Test error")

            self.assertIn("Test error", str(cm.exception))

    def test_get_request(self) -> None:
        """Test GET request."""
        mock_response = Mock()
        mock_http = Mock()
        mock_http.request.return_value = mock_response
        self.client._http = mock_http

        response = self.client.get("/test", {"param": "value"}, {"query": "test"})

        self.assertEqual(response, mock_response)
        mock_http.request.assert_called_once_with(
            method="GET", endpoint="/test", json_body={"param": "value"}, params={"query": "test"}, raise_for_status=False
        )

    def test_get_request_with_raise_for_status(self) -> None:
        """Test GET request with raise_for_status."""
        mock_response = Mock()
        mock_http = Mock()
        mock_http.request.return_value = mock_response
        self.client._http = mock_http

        response = self.client.get("/test", raise_for_status=True)

        self.assertEqual(response, mock_response)
        mock_http.request.assert_called_once_with(method="GET", endpoint="/test", json_body=None, params=None, raise_for_status=True)

    def test_post_request(self) -> None:
        """Test POST request."""
        mock_response = Mock()
        mock_http = Mock()
        mock_http.request.return_value = mock_response
        self.client._http = mock_http

        response = self.client.post("/test", {"data": "value"}, {"query": "test"})

        self.assertEqual(response, mock_response)
        mock_http.request.assert_called_once_with(
            method="POST", endpoint="/test", json_body={"data": "value"}, params={"query": "test"}, raise_for_status=False
        )

    def test_post_request_with_raise_for_status(self) -> None:
        """Test POST request with raise_for_status."""
        mock_response = Mock()
        mock_http = Mock()
        mock_http.request.return_value = mock_response
        self.client._http = mock_http

        response = self.client.post("/test", raise_for_status=True)

        self.assertEqual(response, mock_response)
        mock_http.request.assert_called_once_with(method="POST", endpoint="/test", json_body=None, params=None, raise_for_status=True)


if __name__ == "__main__":
    unittest.main()
