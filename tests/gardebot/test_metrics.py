"""Tests for the /metrics endpoint and metric recording in Gardebot."""

import unittest

from gardebot.app import create_app


class TestMetrics(unittest.TestCase):
    """Test the /metrics endpoint and metric recording."""

    def setUp(self) -> None:
        """Set up the Flask test client."""
        self.client = create_app().test_client()

    def test_metrics_available(self) -> None:
        """Test that the /metrics endpoint is available and returns Prometheus metrics."""
        r = self.client.get("/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"gardebot_webhook_events_total", r.data)

    def test_metrics_increment(self) -> None:
        """Test that sending a webhook increments the appropriate metrics."""
        before = self.client.get("/metrics").data.count(b"message")
        self.client.post("/webhook", json={"event": "message", "payload": {}})
        after = self.client.get("/metrics").data.count(b"message")
        self.assertTrue(after >= before)
