# mypy: disable-error-code="method-assign, attr-defined"
"""Unit tests for PollingAdapter."""

import unittest
from typing import Any, Dict
from unittest.mock import Mock, patch

import pandas as pd  # type: ignore[import-untyped]

from gardebot.adapters.polling import PollingAdapter
from gardebot.errors import NotFoundError
from gardebot.models.domain import Event, Sapeur


class TestPollingAdapter(unittest.TestCase):
    """Test cases for PollingAdapter."""

    def setUp(self) -> None:
        """Set up test fixtures."""
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
        )

    @patch("gardebot.adapters.polling.EventService")
    @patch("gardebot.adapters.polling.VoteService")
    @patch("gardebot.adapters.polling.OnDutyService")
    @patch("gardebot.adapters.polling.SapeurRepository")
    def test_init_default_services(
        self, mock_sapeur_repo: Any, mock_onduty_service: Any, mock_vote_service: Any, mock_event_service: Any
    ) -> None:
        """Test initialization with default services."""
        adapter = PollingAdapter()

        self.assertIsNotNone(adapter._event_service)
        self.assertIsNotNone(adapter._vote_service)
        self.assertIsNotNone(adapter._onduty_service)
        self.assertIsNotNone(adapter._sapeur_repo)

        mock_event_service.assert_called_once()
        mock_vote_service.assert_called_once()
        mock_onduty_service.assert_called_once()
        mock_sapeur_repo.assert_called_once()

    def test_init_custom_services(self) -> None:
        """Test initialization with custom services."""
        custom_event_service = Mock()
        custom_vote_service = Mock()
        custom_onduty_service = Mock()
        custom_sapeur_repo = Mock()

        adapter = PollingAdapter(
            event_service=custom_event_service,
            vote_service=custom_vote_service,
            onduty_service=custom_onduty_service,
            sapeur_repository=custom_sapeur_repo,
        )

        self.assertEqual(adapter._event_service, custom_event_service)
        self.assertEqual(adapter._vote_service, custom_vote_service)
        self.assertEqual(adapter._onduty_service, custom_onduty_service)
        self.assertEqual(adapter._sapeur_repo, custom_sapeur_repo)

    def test_extract_payload_from_data_success(self) -> None:
        """Test successful payload extraction."""
        adapter = PollingAdapter()
        data = {"payload": {"key": "value"}}

        result = adapter._extract_payload_from_data(data)

        self.assertEqual(result, {"key": "value"})

    def test_extract_payload_from_data_missing_payload(self) -> None:
        """Test payload extraction when payload is missing."""
        adapter = PollingAdapter()
        data = {"no_payload": "here"}

        with self.assertRaises(NotFoundError) as context:
            adapter._extract_payload_from_data(data)

        self.assertEqual(context.exception.detail["resource"], "payload")
        self.assertEqual(context.exception.detail["data"], data)

    def test_extract_info_from_data_success(self) -> None:
        """Test successful info extraction."""
        adapter = PollingAdapter()
        data = {"payload": {"_data": {"Info": {"Chat": "chat123", "SenderAlt": "sender123"}}}}

        result = adapter._extract_info_from_data(data)

        self.assertEqual(result, {"Chat": "chat123", "SenderAlt": "sender123"})

    def test_extract_info_from_data_missing_data(self) -> None:
        """Test info extraction when _data is missing."""
        adapter = PollingAdapter()
        data = {"payload": {"no_data": "here"}}

        with self.assertRaises(NotFoundError) as context:
            adapter._extract_info_from_data(data)

        self.assertEqual(context.exception.detail["resource"], "_data")

    def test_extract_info_from_data_missing_info(self) -> None:
        """Test info extraction when Info is missing."""
        adapter = PollingAdapter()
        data = {"payload": {"_data": {"no_info": "here"}}}

        with self.assertRaises(NotFoundError) as context:
            adapter._extract_info_from_data(data)

        self.assertEqual(context.exception.detail["resource"], "Info")

    def test_extract_chat_id_from_data_success(self) -> None:
        """Test successful chat ID extraction."""
        adapter = PollingAdapter()
        data = {"payload": {"_data": {"Info": {"Chat": "chat123@g.us"}}}}

        result = adapter._extract_chat_id_from_data(data)

        self.assertEqual(result, "chat123@g.us")

    def test_extract_chat_id_from_data_missing_chat(self) -> None:
        """Test chat ID extraction when Chat is missing."""
        adapter = PollingAdapter()
        data = {"payload": {"_data": {"Info": {"no_chat": "here"}}}}

        with self.assertRaises(NotFoundError) as context:
            adapter._extract_chat_id_from_data(data)

        self.assertEqual(context.exception.detail["resource"], "Chat")

    def test_extract_sapeur_from_payload_success(self) -> None:
        """Test successful sapeur extraction."""
        adapter = PollingAdapter()
        adapter._sapeur_repo = Mock()
        adapter._sapeur_repo.find_by_uid.return_value = self.test_sapeur

        data = {"payload": {"_data": {"Info": {"SenderAlt": "1234567890@g.us"}}}}

        result = adapter._extract_sapeur_from_payload(data)

        adapter._sapeur_repo.find_by_uid.assert_called_once_with("1234567890@c.us")
        self.assertEqual(result, self.test_sapeur)

    def test_extract_sapeur_from_payload_missing_sender(self) -> None:
        """Test sapeur extraction when SenderAlt is missing."""
        adapter = PollingAdapter()
        data = {"payload": {"_data": {"Info": {"no_sender": "here"}}}}

        with self.assertRaises(NotFoundError) as context:
            adapter._extract_sapeur_from_payload(data)

        self.assertEqual(context.exception.detail["resource"], "SenderAlt")

    def test_extract_vote_value_from_data_success(self) -> None:
        """Test successful vote value extraction."""
        adapter = PollingAdapter()
        data = {"payload": {"vote": {"selectedOptions": ["Présent"]}}}

        result = adapter._extract_vote_value_from_data(data)

        self.assertEqual(result, "Présent")

    def test_extract_vote_value_from_data_empty_selection(self) -> None:
        """Test vote value extraction with empty selection."""
        adapter = PollingAdapter()
        data: Dict[str, Any] = {"payload": {"vote": {"selectedOptions": []}}}

        result = adapter._extract_vote_value_from_data(data)

        self.assertIsNone(result)

    def test_extract_vote_value_from_data_missing_vote(self) -> None:
        """Test vote value extraction when vote is missing."""
        adapter = PollingAdapter()
        data = {"payload": {"no_vote": "here"}}

        with self.assertRaises(NotFoundError) as context:
            adapter._extract_vote_value_from_data(data)

        self.assertEqual(context.exception.detail["resource"], "vote")

    def test_extract_event_from_data_success(self) -> None:
        """Test successful event extraction."""
        adapter = PollingAdapter()
        adapter._event_service = Mock()
        adapter._event_service.find_by_poll_uid.return_value = self.test_event

        data = {"payload": {"poll": {"id": "poll_123"}}}

        result = adapter._extract_event_from_data(data)

        adapter._event_service.find_by_poll_uid.assert_called_once_with("poll_123")
        self.assertEqual(result, self.test_event)

    def test_extract_event_from_data_missing_poll(self) -> None:
        """Test event extraction when poll is missing."""
        adapter = PollingAdapter()
        data = {"payload": {"no_poll": "here"}}

        with self.assertRaises(NotFoundError) as context:
            adapter._extract_event_from_data(data)

        self.assertEqual(context.exception.detail["resource"], "poll")

    def test_extract_event_from_data_missing_poll_id(self) -> None:
        """Test event extraction when poll.id is missing."""
        adapter = PollingAdapter()
        data = {"payload": {"poll": {"no_id": "here"}}}

        with self.assertRaises(NotFoundError) as context:
            adapter._extract_event_from_data(data)

        self.assertEqual(context.exception.detail["resource"], "poll.id")

    def test_parse_vote_payload_success(self) -> None:
        """Test successful vote payload parsing."""
        adapter = PollingAdapter()
        adapter._event_service = Mock()
        adapter._event_service.find_by_poll_uid.return_value = self.test_event
        adapter._sapeur_repo = Mock()
        adapter._sapeur_repo.find_by_uid.return_value = self.test_sapeur

        data = {
            "payload": {
                "_data": {"Info": {"SenderAlt": "1234567890@g.us"}},
                "vote": {"selectedOptions": ["Présent"]},
                "poll": {"id": "poll_123"},
            }
        }

        result = adapter._parse_vote_payload(data)

        self.assertEqual(result["event"], self.test_event)
        self.assertEqual(result["sapeur"], self.test_sapeur)
        self.assertEqual(result["vote_value"], True)  # "Présent" maps to True

    def test_parse_vote_payload_invalid_vote_value(self) -> None:
        """Test vote payload parsing with invalid vote value."""
        adapter = PollingAdapter()
        adapter._event_service = Mock()
        adapter._event_service.find_by_poll_uid.return_value = self.test_event
        adapter._sapeur_repo = Mock()
        adapter._sapeur_repo.find_by_uid.return_value = self.test_sapeur

        data = {
            "payload": {
                "_data": {"Info": {"SenderAlt": "1234567890@g.us"}},
                "vote": {"selectedOptions": ["InvalidOption"]},
                "poll": {"id": "poll_123"},
            }
        }

        with self.assertRaises(ValueError) as context:
            adapter._parse_vote_payload(data)

        self.assertIn("Invalid vote value InvalidOption", str(context.exception))

    @patch("gardebot.adapters.polling.LOGGER")
    def test_process_vote_from_group_success(self, mock_logger: Any) -> None:
        """Test successful vote processing from group."""
        adapter = PollingAdapter()
        adapter._event_service = Mock()
        adapter._event_service.find_by_poll_uid.return_value = self.test_event
        adapter._sapeur_repo = Mock()
        adapter._sapeur_repo.find_by_uid.return_value = self.test_sapeur
        adapter._vote_service = Mock()
        adapter._onduty_service = Mock()
        adapter._onduty_service.is_assigned.return_value = False
        adapter._vote_service.test_event_completion.return_value = True

        data = {
            "payload": {
                "_data": {"Info": {"SenderAlt": "1234567890@g.us"}},
                "vote": {"selectedOptions": ["Présent"]},
                "poll": {"id": "poll_123"},
            }
        }

        adapter.process_vote_from_group(data)

        adapter._vote_service.record_vote.assert_called_once()
        adapter._vote_service.test_event_completion.assert_called_once_with(self.test_event)
        mock_logger.info.assert_called_with("event_ready_for_assignment", poll_string=self.test_event.poll_string)

    @patch("gardebot.adapters.polling.LOGGER")
    def test_process_vote_from_group_already_assigned(self, mock_logger: Any) -> None:
        """Test vote processing when event is already assigned."""
        adapter = PollingAdapter()
        adapter._event_service = Mock()
        adapter._event_service.find_by_poll_uid.return_value = self.test_event
        adapter._sapeur_repo = Mock()
        adapter._sapeur_repo.find_by_uid.return_value = self.test_sapeur
        adapter._onduty_service = Mock()
        adapter._onduty_service.is_assigned.return_value = True

        data = {
            "payload": {
                "_data": {"Info": {"SenderAlt": "1234567890@g.us"}},
                "vote": {"selectedOptions": ["Présent"]},
                "poll": {"id": "poll_123"},
            }
        }

        adapter.process_vote_from_group(data)

        mock_logger.info.assert_called_with("vote_ignored_event_already_assigned", poll_string=self.test_event.poll_string)

    @patch("gardebot.adapters.polling.LOGGER")
    def test_process_vote_from_group_not_found_error(self, mock_logger: Any) -> None:
        """Test vote processing with NotFoundError."""
        adapter = PollingAdapter()
        adapter._extract_event_from_data = Mock(side_effect=NotFoundError("Test error", {"detail": "test"}))

        data: Dict[str, Any] = {"payload": {}}

        adapter.process_vote_from_group(data)

        mock_logger.error.assert_called_with("vote_not_found_error", detail={"detail": "test"})

    @patch("gardebot.adapters.polling.LOGGER")
    def test_process_vote_from_group_generic_exception(self, mock_logger: Any) -> None:
        """Test vote processing with generic exception."""
        adapter = PollingAdapter()
        adapter._extract_event_from_data = Mock(side_effect=Exception("Test error"))

        data: Dict[str, Any] = {"payload": {}}

        adapter.process_vote_from_group(data)

        mock_logger.error.assert_called_with("vote_processing_error", error="Test error", data=data)

    def test_process_vote_from_admin(self) -> None:
        """Test admin vote processing (placeholder)."""
        adapter = PollingAdapter()
        data: Dict[str, Any] = {"payload": {}}

        # This should not raise an exception (placeholder implementation)
        adapter.process_vote_from_admin(data)

    @patch("gardebot.adapters.polling.pd")
    @patch("gardebot.adapters.polling.LOGGER")
    def test_should_be_published_already_published(self, mock_logger: Any, mock_pd: Any) -> None:
        """Test should_be_published when event is already published."""
        # Set pd.Timestamp.now().date() to a real date to avoid TypeError
        mock_today = pd.Timestamp("2024-01-01").date()
        mock_pd.Timestamp.now.return_value.date.return_value = mock_today

        adapter = PollingAdapter()
        event_with_poll_uid = Event(
            title="Test",
            location="Test",
            start_date=pd.Timestamp("2024-01-01 08:00:00"),
            end_date=pd.Timestamp("2024-01-01 18:00:00"),
            published_date=pd.Timestamp("2024-01-01 07:00:00"),
            headcount=5,
            poll_uid="existing_uid",
        )

        result = adapter.should_be_published(event_with_poll_uid)

        self.assertFalse(result)
        mock_logger.debug.assert_called_with("event_already_published", poll_string=event_with_poll_uid.poll_string)

    def test_send_poll_success(self) -> None:
        """Test successful poll sending."""
        adapter = PollingAdapter()
        adapter.session = "test_session"
        adapter.post = Mock()
        adapter.extract_json_dict = Mock(return_value={"id": "poll_123"})

        mock_response = Mock()
        adapter.post.return_value = mock_response

        result = adapter.send_poll("chat123", "Test Poll", ["Option 1", "Option 2"], True)

        expected_payload = {
            "chatId": "chat123",
            "poll": {"name": "Test Poll", "options": ["Option 1", "Option 2"], "multipleAnswers": True},
            "session": "test_session",
        }

        adapter.post.assert_called_once_with("/api/sendPoll", json_body=expected_payload, raise_for_status=True)
        adapter.extract_json_dict.assert_called_once_with(mock_response)
        self.assertEqual(result, {"id": "poll_123"})

    @patch("gardebot.adapters.polling.LOGGER")
    def test_send_poll_logging(self, mock_logger: Any) -> None:
        """Test that poll sending is logged."""
        adapter = PollingAdapter()
        adapter.session = "test_session"
        adapter.post = Mock()
        adapter.extract_json_dict = Mock(return_value={"id": "poll_123"})

        adapter.send_poll("chat123", "Test Poll", ["Option 1"])

        mock_logger.debug.assert_called_with("sending_poll", to="chat123", title="Test Poll")
        mock_logger.info.assert_called_with("poll_sent", to="chat123", poll_id="poll_123")

    def test_list_events_wrapper(self) -> None:
        """Test list_events wrapper method."""
        adapter = PollingAdapter()
        adapter._event_service = Mock()
        expected_events = [self.test_event]
        adapter._event_service.list_events.return_value = expected_events

        result = adapter.list_events()

        adapter._event_service.list_events.assert_called_once()
        self.assertEqual(result, expected_events)

    def test_assign_poll_uid_wrapper(self) -> None:
        """Test assign_poll_uid wrapper method."""
        adapter = PollingAdapter()
        adapter._event_service = Mock()
        adapter._event_service.assign_poll_uid.return_value = self.test_event

        result = adapter.assign_poll_uid(self.test_event, "new_poll_uid")

        adapter._event_service.assign_poll_uid.assert_called_once_with(event=self.test_event, poll_uid="new_poll_uid")
        self.assertEqual(result, self.test_event)

    def test_extract_vote_value_from_data_missing_selected_options(self) -> None:
        """Test vote value extraction when selectedOptions is missing."""
        adapter = PollingAdapter()
        data = {"payload": {"vote": {"no_selected_options": "here"}}}

        with self.assertRaises(NotFoundError) as context:
            adapter._extract_vote_value_from_data(data)

        self.assertEqual(context.exception.detail["resource"], "vote.selectedOptions")

    @patch("gardebot.adapters.polling.pd")
    @patch("gardebot.adapters.polling.LOGGER")
    def test_should_be_published_not_due_yet(self, mock_logger: Any, mock_pd: Any) -> None:
        """Test should_be_published when event is not due yet."""
        # Mock today's date to be before the publication date
        mock_today = Mock()
        mock_pd.Timestamp.now.return_value.date.return_value = mock_today

        adapter = PollingAdapter()
        event_not_due = Event(
            title="Future Event",
            location="Test Location",
            start_date=pd.Timestamp("2025-01-01 08:00:00"),
            end_date=pd.Timestamp("2025-01-01 18:00:00"),
            headcount=5,
        )

        # Make the scheduled publication date appear to be in the future
        mock_publication_date = Mock()
        mock_publication_date.date.return_value = Mock()
        event_not_due.scheduled_publication_date = mock_publication_date
        event_not_due.scheduled_publication_date.date.return_value.__gt__ = Mock(return_value=True)

        result = adapter.should_be_published(event_not_due)

        self.assertFalse(result)
        mock_logger.debug.assert_called_with("event_not_due_yet", poll_string=event_not_due.poll_string)

    @patch("gardebot.adapters.polling.pd")
    @patch("gardebot.adapters.polling.LOGGER")
    def test_should_be_published_already_assigned(self, mock_logger: Any, mock_pd: Any) -> None:
        """Test should_be_published when event is already assigned."""
        # Mock today's date
        mock_today = Mock()
        mock_pd.Timestamp.now.return_value.date.return_value = mock_today

        adapter = PollingAdapter()
        adapter._onduty_service = Mock()
        adapter._onduty_service.is_assigned.return_value = True

        event_assigned = Event(
            title="Assigned Event",
            location="Test Location",
            start_date=pd.Timestamp("2024-01-01 08:00:00"),
            end_date=pd.Timestamp("2024-01-01 18:00:00"),
            headcount=5,
        )

        # Make the scheduled publication date appear to be in the past
        mock_publication_date = Mock()
        event_assigned.scheduled_publication_date = mock_publication_date
        event_assigned.scheduled_publication_date.date.return_value.__gt__ = Mock(return_value=False)

        result = adapter.should_be_published(event_assigned)

        self.assertFalse(result)
        mock_logger.debug.assert_called_with("poll_already_assigned", poll_string=event_assigned.poll_string)

    @patch("gardebot.adapters.polling.pd")
    def test_should_be_published_ready_for_publication(self, mock_pd: Any) -> None:
        """Test should_be_published when event is ready for publication."""
        # Mock today's date
        mock_today = Mock()
        mock_pd.Timestamp.now.return_value.date.return_value = mock_today

        adapter = PollingAdapter()
        adapter._onduty_service = Mock()
        adapter._onduty_service.is_assigned.return_value = False

        event_ready = Event(
            title="Ready Event",
            location="Test Location",
            start_date=pd.Timestamp("2024-01-01 08:00:00"),
            end_date=pd.Timestamp("2024-01-01 18:00:00"),
            headcount=5,
        )

        # Make the scheduled publication date appear to be in the past
        mock_publication_date = Mock()
        event_ready.scheduled_publication_date = mock_publication_date
        event_ready.scheduled_publication_date.date.return_value.__gt__ = Mock(return_value=False)

        result = adapter.should_be_published(event_ready)

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
