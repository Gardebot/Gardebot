"""Unit tests for HTTP client."""

import unittest
from unittest.mock import Mock, patch

import requests  # type: ignore[import-untyped]

from gardebot.errors import ExternalServiceError
from gardebot.http.http_client import HttpClient, _exponential_backoff, safe_response_preview


class TestExponentialBackoff(unittest.TestCase):
    """Test exponential backoff utility function."""

    def test_exponential_backoff_no_jitter(self) -> None:
        """Test exponential backoff without jitter."""
        self.assertEqual(_exponential_backoff(0, 1.0, 10.0, jitter=False), 1.0)
        self.assertEqual(_exponential_backoff(1, 1.0, 10.0, jitter=False), 2.0)
        self.assertEqual(_exponential_backoff(2, 1.0, 10.0, jitter=False), 4.0)
        self.assertEqual(_exponential_backoff(3, 1.0, 10.0, jitter=False), 8.0)

    def test_exponential_backoff_cap(self) -> None:
        """Test exponential backoff with cap."""
        result = _exponential_backoff(10, 1.0, 5.0, jitter=False)
        self.assertEqual(result, 5.0)

    def test_exponential_backoff_with_jitter(self) -> None:
        """Test exponential backoff with jitter."""
        result = _exponential_backoff(1, 1.0, 10.0, jitter=True)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 2.0)


class TestSafeResponsePreview(unittest.TestCase):
    """Test safe response preview utility."""

    def test_safe_response_preview_normal(self) -> None:
        """Test normal response preview."""
        mock_response = Mock()
        mock_response.text = "This is a test response"
        result = safe_response_preview(mock_response)
        self.assertEqual(result, "This is a test response")

    def test_safe_response_preview_with_limit(self) -> None:
        """Test response preview with limit."""
        mock_response = Mock()
        mock_response.text = "This is a very long response text"
        result = safe_response_preview(mock_response, limit=10)
        self.assertEqual(result, "This is a ")

    def test_safe_response_preview_exception(self) -> None:
        """Test response preview when exception occurs."""
        mock_response = Mock()
        mock_response.text = Mock(side_effect=Exception("Error"))
        result = safe_response_preview(mock_response)
        self.assertEqual(result, "<unreadable>")


class TestHttpClient(unittest.TestCase):
    """Test HttpClient class."""

    def setUp(self) -> None:
        """Set up test client."""
        self.client = HttpClient(base_url="https://api.example.com", timeout=30, headers={"Authorization": "Bearer test"}, retries=2)

    def test_client_initialization(self) -> None:
        """Test client initialization."""
        self.assertEqual(self.client.base_url, "https://api.example.com")
        self.assertEqual(self.client.timeout, 30)
        self.assertEqual(self.client.headers, {"Authorization": "Bearer test"})
        self.assertEqual(self.client.retries, 2)

    def test_full_url_relative(self) -> None:
        """Test full URL construction with relative endpoint."""
        url = self.client._full_url("/test/endpoint")
        self.assertEqual(url, "https://api.example.com/test/endpoint")

    def test_full_url_absolute(self) -> None:
        """Test full URL construction with absolute endpoint."""
        url = self.client._full_url("https://other.com/test")
        self.assertEqual(url, "https://other.com/test")

    def test_is_success(self) -> None:
        """Test success status check."""
        self.assertTrue(self.client.is_success(200))
        self.assertTrue(self.client.is_success(201))
        self.assertTrue(self.client.is_success(299))
        self.assertFalse(self.client.is_success(300))
        self.assertFalse(self.client.is_success(400))
        self.assertFalse(self.client.is_success(500))

    @patch("requests.request")
    def test_successful_request(self, mock_request: Mock) -> None:
        """Test successful HTTP request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Success"
        mock_request.return_value = mock_response

        response = self.client.request("GET", "/test")

        self.assertEqual(response, mock_response)
        mock_request.assert_called_once_with(
            method="GET", url="https://api.example.com/test", headers={"Authorization": "Bearer test"}, json=None, params=None, timeout=30
        )

    @patch("requests.request")
    def test_request_with_params(self, mock_request: Mock) -> None:
        """Test request with parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Success"
        mock_request.return_value = mock_response

        self.client.request("POST", "/test", json_body={"key": "value"}, params={"param": "value"})

        mock_request.assert_called_once_with(
            method="POST",
            url="https://api.example.com/test",
            headers={"Authorization": "Bearer test"},
            json={"key": "value"},
            params={"param": "value"},
            timeout=30,
        )

    @patch("requests.request")
    def test_request_raise_for_status(self, mock_request: Mock) -> None:
        """Test request with raise_for_status=True."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_request.return_value = mock_response

        with self.assertRaises(ExternalServiceError) as cm:
            self.client.request("GET", "/test", raise_for_status=True)

        self.assertIn("Non-success status 400", str(cm.exception))

    @patch("requests.request")
    @patch("time.sleep")
    def test_request_with_retries(self, mock_sleep: Mock, mock_request: Mock) -> None:
        """Test request with retries."""
        # First two calls fail, third succeeds
        mock_request.side_effect = [
            requests.RequestException("Network error"),
            requests.RequestException("Network error"),
            Mock(status_code=200, text="Success"),
        ]

        response = self.client.request("GET", "/test")

        self.assertEqual(mock_request.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertEqual(response.status_code, 200)

    @patch("requests.request")
    @patch("time.sleep")
    def test_request_max_retries_exceeded(self, mock_sleep: Mock, mock_request: Mock) -> None:
        """Test request when max retries exceeded."""
        mock_request.side_effect = requests.RequestException("Network error")

        with self.assertRaises(ExternalServiceError) as cm:
            self.client.request("GET", "/test")

        self.assertEqual(mock_request.call_count, 3)  # Initial + 2 retries
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertIn("HTTP request failed", str(cm.exception))

    @patch("requests.request")
    def test_request_external_service_error_propagated(self, mock_request: Mock) -> None:
        """Test that ExternalServiceError is propagated correctly."""
        mock_request.side_effect = ExternalServiceError("Service unavailable")

        with self.assertRaises(ExternalServiceError) as cm:
            self.client.request("GET", "/test")

        self.assertEqual(str(cm.exception), "Service unavailable")

    def test_client_with_defaults(self) -> None:
        """Test client initialization with default settings."""
        with patch("gardebot.settings.settings") as mock_settings:
            mock_settings.api.base_url = "https://default.com"
            mock_settings.api.timeout_seconds = 60
            mock_settings.api.retry_attempts = 3
            mock_settings.api.retry_backoff_seconds = 1.0
            mock_settings.api.retry_backoff_max_seconds = 30.0

            client = HttpClient(
                base_url=mock_settings.api.base_url, timeout=mock_settings.api.timeout_seconds, retries=mock_settings.api.retry_attempts
            )
            self.assertEqual(client.base_url, "https://default.com")
            self.assertEqual(client.timeout, 60)
            self.assertEqual(client.retries, 3)

    def test_client_zero_retries(self) -> None:
        """Test client with zero retries."""
        client = HttpClient(retries=0)
        self.assertEqual(client.retries, 0)

    def test_client_negative_retries(self) -> None:
        """Test client with negative retries."""
        client = HttpClient(retries=-1)
        self.assertEqual(client.retries, 0)


if __name__ == "__main__":
    unittest.main()
