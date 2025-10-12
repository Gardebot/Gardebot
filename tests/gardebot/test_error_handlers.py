"""Tests for error handlers in the Gardebot Flask app."""

import unittest
from typing import Any, Dict

import gardebot.dispatcher
from gardebot.app import create_app


class TestErrorHandlers(unittest.TestCase):
    """Test the error handlers in the Gardebot Flask app."""

    def setUp(self) -> None:
        """Set up the Flask test client."""
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_unexpected_exception(self) -> None:
        """Test that an unexpected exception in the webhook handler returns a 500 with JSON error."""

        original_dispatch = gardebot.dispatcher.EventDispatcher.dispatch

        def boom(self: gardebot.dispatcher.EventDispatcher, payload: Dict[str, Any]) -> None:  # noqa: D401, ARG001
            """Simulate a failure in the dispatcher."""
            raise RuntimeError("simulated boom")

        try:
            gardebot.dispatcher.EventDispatcher.dispatch = boom  # type: ignore[method-assign, assignment]
            resp = self.client.post(
                "/webhook",
                json={"event": "message", "payload": {"fromMe": False, "from": "x", "body": "hi"}},
            )
        finally:
            gardebot.dispatcher.EventDispatcher.dispatch = original_dispatch  # type: ignore[method-assign]

        self.assertEqual(resp.status_code, 500, msg=f"Body was: {resp.get_json()}")
        data = resp.get_json()
        # Defensive diagnostics
        self.assertIsInstance(data, dict, f"Non-JSON response: {resp.data}")
        self.assertEqual(data["status"], "error")
        self.assertIn("message", data)
