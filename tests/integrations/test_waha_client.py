"""Tests for the WahaClient integration."""

import unittest
from unittest.mock import Mock, patch

import requests  # type: ignore[import-untyped]

from gardebot.errors import ExternalServiceError
from gardebot.integrations.waha_client import WahaClient


class TestWahaClient(unittest.TestCase):
    """Test the WahaClient class."""

    def setUp(self) -> None:
        """Set up a WahaClient instance."""
        self.client = WahaClient(api_key="k", base_url="http://waha.local", session="s")

    @patch("requests.request")
    def test_send_text_success(self, mock_req: Mock) -> None:
        """Test sending a text message successfully."""
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'{"id":"123"}'
        mock_req.return_value = resp
        data = self.client.send_text("123", "hello")
        self.assertEqual(data["id"], "123")

    @patch("requests.request")
    def test_send_text_failure(self, mock_req: Mock) -> None:
        """Test sending a text message with failure."""
        resp = requests.Response()
        resp.status_code = 500
        resp._content = b"fail"
        mock_req.return_value = resp
        with self.assertRaises(ExternalServiceError):
            self.client.send_text("123", "hello")

    @patch("requests.request")
    def test_get_message(self, mock_req: Mock) -> None:
        """Test retrieving a message successfully."""
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'{"body":"hi"}'
        mock_req.return_value = resp
        data = self.client.get_message("chat", "mid")
        self.assertEqual(data["body"], "hi")
