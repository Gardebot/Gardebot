# mypy: disable-error-code="method-assign, attr-defined, index"
"""Unit tests for MessagingAdapter - clean version."""

import unittest
from typing import Any
from unittest.mock import Mock, patch

import pandas as pd  # type: ignore[import-untyped]

from gardebot.adapters.messaging import MessagingAdapter
from gardebot.config import EM_NAME, GROUP_ID_GARDE_ET_PIQUET
from gardebot.errors import NotFoundError
from gardebot.models.domain import Event, OnDutyAssignment, Sapeur


class TestMessagingAdapter(unittest.TestCase):
    """Test cases for MessagingAdapter."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Create test data
        self.test_sapeur = Sapeur(
            uid="1234567890@c.us",
            name="Test User",
            pushname="TestUser",
            phone="+41123456789",
            joined_date=pd.Timestamp("2023-01-01"),
            group_id="test_group",
        )

        self.test_event = Event(
            title="Test Event",
            location="Test Location",
            start_date=pd.Timestamp("2024-01-01 08:00:00"),
            end_date=pd.Timestamp("2024-01-01 18:00:00"),
            headcount=5,
            poll_uid="test_poll_uid",
        )

        self.test_assignment = OnDutyAssignment(event=self.test_event, sapeur_list=[self.test_sapeur])

    @patch("gardebot.adapters.messaging.VoteService")
    def test_init_default_vote_service(self, mock_vote_service: Any) -> None:
        """Test initialization with default VoteService."""
        adapter = MessagingAdapter()
        self.assertIsNotNone(adapter._vote_service)
        mock_vote_service.assert_called_once()

    def test_init_custom_vote_service(self) -> None:
        """Test initialization with custom VoteService."""
        custom_service = Mock()
        adapter = MessagingAdapter(vote_service=custom_service)
        self.assertEqual(adapter._vote_service, custom_service)

    def test_send_text_success(self) -> None:
        """Test successful text message sending."""
        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.session = "test_session"
        adapter._post_json = Mock(return_value={"id": "msg123", "status": "sent"})

        result = adapter.send_text("1234567890@c.us", "Test message")

        expected_payload = {"session": "test_session", "chatId": "1234567890@c.us", "text": "Test message"}
        adapter._post_json.assert_called_once_with("/api/sendText", expected_payload)
        self.assertEqual(result, {"id": "msg123", "status": "sent"})

    @patch("gardebot.adapters.messaging.LOGGER")
    def test_send_text_truncates_log_message(self, mock_logger: Any) -> None:
        """Test that long messages are truncated in logs."""
        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter._post_json = Mock(return_value={})

        long_message = "A" * 100
        adapter.send_text("1234567890@c.us", long_message)

        mock_logger.info.assert_called_once()
        args = mock_logger.info.call_args[1]
        self.assertEqual(len(args["text_excerpt"]), 60)

    def test_send_event_without_poll_uid(self) -> None:
        """Test sending event without poll_uid."""
        event_without_poll = Event(
            title="Test Event",
            location="Test Location",
            start_date=pd.Timestamp("2024-01-01 08:00:00"),
            end_date=pd.Timestamp("2024-01-01 18:00:00"),
            headcount=5,
        )

        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.session = "test_session"
        adapter._post_json = Mock(return_value={"id": "event123"})

        result = adapter.send_event("1234567890@c.us", event_without_poll)

        # Verify the call was made and payload structure
        adapter._post_json.assert_called_once()
        call_args = adapter._post_json.call_args
        endpoint = call_args[0][0]
        payload = call_args[0][1]

        self.assertEqual(endpoint, "/api/test_session/events")
        self.assertEqual(payload["chatId"], "1234567890@c.us")
        self.assertNotIn("reply_to", payload)
        self.assertEqual(result, {"id": "event123"})

    def test_send_event_with_poll_uid(self) -> None:
        """Test sending event with poll_uid."""
        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.session = "test_session"
        adapter._post_json = Mock(return_value={"id": "event123"})

        adapter.send_event("1234567890@c.us", self.test_event)

        call_args = adapter._post_json.call_args[0]
        payload = call_args[1]
        self.assertIn("reply_to", payload)
        self.assertEqual(payload["reply_to"], "test_poll_uid")

    def test_get_message_success(self) -> None:
        """Test successful message retrieval."""
        expected_response = {"id": "msg123", "text": "Test message"}
        mock_response = Mock()

        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.session = "test_session"
        adapter.get = Mock(return_value=mock_response)
        adapter.extract_json_dict = Mock(return_value=expected_response)

        result = adapter.get_message("chat123", "msg123")

        expected_endpoint = "/api/test_session/chats/chat123/messages/msg123"
        adapter.get.assert_called_once_with(expected_endpoint, raise_for_status=True)
        adapter.extract_json_dict.assert_called_once_with(mock_response)
        self.assertEqual(result, expected_response)

    def test_build_mentions_payload_without_reply(self) -> None:
        """Test building mentions payload without reply_to."""
        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.session = "test_session"

        sapeur_list = [self.test_sapeur]
        result = adapter._build_mentions_payload("chat123", sapeur_list)

        expected_payload = {"session": "test_session", "chatId": "chat123", "text": "@41123456789", "mentions": ["1234567890@c.us"]}
        self.assertEqual(result, expected_payload)
        self.assertNotIn("reply_to", result)

    def test_build_mentions_payload_with_reply(self) -> None:
        """Test building mentions payload with reply_to."""
        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.session = "test_session"

        sapeur_list = [self.test_sapeur]
        result = adapter._build_mentions_payload("chat123", sapeur_list, "reply123")

        expected_payload = {
            "session": "test_session",
            "chatId": "chat123",
            "text": "@41123456789",
            "mentions": ["1234567890@c.us"],
            "reply_to": "reply123",
        }
        self.assertEqual(result, expected_payload)

    def test_build_mentions_payload_multiple_sapeurs(self) -> None:
        """Test building mentions payload with multiple sapeurs."""
        sapeur2 = Sapeur(
            uid="0987654321@c.us",
            name="Test User 2",
            pushname="TestUser2",
            phone="+41987654321",
            joined_date=pd.Timestamp("2023-01-01"),
            group_id="test_group",
        )

        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.session = "test_session"

        sapeur_list = [self.test_sapeur, sapeur2]
        result = adapter._build_mentions_payload("chat123", sapeur_list)

        self.assertEqual(result["text"], "@41123456789, @41987654321")
        self.assertEqual(result["mentions"], ["1234567890@c.us", "0987654321@c.us"])

    def test_post_json_success(self) -> None:
        """Test successful JSON POST."""
        expected_response = {"status": "success"}
        mock_response = Mock()

        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.post = Mock(return_value=mock_response)
        adapter.extract_json_dict = Mock(return_value=expected_response)

        result = adapter._post_json("/test/endpoint", {"key": "value"})

        adapter.post.assert_called_once_with("/test/endpoint", json_body={"key": "value"}, raise_for_status=True)
        adapter.extract_json_dict.assert_called_once_with(mock_response)
        self.assertEqual(result, expected_response)

    def test_build_vote_reminder_payload_with_recipients(self) -> None:
        """Test building vote reminder payload with recipients."""
        mock_vote_service = Mock()
        mock_vote_service.list_non_responding.return_value = [self.test_sapeur]

        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.session = "test_session"

        result = adapter._build_vote_reminder_payload(self.test_event)

        self.assertIsNotNone(result)
        self.assertIn("text", result)  # type: ignore[arg-type]
        self.assertIn("Bonjour, merci à @41123456789 de répondre au sondage", result["text"])
        self.assertEqual(result["chatId"], GROUP_ID_GARDE_ET_PIQUET)
        self.assertEqual(result["reply_to"], "test_poll_uid")

    def test_build_vote_reminder_payload_no_recipients(self) -> None:
        """Test building vote reminder payload with no recipients."""
        mock_vote_service = Mock()
        mock_vote_service.list_non_responding.return_value = []

        adapter = MessagingAdapter(vote_service=mock_vote_service)

        result = adapter._build_vote_reminder_payload(self.test_event)

        self.assertIsNone(result)

    def test_build_vote_reminder_filters_em_names(self) -> None:
        """Test that EM_NAME sapeurs are filtered out."""
        if EM_NAME:  # Only test if EM_NAME is not empty
            em_sapeur = Sapeur(
                uid="em@c.us",
                name=EM_NAME[0],
                pushname="EM",
                phone="+41000000000",
                joined_date=pd.Timestamp("2023-01-01"),
                group_id="test_group",
            )

            mock_vote_service = Mock()
            mock_vote_service.list_non_responding.return_value = [self.test_sapeur, em_sapeur]

            adapter = MessagingAdapter(vote_service=mock_vote_service)
            adapter.session = "test_session"

            result = adapter._build_vote_reminder_payload(self.test_event)

            self.assertIsNotNone(result)
            self.assertNotIn(em_sapeur.uid, result["mentions"])
            self.assertIn(self.test_sapeur.uid, result["mentions"])

    def test_send_vote_reminder_success(self) -> None:
        """Test successful vote reminder sending."""
        mock_vote_service = Mock()
        mock_vote_service.list_non_responding.return_value = [self.test_sapeur]

        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.session = "test_session"
        adapter.endpoint = "/api/sendText"
        adapter._post_json = Mock(return_value={"id": "reminder123"})

        result = adapter.send_vote_reminder(self.test_event)

        self.assertEqual(result, {"id": "reminder123"})
        adapter._post_json.assert_called_once()

    def test_send_vote_reminder_no_recipients_raises_error(self) -> None:
        """Test that sending vote reminder with no recipients raises NotFoundError."""
        mock_vote_service = Mock()
        mock_vote_service.list_non_responding.return_value = []

        adapter = MessagingAdapter(vote_service=mock_vote_service)

        with self.assertRaises(NotFoundError) as context:
            adapter.send_vote_reminder(self.test_event)

        self.assertEqual(context.exception.detail["poll_string"], self.test_event.poll_string)

    def test_send_group_convocation_success(self) -> None:
        """Test successful group convocation sending."""
        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter.session = "test_session"
        adapter.endpoint = "/api/sendText"
        adapter._post_json = Mock(return_value={"id": "convocation123"})

        result = adapter.send_group_convocation("chat123", self.test_assignment)

        self.assertEqual(result, {"id": "convocation123"})
        adapter._post_json.assert_called_once()

        call_args = adapter._post_json.call_args[0]
        payload = call_args[1]
        self.assertIn("Merci à @41123456789 pour la garde:", payload["text"])
        self.assertIn("Vous êtes convoqué.e.s.", payload["text"])

    def test_send_private_convocation_success(self) -> None:
        """Test successful private convocation sending."""
        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)

        with patch.object(adapter, "send_event", return_value={"id": "private_conv123"}) as mock_send_event:
            result = adapter.send_private_convocation("1234567890@c.us", self.test_event)

            mock_send_event.assert_called_once_with(to_number="1234567890@c.us", event=self.test_event)
            self.assertEqual(result, {"id": "private_conv123"})

    def test_endpoint_initialization(self) -> None:
        """Test that endpoint is properly initialized."""
        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        self.assertEqual(adapter.endpoint, "/api/sendText")

    @patch("gardebot.adapters.messaging.LOGGER")
    def test_logging_in_send_methods(self, mock_logger: Any) -> None:
        """Test that logging is properly called in send methods."""
        mock_vote_service = Mock()
        adapter = MessagingAdapter(vote_service=mock_vote_service)
        adapter._post_json = Mock(return_value={})

        # Test send_text logging
        adapter.send_text("1234567890@c.us", "Test message")
        mock_logger.info.assert_called()

        mock_logger.reset_mock()

        # Test send_event logging
        adapter.session = "test_session"
        adapter.send_event("1234567890@c.us", self.test_event)
        mock_logger.debug.assert_called()


if __name__ == "__main__":
    unittest.main()
