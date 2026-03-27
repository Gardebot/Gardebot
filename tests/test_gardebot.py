# mypy: disable-error-code="method-assign, attr-defined"
"""Unit tests for gardebot main module."""

import unittest
from datetime import date
from unittest.mock import Mock, patch

from gardebot.gardebot import Gardebot


class TestGardebot(unittest.TestCase):
    """Test cases for Gardebot class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        with (
            patch("gardebot.gardebot.EventService"),
            patch("gardebot.gardebot.VoteService"),
            patch("gardebot.gardebot.OnDutyService"),
            patch("gardebot.gardebot.SapeurService"),
            patch("gardebot.gardebot.MessageService"),
            patch("gardebot.gardebot.PollService"),
        ):
            self.gardebot = Gardebot()

    def test_init(self) -> None:
        """Test Gardebot initialization."""
        self.assertIsNotNone(self.gardebot.event_service)
        self.assertIsNotNone(self.gardebot.vote_service)
        self.assertIsNotNone(self.gardebot.onduty_service)
        self.assertIsNotNone(self.gardebot.sapeur_service)
        self.assertIsNotNone(self.gardebot.message_service)
        self.assertIsNotNone(self.gardebot.poll_service)

    def test_handle_incoming_message(self) -> None:
        """Test handling incoming message."""
        data = {"event": "message", "payload": {}}
        self.gardebot.handle_incoming_message(data)
        self.gardebot.message_service.handle_webhook_payload.assert_called_once_with(data)

    def test_handle_incoming_vote(self) -> None:
        """Test handling incoming vote."""
        data = {"event": "poll.vote", "payload": {}}
        self.gardebot.handle_incoming_vote(data)
        self.gardebot.poll_service.handle_webhook_payload.assert_called_once_with(data)

    def test_assign_on_duty_for_events_success(self) -> None:
        """Test successful on-duty assignment."""
        mock_event = Mock()
        mock_event.poll_string = "test_poll"
        mock_assignment = Mock()
        mock_assignment.sapeur_list = [Mock(name="John"), Mock(name="Jane")]

        self.gardebot.event_service.list_events.return_value = [mock_event]
        self.gardebot.vote_service.test_event_completion.return_value = True
        self.gardebot.onduty_service.is_assigned.return_value = False
        self.gardebot.onduty_service.process_assignment.return_value = mock_assignment

        with patch("gardebot.gardebot.LOGGER") as mock_logger:
            self.gardebot.assign_on_duty_for_events()

        self.gardebot.message_service.send_convocation.assert_called_once_with(assignment=mock_assignment)
        mock_logger.info.assert_called_once()

    def test_assign_on_duty_for_events_already_assigned(self) -> None:
        """Test on-duty assignment when already assigned."""
        mock_event = Mock()
        self.gardebot.event_service.list_events.return_value = [mock_event]
        self.gardebot.vote_service.test_event_completion.return_value = True
        self.gardebot.onduty_service.is_assigned.return_value = True

        self.gardebot.assign_on_duty_for_events()

        self.gardebot.onduty_service.process_assignment.assert_not_called()
        self.gardebot.message_service.send_convocation.assert_not_called()

    def test_assign_on_duty_for_events_error(self) -> None:
        """Test on-duty assignment with error."""
        mock_event = Mock()
        mock_event.poll_string = "test_poll"
        self.gardebot.event_service.list_events.return_value = [mock_event]
        self.gardebot.vote_service.test_event_completion.side_effect = Exception("Test error")

        with patch("gardebot.gardebot.LOGGER") as mock_logger:
            self.gardebot.assign_on_duty_for_events()

        mock_logger.error.assert_called_once()

    def test_initialize_success(self) -> None:
        """Test successful initialization."""
        with patch("gardebot.gardebot.LOGGER") as mock_logger:
            self.gardebot.initialize()

        self.gardebot.event_service.synchronize_events.assert_called_once()
        self.gardebot.sapeur_service.synchronize_sapeurs.assert_called_once()
        self.gardebot.vote_service.create.assert_called_once_with(overwrite=False)
        self.gardebot.onduty_service.create.assert_called_once_with(overwrite=False)
        mock_logger.debug.assert_called()

    def test_initialize_error(self) -> None:
        """Test initialization with error."""
        self.gardebot.event_service.synchronize_events.side_effect = Exception("Test error")

        with patch("gardebot.gardebot.LOGGER") as mock_logger:
            self.gardebot.initialize()

        mock_logger.exception.assert_called_once()

    @patch("gardebot.gardebot.os.environ.get")
    def test_notify_admin(self, mock_env_get: Mock) -> None:
        """Test admin notification."""
        mock_env_get.return_value = "1234567890"
        self.gardebot._notify_admin("Test message")

        self.gardebot.message_service.send_text.assert_called_once_with(to_number="1234567890", text="Test message")

    @patch("gardebot.gardebot.pd.Timestamp")
    @patch("gardebot.gardebot.holidays.country_holidays")
    def test_send_holiday_warning(self, mock_holidays: Mock, mock_timestamp: Mock) -> None:
        """Test holiday warning."""

        mock_now = Mock()
        mock_now.date.return_value = date(2023, 12, 20)
        mock_now.year = 2023
        mock_timestamp.now.return_value = mock_now

        mock_holidays.return_value = {
            date(2023, 12, 25): "Christmas",
            date(2023, 12, 23): "Test Holiday",  # 3 days from "now"
        }

        with patch("gardebot.gardebot.PREVENTION_DAY_BEFORE_HOLIDAY", 3):
            self.gardebot.send_holiday_warning()

        # Should send notification for Test Holiday (3 days away)
        self.gardebot.message_service.send_text.assert_called()

    def test_reminders(self) -> None:
        """Test sending reminders."""
        mock_event = Mock()
        mock_event.poll_string = "test_poll"
        mock_event.should_send_reminder.return_value = True
        mock_event.nb_reminder = 1

        updated_event = Mock()
        updated_event.poll_string = "test_poll"
        updated_event.nb_reminder = 2

        self.gardebot.event_service.list_events.return_value = [mock_event]
        self.gardebot.onduty_service.is_assigned.return_value = False
        self.gardebot.event_service.increment_reminder.return_value = updated_event

        with patch("gardebot.gardebot.LOGGER") as mock_logger:
            self.gardebot.reminders()

        self.gardebot.message_service.send_vote_reminder.assert_called_once_with(event=mock_event)
        mock_logger.info.assert_called_once()

    def test_reminders_error(self) -> None:
        """Test reminders with error."""
        mock_event = Mock()
        mock_event.poll_string = "test_poll"
        mock_event.should_send_reminder.return_value = True

        self.gardebot.event_service.list_events.return_value = [mock_event]
        self.gardebot.onduty_service.is_assigned.return_value = False
        self.gardebot.message_service.send_vote_reminder.side_effect = Exception("Test error")

        with patch("gardebot.gardebot.LOGGER") as mock_logger:
            self.gardebot.reminders()

        mock_logger.error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
