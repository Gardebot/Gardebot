"""Tests for the HttpClient class."""

import unittest
from unittest.mock import patch

import requests  # type: ignore[import-untyped]

from gardebot.errors import ExternalServiceError
from gardebot.http.http_client import HttpClient


class TestHttpClient(unittest.TestCase):
    """Test the HttpClient class."""

    def test_success_get(self) -> None:
        """Test a successful GET request."""
        client = HttpClient("http://example.com")
        with patch("requests.request") as mock_req:
            resp = requests.Response()
            resp.status_code = 200
            resp._content = b'{"ok": true}'  # noqa: SLF001
            mock_req.return_value = resp
            r = client.request("GET", "/ping")
            self.assertEqual(r.status_code, 200)

    def test_retry_and_fail(self) -> None:
        """Test retries and failure handling."""
        client = HttpClient("http://example.com", retries=1)
        with patch("requests.request", side_effect=requests.RequestException("boom")):
            with self.assertRaises(ExternalServiceError):
                client.request("GET", "/x")

    def test_non_success_raise_for_status(self) -> None:
        """Test that non-success status raises an error when raise_for_status is True."""
        client = HttpClient("http://example.com")
        with patch("requests.request") as mock_req:
            resp = requests.Response()
            resp.status_code = 500
            resp._content = b"server error"
            mock_req.return_value = resp
            with self.assertRaises(ExternalServiceError):
                client.request("GET", "/fail", raise_for_status=True)
