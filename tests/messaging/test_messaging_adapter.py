"""Tests for MessagingAdapter."""

import unittest
from unittest.mock import MagicMock

from gardebot.adapters.messaging import MessagingAdapter
from gardebot.errors import ExternalServiceError
from gardebot.integrations.waha_client import WahaClient


class TestMessagingAdapter(unittest.TestCase):
    """Tests for MessagingAdapter."""

    def setUp(self) -> None:
        """Set up the MessagingAdapter with a mocked WahaClient."""
        self.mock_client = MagicMock(spec=WahaClient)
        self.mock_client.session = "default"
        self.adapter = MessagingAdapter(waha_client=self.mock_client)

    def test_send_text_ok(self) -> None:
        """Test that send_text works correctly."""
        self.mock_client.send_text.return_value = {"id": "123"}
        res = self.adapter.send_text("111", "hello")
        self.assertEqual(res["id"], "123")

    def test_send_text_error(self) -> None:
        """Test that send_text raises ExternalServiceError on failure."""
        self.mock_client.send_text.side_effect = ExternalServiceError("boom")
        with self.assertRaises(ExternalServiceError):
            self.adapter.send_text("111", "hello")
