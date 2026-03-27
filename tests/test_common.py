"""Unit tests for common module."""

import unittest
from datetime import datetime

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.common import _format_french_date, parse_iso_datetime


class TestCommonFunctions(unittest.TestCase):
    """Test cases for common utility functions."""

    def test_parse_iso_datetime_standard(self) -> None:
        """Test parsing standard ISO datetime."""
        dt_str = "2023-12-25T10:30:00+01:00"
        result = parse_iso_datetime(dt_str)

        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 25)
        self.assertEqual(result.hour, 10)
        self.assertEqual(result.minute, 30)

    def test_parse_iso_datetime_zulu(self) -> None:
        """Test parsing ISO datetime with Z suffix."""
        dt_str = "2023-12-25T10:30:00Z"
        result = parse_iso_datetime(dt_str)

        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 25)

    def test_parse_iso_datetime_invalid(self) -> None:
        """Test parsing invalid ISO datetime."""
        with self.assertRaises(ValueError):
            parse_iso_datetime("invalid-date")

    def test_format_french_date(self) -> None:
        """Test French date formatting."""
        # Create a pandas Timestamp for December 25, 2023 (Monday)
        test_date = pd.Timestamp(2023, 12, 25)
        result = _format_french_date(test_date)

        self.assertIn("lundi", result.lower())  # Monday in French
        self.assertIn("25", result)
        self.assertIn("décembre", result.lower())  # December in French
        self.assertIn("2023", result)


if __name__ == "__main__":
    unittest.main()
