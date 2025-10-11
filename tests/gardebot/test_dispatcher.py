"""Unit tests for the EventDispatcher class in gardebot.dispatcher."""

import unittest
from typing import Any
from unittest.mock import Mock, patch

from gardebot.dispatcher import EventDispatcher


class TestEventDispatcher(unittest.TestCase):
    """Unit tests for the EventDispatcher class."""

    def setUp(self) -> None:
        """Set up a mock Gardebot instance and the EventDispatcher."""
        self.mock_gardebot = Mock()
        self.dispatcher = EventDispatcher(self.mock_gardebot)

    def test_dispatch_invalid_event(self) -> None:
        """Test dispatching with invalid event types."""
        payload = {"event": None}
        self.assertFalse(self.dispatcher.dispatch(payload))
        payload = {"event": 123}  # type: ignore[dict-item]
        self.assertFalse(self.dispatcher.dispatch(payload))

    def test_dispatch_missing_event(self) -> None:
        """Test dispatching with missing event key."""
        payload = {"some_other_key": "value"}
        self.assertFalse(self.dispatcher.dispatch(payload))

    @patch("gardebot.dispatcher.LOGGER")
    def test_dispatch_message_event(self, _mock_logger: Any) -> None:
        """Test dispatching a message event."""
        payload = {"event": "message"}
        self.assertTrue(self.dispatcher.dispatch(payload))
        self.mock_gardebot.handle_incoming_message.assert_called_once_with(payload)

    @patch("gardebot.dispatcher.LOGGER")
    def test_dispatch_poll_vote_event(self, _mock_logger: Any) -> None:
        """Test dispatching a poll vote event."""
        payload = {"event": "poll.vote"}
        self.assertTrue(self.dispatcher.dispatch(payload))
        self.mock_gardebot.process_vote.assert_called_once_with(payload)

    @patch("gardebot.dispatcher.LOGGER")
    def test_dispatch_session_status_event(self, _mock_logger: Any) -> None:
        """Test dispatching a session status event."""
        payload = {"event": "session.status", "payload": {"status": "CONNECTED"}}
        self.assertTrue(self.dispatcher.dispatch(payload))
        self.mock_gardebot.initialize.assert_not_called()
        payload = {"event": "session.status", "payload": {"status": "WORKING"}}
        self.assertTrue(self.dispatcher.dispatch(payload))
        self.mock_gardebot.initialize.assert_called_once()

    @patch("threading.Timer")
    @patch("gardebot.dispatcher.LOGGER")
    def test_dispatch_group_participants_event(self, _mock_logger: Any, mock_timer: Any) -> None:
        """Test dispatching a group participants event."""
        mock_timer_instance = Mock()
        mock_timer.return_value = mock_timer_instance
        payload = {"event": "group.v2.participants"}
        self.assertTrue(self.dispatcher.dispatch(payload))
        mock_timer.assert_called_once()
        mock_timer_instance.start.assert_called_once()

    @patch("gardebot.dispatcher.LOGGER")
    def test_dispatch_unhandled_event(self, mock_logger: Any) -> None:
        """Test dispatching an unhandled event."""
        payload = {"event": "unknown_event"}
        self.assertFalse(self.dispatcher.dispatch(payload))
        mock_logger.info.assert_called_once_with("unhandled_event", event="unknown_event")

    def test_dispatch_partial_match(self) -> None:
        """Test dispatching with partial event match."""
        payload = {"event": "incoming_message_notification"}
        self.assertTrue(self.dispatcher.dispatch(payload))
        self.mock_gardebot.handle_incoming_message.assert_called_once_with(payload)
