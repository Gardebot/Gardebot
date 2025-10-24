"""Optimized unit tests for infomaniak integration module."""

import os
import unittest
from typing import Any
from unittest.mock import Mock, patch

import pandas as pd  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]

from gardebot.integrations.infomaniak import InfomaniakCalendar


class TestInfomaniakCalendar(unittest.TestCase):
    """Test cases for InfomaniakCalendar class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.calendar = InfomaniakCalendar()

    @patch.dict(os.environ, {"CALENDAR_URL": "https://test.url/ical"})
    def test_init_with_env_var(self) -> None:
        """Test initialization with environment variable."""
        calendar = InfomaniakCalendar()
        self.assertEqual(calendar.url, "https://test.url/ical")

    def test_event_field_extraction(self) -> None:
        """Test event field extraction methods."""
        # Test name extraction
        event = Mock()
        event.get.return_value = "Test Event"
        self.assertEqual(self.calendar._get_name_from_event(event), "Test Event")

        # Test missing name
        event.get.return_value = None
        with patch("gardebot.integrations.infomaniak.LOGGER") as mock_logger:
            self.assertIsNone(self.calendar._get_name_from_event(event))
            mock_logger.error.assert_called_with("missing_event_name")

        # Test location extraction
        event = Mock()  # Fresh mock
        event.get.return_value = "Location, Extra"
        self.assertEqual(self.calendar._get_location_from_event(event), "Location")

        # Test missing location
        event = Mock()  # Fresh mock
        event.get.side_effect = lambda key: "Summary" if key == "summary" else None
        with patch("gardebot.integrations.infomaniak.LOGGER") as mock_logger:
            self.assertIsNone(self.calendar._get_location_from_event(event))
            mock_logger.error.assert_called_with("missing_event_location", summary="Summary")

        # Test headcount extraction
        event = Mock()  # Fresh mock
        event.get.return_value = "5"
        self.assertEqual(self.calendar._get_headcount_from_event(event), 5)

        # Test invalid headcount cases
        invalid_cases = [None, "", "0"]
        for invalid_value in invalid_cases:
            event = Mock()  # Fresh mock for each case
            event.get.side_effect = lambda key, val=invalid_value: "Summary" if key == "summary" else val
            with patch("gardebot.integrations.infomaniak.LOGGER") as mock_logger:
                self.assertIsNone(self.calendar._get_headcount_from_event(event))
                mock_logger.error.assert_called_with("invalid_headcount", summary="Summary")

    @patch("gardebot.integrations.infomaniak.pd.to_datetime")
    def test_date_extraction(self, mock_to_datetime: Any) -> None:
        """Test date extraction from events."""
        event = Mock()
        event.get.return_value.dt = Mock()

        # Test successful date extraction
        mock_timestamp = Mock()
        mock_timestamp.tz_convert.return_value.tz_localize.return_value = pd.Timestamp("2023-10-25")
        mock_to_datetime.return_value = mock_timestamp

        result = self.calendar._get_date_from_event(event, "dtstart")
        self.assertEqual(result, pd.Timestamp("2023-10-25"))

        # Test invalid date
        with patch("gardebot.integrations.infomaniak.pd.isnull", return_value=True):
            with patch("gardebot.integrations.infomaniak.LOGGER") as mock_logger:
                event.get.side_effect = lambda key: Mock(dt="invalid") if key == "dtstart" else "Summary"
                result = self.calendar._get_date_from_event(event, "dtstart")

                self.assertIsNone(result)
                mock_logger.error.assert_called_with("invalid_date_field", summary="Summary", field="dtstart")

    def test_clean_event(self) -> None:
        """Test event cleaning."""
        with patch.object(self.calendar, "_get_name_from_event", return_value="Event"):
            with patch.object(self.calendar, "_get_location_from_event", return_value="Location"):
                with patch.object(self.calendar, "_get_headcount_from_event", return_value=5):
                    with patch.object(self.calendar, "_get_date_from_event") as mock_date:
                        mock_date.side_effect = [pd.Timestamp("2023-10-25 10:00"), pd.Timestamp("2023-10-25 12:00")]

                        result = self.calendar.clean_event(Mock())

                        expected = {
                            "name": "Event",
                            "location": "Location",
                            "headcount": 5,
                            "start_date": pd.Timestamp("2023-10-25 10:00"),
                            "end_date": pd.Timestamp("2023-10-25 12:00"),
                        }
                        self.assertEqual(result, expected)

    @patch("gardebot.integrations.infomaniak.LOGGER")
    def test_fetch_calendar_errors(self, mock_logger: Any) -> None:
        """Test fetch calendar error cases."""
        # Test missing URL
        self.calendar.url = None
        result = self.calendar.fetch_calendar()
        self.assertTrue(result.empty)
        mock_logger.error.assert_called_with("calendar_url_missing")

        # Test HTTP error
        self.calendar.url = "https://test.url"
        with patch("gardebot.integrations.infomaniak.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")
            with self.assertRaises(requests.RequestException):
                self.calendar.fetch_calendar()

    def test_data_processing(self) -> None:
        """Test DataFrame processing methods."""
        # Test _remove_na_rows
        df_with_na = pd.DataFrame({"name": ["A", "B", "C"], "location": ["X", None, "Z"], "headcount": [1, 2, None]})

        with patch("gardebot.integrations.infomaniak.LOGGER") as mock_logger:
            result = self.calendar._remove_na_rows(df_with_na)
            self.assertEqual(len(result), 1)  # Only first row should remain
            mock_logger.warning.assert_called_with("calendar_rows_dropped", dropped=2)

        # Test _handle_duplicate_names
        df_empty = pd.DataFrame()
        self.assertTrue(self.calendar._handle_duplicate_names(df_empty).empty)

        df_no_name = pd.DataFrame({"location": ["X", "Y"]})
        pd.testing.assert_frame_equal(self.calendar._handle_duplicate_names(df_no_name), df_no_name)

        # Test duplicate handling with chronological ordering
        df_duplicates = pd.DataFrame(
            {
                "name": ["Event", "Event", "Other", "Event"],
                "start_date": [
                    pd.Timestamp("2023-10-28"),
                    pd.Timestamp("2023-10-25"),
                    pd.Timestamp("2023-10-26"),
                    pd.Timestamp("2023-10-27"),
                ],
            }
        )

        result = self.calendar._handle_duplicate_names(df_duplicates)
        # After sorting by start_date, the order should be: Event(25th), Event(27th), Event(28th), Other(26th)
        # Which becomes: Event, Event 2, Event 3, Other (after duplicate numbering)
        expected_names = ["Event", "Other", "Event 2", "Event 3"]  # Corrected expected order
        self.assertEqual(result["name"].tolist(), expected_names)
        self.assertTrue(result["start_date"].is_monotonic_increasing)


if __name__ == "__main__":
    unittest.main()
