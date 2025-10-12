"""End-to-end tests for webhook message flow, including network failure simulation."""

import unittest
from unittest.mock import Mock, patch

from requests import RequestException  # type: ignore[import-untyped]

from gardebot.app import create_app  # type: ignore


class TestE2EMessageFlow(unittest.TestCase):
    """End-to-end tests for webhook message flow, including network failure simulation."""

    def setUp(self) -> None:
        """Set up the Flask test client."""
        self.client = create_app().test_client()

    def test_message_success(self) -> None:
        """Test a successful message flow."""
        resp = self.client.post(
            "/webhook",
            json={
                "event": "message",
                "payload": {
                    "fromMe": False,
                    "from": "111",
                    "body": "!ping",
                    "timestamp": 1,
                },
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNotNone(data)
        self.assertTrue(data["handled"])

    @patch("requests.request")
    def test_message_waha_network_failure(self, mock_req: Mock) -> None:
        """Test message flow with WahaClient network failure."""
        mock_req.side_effect = RequestException("down")
        resp = self.client.post(
            "/webhook",
            json={
                "event": "message",
                "payload": {
                    "fromMe": False,
                    "from": "222",
                    "body": "Hello",
                    "timestamp": 2,
                },
            },
        )
        # Still 200 because legacy path converts failure to log + continue
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNotNone(data)
        self.assertTrue(data["handled"])
