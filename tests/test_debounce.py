"""Unit tests for debounce module."""

import time
import unittest
from unittest.mock import Mock

from gardebot.common.debounce import Debouncer


class TestDebouncer(unittest.TestCase):
    """Test cases for Debouncer class."""

    def test_init(self) -> None:
        """Test debouncer initialization."""
        action = Mock()
        debouncer = Debouncer(0.1, action)

        self.assertEqual(debouncer.delay, 0.1)
        self.assertEqual(debouncer.action, action)
        self.assertIsNone(debouncer._timer)

    def test_trigger_single_call(self) -> None:
        """Test single trigger call."""
        action = Mock()
        debouncer = Debouncer(0.05, action)

        debouncer.trigger()
        time.sleep(0.1)  # Wait for action to execute

        action.assert_called_once()

    def test_trigger_multiple_calls_debounced(self) -> None:
        """Test multiple rapid trigger calls are debounced."""
        action = Mock()
        debouncer = Debouncer(0.1, action)

        # Trigger multiple times rapidly
        debouncer.trigger()
        debouncer.trigger()
        debouncer.trigger()

        time.sleep(0.15)  # Wait for final action to execute

        # Should only be called once due to debouncing
        action.assert_called_once()

    def test_trigger_cancels_previous_timer(self) -> None:
        """Test that new trigger cancels previous timer."""
        action = Mock()
        debouncer = Debouncer(0.1, action)

        debouncer.trigger()
        first_timer = debouncer._timer

        debouncer.trigger()
        second_timer = debouncer._timer

        # Should have different timers
        self.assertNotEqual(first_timer, second_timer)
        self.assertIsNotNone(second_timer)

    def test_trigger_with_zero_delay(self) -> None:
        """Test trigger with zero delay."""
        action = Mock()
        debouncer = Debouncer(0.0, action)

        debouncer.trigger()
        time.sleep(0.01)  # Small sleep to allow execution

        action.assert_called_once()

    def test_action_with_exception(self) -> None:
        """Test that action exceptions don't break debouncer."""

        def failing_action() -> None:
            raise Exception("Test exception")

        debouncer = Debouncer(0.05, failing_action)

        # Should not raise exception
        debouncer.trigger()
        time.sleep(0.1)  # Wait for action to execute

        # Debouncer should still be functional
        self.assertIsNotNone(debouncer._timer)


if __name__ == "__main__":
    unittest.main()
