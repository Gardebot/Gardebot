"""Optimized unit tests for storage module."""

import io
import os
import unittest
from typing import Any
from unittest.mock import Mock, patch

import pandas as pd  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]

from gardebot.common.storage import FileStorage, ensure_columns


class TestFileStorage(unittest.TestCase):
    """Test cases for FileStorage class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.env_vars = {"KDRIVE_USER": "test_user", "KDRIVE_PWD": "test_password", "KDRIVE_ID": "test_id", "KDRIVE_FOLDER": "test_folder"}

    def test_initialization(self) -> None:
        """Test FileStorage initialization scenarios."""
        # Test successful initialization
        with patch.dict(os.environ, self.env_vars):
            storage = FileStorage()
            self.assertEqual(storage.user, "test_user")
            self.assertEqual(storage.pwd, "test_password")
            self.assertEqual(storage.kdrive_id, "test_id")
            self.assertEqual(storage.folder, "test_folder")

    @patch.dict(
        os.environ, {"KDRIVE_USER": "test_user", "KDRIVE_PWD": "test_password", "KDRIVE_ID": "test_id", "KDRIVE_FOLDER": "test_folder"}
    )
    def test_url_generation(self) -> None:
        """Test WebDAV URL generation methods."""
        storage = FileStorage()

        # Test base URL
        expected_base = "https://test_id.connect.kdrive.infomaniak.com/remote.php/webdav/Common%20documents/"
        self.assertEqual(storage._webdav_base_url(), expected_base)

        # Test file URL
        file_url = storage._file_url("test_file.parquet")
        expected_file = expected_base + "test_folder/test_file.parquet"
        self.assertEqual(file_url, expected_file)

        # Test file URL with spaces
        file_url_spaces = storage._file_url("test file.parquet")
        self.assertIn("test%20file.parquet", file_url_spaces)
        self.assertNotIn(" ", file_url_spaces)

    @patch.dict(
        os.environ, {"KDRIVE_USER": "test_user", "KDRIVE_PWD": "test_password", "KDRIVE_ID": "test_id", "KDRIVE_FOLDER": "test_folder"}
    )
    @patch("gardebot.common.storage.requests.get")
    def test_read_parquet(self, mock_get: Any) -> None:
        """Test parquet file reading scenarios."""
        storage = FileStorage()

        # Test successful read
        df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        buffer = io.BytesIO()
        df.to_parquet(buffer)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = buffer.getvalue()
        mock_get.return_value = mock_response

        result = storage.read_parquet("test_file.parquet")
        pd.testing.assert_frame_equal(result.reset_index(drop=True), df.reset_index(drop=True))

        # Test file not found
        mock_response.status_code = 404
        result = storage.read_parquet("nonexistent.parquet")
        self.assertTrue(result.empty)

        # Test extension handling
        storage.read_parquet("test_file")  # No extension
        call_args = mock_get.call_args
        self.assertIn("test_file.parquet", call_args[0][0])

    @patch.dict(
        os.environ, {"KDRIVE_USER": "test_user", "KDRIVE_PWD": "test_password", "KDRIVE_ID": "test_id", "KDRIVE_FOLDER": "test_folder"}
    )
    @patch("gardebot.common.storage.requests.put")
    def test_write_operations(self, mock_put: Any) -> None:
        """Test file writing operations."""
        storage = FileStorage()
        df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})

        # Test successful parquet write
        mock_response = Mock()
        mock_response.status_code = 201
        mock_put.return_value = mock_response

        storage.write_parquet(df, "test_file.parquet")
        call_args = mock_put.call_args
        self.assertEqual(call_args[1]["headers"]["Content-Type"], "application/octet-stream")
        self.assertEqual(call_args[1]["auth"], ("test_user", "test_password"))

        # Test parquet write with extension handling
        mock_put.reset_mock()
        storage.write_parquet(df, "test_file")  # No extension
        call_args = mock_put.call_args
        self.assertIn("test_file.parquet", call_args[0][0])

        # Test CSV write
        mock_put.reset_mock()
        storage.write_csv(df, "test_file.csv")
        call_args = mock_put.call_args
        self.assertEqual(call_args[1]["headers"]["Content-Type"], "text/csv; charset=utf-8")

        # Test write failures
        with patch("gardebot.common.storage.LOGGER") as mock_logger:
            mock_response.status_code = 500
            mock_response.text = "Server Error"
            storage.write_parquet(df, "test_file.parquet")
            mock_logger.error.assert_called_once()

            mock_logger.reset_mock()
            storage.write_csv(df, "test_file.csv")
            mock_logger.warning.assert_called_once()

    @patch.dict(
        os.environ, {"KDRIVE_USER": "test_user", "KDRIVE_PWD": "test_password", "KDRIVE_ID": "test_id", "KDRIVE_FOLDER": "test_folder"}
    )
    def test_atomic_write(self) -> None:
        """Test atomic write operations."""
        storage = FileStorage()
        df = pd.DataFrame({"col1": [1, 2]})

        # Test successful atomic write with CSV
        with patch.object(storage, "write_parquet") as mock_write_parquet:
            with patch.object(storage, "write_csv") as mock_write_csv:
                with patch("gardebot.common.storage.LOGGER") as mock_logger:
                    storage.atomic_write(df, "test_file", also_csv=True)

                    mock_write_parquet.assert_called_once()
                    mock_write_csv.assert_called_once()
                    mock_logger.info.assert_called_once()

        # Test atomic write without CSV
        with patch.object(storage, "write_parquet") as mock_write_parquet:
            with patch.object(storage, "write_csv") as mock_write_csv:
                storage.atomic_write(df, "test_file", also_csv=False)

                mock_write_parquet.assert_called_once()
                mock_write_csv.assert_not_called()

        # Test CSV exception handling
        with patch.object(storage, "write_parquet"):
            with patch.object(storage, "write_csv", side_effect=requests.RequestException("Network error")):
                with patch("gardebot.common.storage.LOGGER") as mock_logger:
                    storage.atomic_write(df, "test_file", also_csv=True)
                    mock_logger.exception.assert_called_once()


class TestEnsureColumns(unittest.TestCase):
    """Test cases for ensure_columns function."""

    def test_ensure_columns_scenarios(self) -> None:
        """Test ensure_columns with various scenarios."""
        # Test with existing columns
        df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        result = ensure_columns(df, ["col1", "col2"])
        pd.testing.assert_frame_equal(result, df)

        # Test with missing columns
        df = pd.DataFrame({"col1": [1, 2]})
        result = ensure_columns(df, ["col1", "col2", "col3"])
        self.assertIn("col2", result.columns)
        self.assertIn("col3", result.columns)
        self.assertTrue(result["col2"].isna().all())
        self.assertTrue(result["col3"].isna().all())

        # Test with empty requirements
        df = pd.DataFrame({"col1": [1, 2]})
        result = ensure_columns(df, [])
        pd.testing.assert_frame_equal(result, df)

        # Test with empty DataFrame
        df = pd.DataFrame()
        result = ensure_columns(df, ["col1", "col2"])
        self.assertIn("col1", result.columns)
        self.assertIn("col2", result.columns)


if __name__ == "__main__":
    unittest.main()
