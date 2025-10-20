"""Storage module for Gardebot using WebDAV (Kdrive)."""

from __future__ import annotations

import io
import logging
import os
from typing import Iterable

import pandas as pd  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]
from dotenv import load_dotenv

LOGGER = logging.getLogger(__name__)


class FileStorage:
    """Handles low-level file persistence (WebDAV Kdrive)."""

    def __init__(self) -> None:
        """Load environment configuration for remote storage."""
        load_dotenv(dotenv_path="credentials.env")
        required = ["KDRIVE_USER", "KDRIVE_PWD", "KDRIVE_ID", "KDRIVE_FOLDER"]
        missing = [v for v in required if os.environ.get(v) is None]
        if len(missing) > 0:
            raise ValueError(f"Missing environment variables: {missing}")
        self.user = os.environ["KDRIVE_USER"]
        self.pwd = os.environ["KDRIVE_PWD"]
        self.kdrive_id = os.environ["KDRIVE_ID"]
        self.folder = os.environ["KDRIVE_FOLDER"]

    def _webdav_base_url(self) -> str:
        """Return base WebDAV folder URL."""
        return f"https://{self.kdrive_id}.connect.kdrive.infomaniak.com/remote.php/webdav/Common%20documents/"

    def _file_url(self, filename: str) -> str:
        """Build fully-qualified file URL."""
        filename = filename.replace(" ", "%20")
        path = os.path.join(self.folder, filename)
        return os.path.join(self._webdav_base_url(), path).replace(" ", "%20")

    def read_parquet(self, filename: str) -> pd.DataFrame:
        """Read a parquet file from remote storage; returns empty DataFrame if missing."""
        if not filename.endswith(".parquet"):
            filename = f"{filename}.parquet"
        url = self._file_url(filename)
        resp = requests.get(url, auth=(self.user, self.pwd), timeout=200)
        if resp.status_code != 200:  # noqa: PLR2004
            LOGGER.info("File %s not found (status %s). Returning empty DataFrame.", filename, resp.status_code)
            return pd.DataFrame()
        return pd.read_parquet(io.BytesIO(resp.content))

    def write_parquet(self, df: pd.DataFrame, filename: str) -> None:
        """Persist DataFrame as parquet to remote storage."""
        if not filename.endswith(".parquet"):
            filename = f"{filename}.parquet"
        url = self._file_url(filename)
        buffer = io.BytesIO()
        df.to_parquet(buffer)
        resp = requests.put(
            url,
            data=buffer.getvalue(),
            auth=(self.user, self.pwd),
            headers={"Content-Type": "application/octet-stream"},
            timeout=200,
        )
        if resp.status_code not in (201, 204):
            LOGGER.error("Failed to write %s (status %s): %s", filename, resp.status_code, resp.text)

    def write_csv(self, df: pd.DataFrame, filename: str) -> None:
        """Optionally write CSV (auxiliary human-readable)."""
        if not filename.endswith(".csv"):
            filename = f"{filename}.csv"
        url = self._file_url(filename)
        csv_data = df.to_csv(index=True)
        resp = requests.put(
            url,
            data=csv_data.encode("utf-8"),
            auth=(self.user, self.pwd),
            headers={"Content-Type": "text/csv; charset=utf-8"},
            timeout=200,
        )
        if resp.status_code not in (201, 204):
            LOGGER.warning("Failed to write CSV %s (status %s)", filename, resp.status_code)

    def atomic_write(self, df: pd.DataFrame, filename: str, also_csv: bool = True) -> None:
        """High-level write (parquet + optional CSV)."""
        LOGGER.info("Writing file %s (rows=%d, also_csv=%s)", filename, len(df), also_csv)
        self.write_parquet(df, filename)
        if also_csv:
            try:
                self.write_csv(df, filename)
            except (requests.RequestException, OSError) as exc:
                LOGGER.exception("CSV write failed for %s: %s", filename, exc)


def ensure_columns(df: pd.DataFrame, required: Iterable[str]) -> pd.DataFrame:
    """Ensure required columns exist; add if missing."""
    for col in required:
        if col not in df.columns:
            df[col] = None
    return df
