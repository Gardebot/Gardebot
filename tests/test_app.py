"""Unit tests for app module."""

import json
import unittest
from unittest.mock import Mock, patch

from gardebot.app import create_app
from gardebot.validation import MessageValidationError


class TestApp(unittest.TestCase):
    """Test cases for Flask application."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        with patch("gardebot.app.Gardebot"), patch("gardebot.app.register_error_handlers"):
            self.app = create_app()
            self.app.testing = True  # Propagate exceptions to test client
            self.client = self.app.test_client()

    def test_health_endpoint(self) -> None:
        """Test health check endpoint."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "ok")

    @patch("gardebot.app.generate_latest")
    def test_metrics_endpoint(self, mock_generate: Mock) -> None:
        """Test metrics endpoint."""
        mock_generate.return_value = b"metric_data"
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"metric_data")

    def test_webhook_get(self) -> None:
        """Test webhook GET request."""
        response = self.client.get("/webhook")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "ok")
        self.assertIn("correlation_id", data)

    @patch("gardebot.app.EventDispatcher")
    def test_webhook_post_valid_message(self, mock_dispatcher_cls: Mock) -> None:
        """Test webhook POST with valid message."""
        mock_dispatcher = Mock()
        mock_dispatcher.dispatch.return_value = True
        mock_dispatcher_cls.return_value = mock_dispatcher

        payload = {"event": "message", "payload": {"from": "1234567890", "body": "test message", "timestamp": 1234567890}}

        with patch("gardebot.app.validate_message_event", return_value=payload):
            response = self.client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["handled"])

    def test_webhook_post_invalid_json(self) -> None:
        """Test webhook POST with invalid JSON."""
        response = self.client.post("/webhook", data="invalid json")

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["message"], "invalid_json")

    @patch("gardebot.app.validate_message_event")
    def test_webhook_post_invalid_message_payload(self, mock_validate: Mock) -> None:
        """Test webhook POST with invalid message payload."""

        mock_validate.side_effect = MessageValidationError("Invalid payload")
        payload = {"event": "message", "payload": {}}

        response = self.client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 422)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["message"], "invalid_message_payload")

    @patch("gardebot.app.basic_event_presence_check")
    def test_webhook_post_invalid_non_message_event(self, mock_check: Mock) -> None:
        """Test webhook POST with invalid non-message event."""
        mock_check.return_value = False
        payload = {"event": "other.event"}

        response = self.client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["message"], "invalid_event")


if __name__ == "__main__":
    unittest.main()
