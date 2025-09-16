"""Handles file operations for the Planning class."""

import io
import logging
import os
from abc import ABC
from typing import Tuple

import pandas as pd  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]
from dotenv import load_dotenv

LOGGER = logging.getLogger(__name__)


class DataManager(ABC):
    """Handles file operations for the subclasses."""

    def __init__(self) -> None:
        """Initializes the DataManager with a for file operations on Kdrive."""
        load_dotenv(dotenv_path="credentials.env", override=True)

    # @abstractmethod
    # def load_dataframe(self, filename: str) -> pd.DataFrame:
    #     """Load a dataframe from a file or create a new one if not found.

    #     This method must be implemented by subclasses.

    #     Args:
    #         filename (str): Name of the file to load.

    #     Returns:
    #         pd.DataFrame: The loaded DataFrame.
    #     """

    def _get_credentials(self) -> Tuple[str, str]:
        """Get the Kdrive credentials from environment variables.

        Returns:
            Tuple[str, str]: The Kdrive username and password.
        """
        load_dotenv(dotenv_path="credentials.env", override=True)
        username = os.environ.get("KDRIVE_USER")
        if username is None:
            raise ValueError("KDRIVE_USER environment variable not set")
        password = os.environ.get("KDRIVE_PWD")
        if password is None:
            raise ValueError("KDRIVE_PWD environment variable not set")
        return username, password

    def generate_file_url(self, filename: str) -> str:
        """Generate the file URL for Kdrive."""
        k_id = os.environ.get("KDRIVE_ID")
        if k_id is None:
            raise ValueError("KDRIVE_ID environment variable not set")
        folder = os.environ.get("KDRIVE_FOLDER")
        if folder is None:
            raise ValueError("KDRIVE_FOLDER environment variable not set")

        file_path = os.path.join(folder, filename)
        LOGGER.info("Using File path: %s", file_path)
        folder_url = f"https://{k_id}.connect.kdrive.infomaniak.com/remote.php/webdav/Common%20documents/"
        file_url = os.path.join(folder_url, file_path).replace(" ", "%20")
        return file_url

    def save_dataframe(self, df: pd.DataFrame, filename: str) -> None:
        """Save the calendar dataframe as CSV and Parquet in Kdrive."""
        self.save_dataframe_as_csv(df, filename)
        self.save_dataframe_as_parquet(df, filename)

    def save_dataframe_as_parquet(self, df: pd.DataFrame, filename: str) -> None:
        """Save a dataframe as Parquet in Kdrive for data consistency.

        Args:
            df (pd.DataFrame): The DataFrame to save.
            filename (str): The name of the file to save to.
        """
        username, password = self._get_credentials()
        if not filename.endswith(".parquet"):
            filename = f"{filename.split('.')[0]}.parquet"

        file_url = self.generate_file_url(filename)
        LOGGER.debug("Saving DataFrame to Kdrive as %s", filename)

        output = io.BytesIO()
        df.to_parquet(output)
        parquet_data = output.getvalue()
        response = requests.put(
            file_url,
            data=parquet_data,
            auth=(username, password),
            headers={"Content-Type": "application/octet-stream"},
            timeout=200,
        )

        if response.status_code not in [204, 201]:
            LOGGER.error(
                "Failed to save DataFrame %s to Kdrive. Status code: %s, Response: %s",
                filename,
                response.status_code,
                response.text,
            )

    def save_dataframe_as_csv(self, df: pd.DataFrame, filename: str) -> None:
        """Save a dataframe to Kdrive as csv.

        Args:
            df (pd.DataFrame): The DataFrame to save.
            filename (str): The name of the file to save to.
        """
        username = os.environ.get("KDRIVE_USER")
        if username is None:
            raise ValueError("KDRIVE_USER environment variable not set")
        password = os.environ.get("KDRIVE_PWD")
        if password is None:
            raise ValueError("KDRIVE_PWD environment variable not set")
        if not filename.endswith(".csv"):
            filename = f"{filename.split('.')[0]}.csv"
        file_url = self.generate_file_url(filename)
        LOGGER.debug("Saving DataFrame to Kdrive as %s", filename)

        csv_data = df.to_csv(index=True, encoding="utf-8", sep="\t")
        response = requests.put(
            file_url,
            data=csv_data,
            auth=(username, password),
            headers={"Content-Type": "text/csv; charset=utf-8; delimiter=;"},
            timeout=200,
        )
        if response.status_code not in [204, 201]:
            LOGGER.error(
                "Failed to save DataFrame %s to Kdrive. Status code: %s, Response: %s",
                filename,
                response.status_code,
                response.text,
            )
