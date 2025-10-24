"""Unit tests for PollService."""

import os
import unittest
from unittest.mock import Mock, patch

from gardebot.errors import ExternalServiceError, NotFoundError
from gardebot.services.poll_service import PollService


class TestPollService(unittest.TestCase):
    """Test PollService class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        with patch("gardebot.services.poll_service.PollingAdapter"), patch("gardebot.services.poll_service.MessageService"):
            self.service = PollService()

        self.mock_polling = Mock()
        self.mock_message_service = Mock()
        self.service.polling = self.mock_polling
        self.service.message_service = self.mock_message_service

    @patch("gardebot.services.poll_service.GROUP_ID_GARDE_ET_PIQUET", "group-123")
    def test_handle_webhook_payload_group_vote(self) -> None:
        """Test handling webhook payload from group."""
        data = {"test": "data"}
        self.mock_polling._extract_chat_id_from_data.return_value = "group-123"
        self.mock_polling.process_vote_from_group.return_value = None

        self.service.handle_webhook_payload(data)

        self.mock_polling._extract_chat_id_from_data.assert_called_once_with(data)
        self.mock_polling.process_vote_from_group.assert_called_once_with(data)

    @patch.dict(os.environ, {"ADMIN_NUMBER": "+41999999999"})
    def test_handle_webhook_payload_admin_vote(self) -> None:
        """Test handling webhook payload from admin."""
        data = {"test": "data"}
        self.mock_polling._extract_chat_id_from_data.return_value = "+41999999999"
        self.mock_polling.process_vote_from_admin.return_value = None

        self.service.handle_webhook_payload(data)

        self.mock_polling._extract_chat_id_from_data.assert_called_once_with(data)
        self.mock_polling.process_vote_from_admin.assert_called_once_with(data)

    @patch.dict(os.environ, {"ADMIN_NUMBER": "+41999999999"})
    def test_handle_webhook_payload_unknown_chat(self) -> None:
        """Test handling webhook payload from unknown chat."""
        data = {"test": "data"}
        unknown_chat = "+41123456789"
        self.mock_polling._extract_chat_id_from_data.return_value = unknown_chat

        self.service.handle_webhook_payload(data)

        self.mock_message_service.send_text.assert_called_once_with(
            to_number="+41999999999", text=f"Vote received from unknown chat_id: {unknown_chat}"
        )

    def test_handle_webhook_payload_not_found_error(self) -> None:
        """Test handling webhook payload with NotFoundError."""
        data = {"test": "data"}
        self.mock_polling._extract_chat_id_from_data.side_effect = NotFoundError("Test error")

        # Should not raise, just log the error
        self.service.handle_webhook_payload(data)

    def test_handle_webhook_payload_external_error(self) -> None:
        """Test handling webhook payload with ExternalServiceError."""
        data = {"test": "data"}
        self.mock_polling._extract_chat_id_from_data.side_effect = ExternalServiceError("Test error")

        # Should not raise, just log the error
        self.service.handle_webhook_payload(data)

    @patch("gardebot.services.poll_service.GROUP_ID_GARDE_ET_PIQUET", "group-123")
    @patch("gardebot.services.poll_service.VOTE_OPTIONS", {"Present": "Présent", "Absent": "Absent"})
    def test_publish_polls_success(self) -> None:
        """Test successful poll publishing."""
        mock_event = Mock()
        mock_event.poll_string = "test_poll"
        events = [mock_event]

        self.mock_polling.list_events.return_value = events
        self.mock_polling.should_be_published.return_value = True
        self.mock_polling.send_poll.return_value = {"id": "poll-123"}
        self.mock_polling.assign_poll_uid.return_value = None
        self.mock_polling.mark_published.return_value = None

        self.service.publish_polls()

        self.mock_polling.send_poll.assert_called_once_with(
            to_conv="group-123", poll_title="test_poll", poll_options=["Present", "Absent"], multiple_answers=False
        )
        self.mock_polling.mark_published.assert_called_once_with(event=mock_event, poll_uid="poll-123")

    def test_publish_polls_no_events_to_publish(self) -> None:
        """Test publishing when no events need publishing."""
        mock_event = Mock()
        events = [mock_event]

        self.mock_polling.list_events.return_value = events
        self.mock_polling.should_be_published.return_value = False

        self.service.publish_polls()

        self.mock_polling.send_poll.assert_not_called()

    def test_publish_polls_send_error(self) -> None:
        """Test poll publishing with send error."""
        mock_event = Mock()
        mock_event.poll_string = "test_poll"
        events = [mock_event]

        self.mock_polling.list_events.return_value = events
        self.mock_polling.should_be_published.return_value = True
        self.mock_polling.send_poll.side_effect = ExternalServiceError("Send failed")

        # Should not raise, just continue
        self.service.publish_polls()

        self.mock_polling.assign_poll_uid.assert_not_called()
        self.mock_polling.mark_published.assert_not_called()

    def test_publish_polls_missing_poll_id(self) -> None:
        """Test poll publishing with missing poll ID in response."""
        mock_event = Mock()
        mock_event.poll_string = "test_poll"
        events = [mock_event]

        self.mock_polling.list_events.return_value = events
        self.mock_polling.should_be_published.return_value = True
        self.mock_polling.send_poll.return_value = {"status": "sent"}  # Missing 'id'

        with self.assertRaises(NotFoundError):
            self.service.publish_polls()


if __name__ == "__main__":
    unittest.main()
