"""Unit tests for dispatcher module."""

import unittest
from typing import Any, Dict
from unittest.mock import Mock, patch

from gardebot.dispatcher import EventDispatcher


class TestEventDispatcher(unittest.TestCase):
    """Test cases for EventDispatcher class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_gardebot = Mock()
        self.dispatcher = EventDispatcher(self.mock_gardebot)

    def test_init(self) -> None:
        """Test dispatcher initialization."""
        self.assertEqual(self.dispatcher.gardebot, self.mock_gardebot)
        self.assertIn("message", self.dispatcher._handlers)
        self.assertIn("poll.vote", self.dispatcher._handlers)
        self.assertIn("session.status", self.dispatcher._handlers)
        self.assertIn("group.v2.participants", self.dispatcher._handlers)

    def test_dispatch_message_event(self) -> None:
        """Test dispatching message event."""
        payload = {"event": "message", "data": "test"}
        result = self.dispatcher.dispatch(payload)

        self.assertTrue(result)
        self.mock_gardebot.handle_incoming_message.assert_called_once_with(payload)

    def test_dispatch_poll_vote_event(self) -> None:
        """Test dispatching poll vote event."""
        payload = {"event": "poll.vote", "data": "test"}
        result = self.dispatcher.dispatch(payload)

        self.assertTrue(result)
        self.mock_gardebot.handle_incoming_vote.assert_called_once_with(payload)

    def test_dispatch_invalid_event_field(self) -> None:
        """Test dispatching with invalid event field."""
        payload = {"event": 123}

        with patch("gardebot.dispatcher.LOGGER") as mock_logger:
            result = self.dispatcher.dispatch(payload)

        self.assertFalse(result)
        mock_logger.warning.assert_called_once_with("invalid_event_field", got=123)

    def test_dispatch_unhandled_event(self) -> None:
        """Test dispatching unhandled event."""
        payload = {"event": "unknown.event"}

        with patch("gardebot.dispatcher.LOGGER") as mock_logger:
            result = self.dispatcher.dispatch(payload)

        self.assertFalse(result)
        mock_logger.info.assert_called_once_with("unhandled_event", event="unknown.event")

    def test_handle_session_status_no_payload(self) -> None:
        """Test handling session status with no payload."""
        payload: Dict[str, Any] = {}

        with patch("gardebot.dispatcher.LOGGER") as mock_logger:
            self.dispatcher._handle_session_status(payload)
            mock_logger.debug.assert_called_once_with("session_status_no_payload")

    @patch("gardebot.dispatcher.settings")
    def test_handle_session_status_working(self, mock_settings: Any) -> None:
        """Test handling WORKING session status."""
        mock_settings.server.postpone_sync_time = 5
        payload = {"payload": {"status": "WORKING"}}

        with patch("gardebot.dispatcher.LOGGER") as mock_logger:
            self.dispatcher._handle_session_status(payload)

        mock_logger.info.assert_called_once()
        self.assertTrue(mock_logger.info.call_args[0][0].startswith("session_status_change"))

    def test_handle_group_participants(self) -> None:
        """Test handling group participants change."""
        payload = {"event": "group.v2.participants"}

        with patch("gardebot.dispatcher.LOGGER") as mock_logger:
            self.dispatcher._handle_group_participants(payload)
            mock_logger.info.assert_called_once_with("participants_change_trigger")

    def test_debounced_participant_sync(self) -> None:
        """Test debounced participant synchronization."""
        self.dispatcher._debounced_participant_sync()
        self.mock_gardebot.sapeur_service.synchronize_sapeurs.assert_called_once()

    def test_debounced_initialize(self) -> None:
        """Test debounced initialization."""
        self.dispatcher._debounced_initialize()
        self.mock_gardebot.initialize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
