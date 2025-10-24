# mypy: disable-error-code="method-assign, attr-defined"
"""Unit tests for scheduler module."""

import unittest
from unittest.mock import Mock, patch

from gardebot.scheduler import (
    publish_polls,
    send_assignments,
    send_reminders,
    sync_events,
    warn_holidays,
)


class TestSchedulerFunctions(unittest.TestCase):
    """Test cases for scheduler functions."""

    @patch("gardebot.scheduler.EventService")
    @patch("gardebot.scheduler.LOGGER")
    def test_sync_events(self, mock_logger: Mock, mock_service_cls: Mock) -> None:
        """Test sync_events function."""
        mock_service = Mock()
        mock_service_cls.return_value = mock_service

        sync_events()

        mock_service.synchronize_events.assert_called_once()
        self.assertEqual(mock_logger.info.call_count, 2)

    @patch("gardebot.scheduler.PollService")
    @patch("gardebot.scheduler.LOGGER")
    def test_publish_polls(self, mock_logger: Mock, mock_service_cls: Mock) -> None:
        """Test publish_polls function."""
        mock_service = Mock()
        mock_service_cls.return_value = mock_service

        publish_polls()

        mock_service.publish_polls.assert_called_once()
        self.assertEqual(mock_logger.info.call_count, 2)

    @patch("gardebot.scheduler.Gardebot")
    @patch("gardebot.scheduler.LOGGER")
    def test_send_assignments(self, mock_logger: Mock, mock_gardebot_cls: Mock) -> None:
        """Test send_assignments function."""
        mock_gardebot = Mock()
        mock_gardebot_cls.return_value = mock_gardebot

        send_assignments()

        mock_gardebot.assign_on_duty_for_events.assert_called_once()
        self.assertEqual(mock_logger.info.call_count, 2)

    @patch("gardebot.scheduler.Gardebot")
    @patch("gardebot.scheduler.LOGGER")
    def test_send_reminders(self, mock_logger: Mock, mock_gardebot_cls: Mock) -> None:
        """Test send_reminders function."""
        mock_gardebot = Mock()
        mock_gardebot_cls.return_value = mock_gardebot

        send_reminders()

        mock_gardebot.reminders.assert_called_once()
        self.assertEqual(mock_logger.info.call_count, 2)

    @patch("gardebot.scheduler.Gardebot")
    @patch("gardebot.scheduler.LOGGER")
    def test_warn_holidays(self, mock_logger: Mock, mock_gardebot_cls: Mock) -> None:
        """Test warn_holidays function."""
        mock_gardebot = Mock()
        mock_gardebot_cls.return_value = mock_gardebot

        warn_holidays()

        mock_gardebot.send_holiday_warning.assert_called_once()
        self.assertEqual(mock_logger.info.call_count, 2)


if __name__ == "__main__":
    unittest.main()
