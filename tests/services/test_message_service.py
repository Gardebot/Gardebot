"""Unit tests for MessageService."""

import os
import unittest
from unittest.mock import Mock, patch

from gardebot.errors import ExternalServiceError, NotFoundError
from gardebot.models.domain import Event, OnDutyAssignment, Sapeur
from gardebot.services.message_service import MessageService


class TestMessageService(unittest.TestCase):
    """Test MessageService class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        with patch("gardebot.services.message_service.MessagingAdapter"):
            self.service = MessageService()

        self.mock_messaging = Mock()
        self.service.messaging = self.mock_messaging

        self.sample_event = Event(
            title="Test Event",
            location="Test Location",
            start_date="2025-10-24T10:00:00+01:00",
            end_date="2025-10-24T18:00:00+01:00",
            headcount=3,
            poll_uid="test-poll-123",
        )

        self.sample_sapeur = Sapeur(
            uid="test-uid-123", name="John Doe", pushname="John", phone="+41123456789", joined_date="2025-10-01", group_id="test-group"
        )

        self.sample_assignment = OnDutyAssignment(event=self.sample_event, sapeur_list=[self.sample_sapeur], assigned=True)

    def test_handle_webhook_payload_missing_payload(self) -> None:
        """Test handling webhook with missing payload."""
        data = {"no_payload": "test"}

        with self.assertRaises(NotFoundError):
            self.service.handle_webhook_payload(data)

    def test_handle_webhook_payload_success(self) -> None:
        """Test successful webhook payload handling."""
        data = {"payload": {"body": "Test message", "from": "+41123456789", "timestamp": "2025-10-23T12:00:00Z"}}

        with patch.object(self.service, "_echo") as mock_echo:
            self.service.handle_webhook_payload(data)
            mock_echo.assert_called_once_with("Test message", "+41123456789", "2025-10-23T12:00:00Z")

    def test_handle_webhook_payload_external_error(self) -> None:
        """Test webhook handling with external service error."""
        data = {"payload": {"body": "Test message", "from": "+41123456789", "timestamp": "2025-10-23T12:00:00Z"}}

        with patch.object(self.service, "_echo", side_effect=ExternalServiceError("Test error")):
            # Should not raise, just log the error
            self.service.handle_webhook_payload(data)

    @patch.dict(os.environ, {"BOT_NUMBER": "+41999999999"})
    def test_echo_skip_bot_message(self) -> None:
        """Test echo skips bot messages."""
        with patch("gardebot.services.message_service.LOGGER") as mock_logger:
            self.service._echo("Test message", "+41999999999", "timestamp")
            self.mock_messaging.send_text.assert_not_called()
            mock_logger.debug.assert_called_with("message_echo_skipped_bot", sender="+41999999999")

    @patch.dict(os.environ, {"BOT_NUMBER": "+41000000000"}, clear=True)
    @patch("gardebot.services.message_service.GROUP_ID_GARDE_ET_PIQUET", "group-123")
    def test_echo_skip_group_chat(self) -> None:
        """Test echo skips group chat messages."""
        with patch("gardebot.services.message_service.LOGGER") as mock_logger:
            self.service._echo("Test message", "group-123", "timestamp")
            self.mock_messaging.send_text.assert_not_called()
            mock_logger.debug.assert_called_with("message_echo_skipped_group_chat", sender="group-123")

    @patch.dict(os.environ, {"BOT_NUMBER": "+41000000000"}, clear=True)
    @patch("gardebot.services.message_service.GROUP_ID_GARDE_ET_PIQUET", "different-group")
    def test_echo_success(self) -> None:
        """Test successful echo."""
        self.service._echo("Test message", "+41123456789", "timestamp")

        expected_text = "Echoing, you sent : 'Test message' at timestamp"
        self.mock_messaging.send_text.assert_called_once_with(to_number="+41123456789", text=expected_text)

    def test_send_convocation_missing_poll_uid(self) -> None:
        """Test send convocation with missing poll UID."""
        event_without_poll = Event(
            title="Test Event",
            location="Test Location",
            start_date="2025-10-24T10:00:00+01:00",
            end_date="2025-10-24T18:00:00+01:00",
            headcount=3,
        )
        assignment = OnDutyAssignment(event=event_without_poll, sapeur_list=[self.sample_sapeur], assigned=True)

        with self.assertRaises(NotFoundError):
            self.service.send_convocation(assignment)

    @patch("gardebot.services.message_service.GROUP_ID_GARDE_ET_PIQUET", "group-123")
    def test_send_convocation_success(self) -> None:
        """Test successful convocation sending."""
        self.mock_messaging.send_group_convocation.return_value = {"status": "sent"}
        self.mock_messaging.send_private_convocation.return_value = {"status": "sent"}

        result = self.service.send_convocation(self.sample_assignment)

        self.assertIn("group", result)
        self.assertIn("private", result)
        self.assertEqual(len(result["private"]), 1)
        self.mock_messaging.send_group_convocation.assert_called_once()
        self.mock_messaging.send_private_convocation.assert_called_once()

    @patch("gardebot.services.message_service.GROUP_ID_GARDE_ET_PIQUET", "group-123")
    def test_send_convocation_private_error(self) -> None:
        """Test convocation with private message error."""
        self.mock_messaging.send_group_convocation.return_value = {"status": "sent"}
        self.mock_messaging.send_private_convocation.side_effect = ExternalServiceError("Private error")

        result = self.service.send_convocation(self.sample_assignment)

        self.assertIn("group", result)
        self.assertIn("private", result)
        self.assertEqual(len(result["private"]), 1)
        self.assertIn("error", result["private"][0])

    def test_send_text(self) -> None:
        """Test send_text wrapper."""
        expected_result = {"status": "sent"}
        self.mock_messaging.send_text.return_value = expected_result

        result = self.service.send_text("+41123456789", "Test message")

        self.assertEqual(result, expected_result)
        self.mock_messaging.send_text.assert_called_once_with(to_number="+41123456789", text="Test message")

    def test_send_vote_reminder(self) -> None:
        """Test send_vote_reminder wrapper."""
        expected_result = {"status": "sent"}
        self.mock_messaging.send_vote_reminder.return_value = expected_result

        result = self.service.send_vote_reminder(self.sample_event)

        self.assertEqual(result, expected_result)
        self.mock_messaging.send_vote_reminder.assert_called_once_with(event=self.sample_event)

    @patch.dict(os.environ, {"BOT_NUMBER": "+41000000000"}, clear=True)
    @patch("gardebot.services.message_service.GROUP_ID_GARDE_ET_PIQUET", "different-group")
    def test_echo_success_with_debug_logging(self) -> None:
        """Test successful echo with debug logging enabled."""
        with patch("gardebot.services.message_service.LOGGER") as mock_logger:
            self.service._echo("Test message", "+41123456789", "timestamp")

            # Verify debug log is called
            mock_logger.debug.assert_called_with("message_echo_sent", sender="+41123456789", body="Test message")

            expected_text = "Echoing, you sent : 'Test message' at timestamp"
            self.mock_messaging.send_text.assert_called_once_with(to_number="+41123456789", text=expected_text)


if __name__ == "__main__":
    unittest.main()
