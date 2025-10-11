"""Tests for the Debouncer utility."""

import time
import unittest

from gardebot.common.debounce import Debouncer


class TestDebounce(unittest.TestCase):
    """Test the Debouncer utility."""

    def test_single_execution(self) -> None:
        """Test that the debounced function is called only once after multiple rapid triggers."""
        c = {"n": 0}

        def inc() -> None:
            c["n"] += 1

        d = Debouncer(0.1, inc)
        for _ in range(5):
            d.trigger()
            time.sleep(0.02)
        time.sleep(0.15)
        self.assertEqual(c["n"], 1)
