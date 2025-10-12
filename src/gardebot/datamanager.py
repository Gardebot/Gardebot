"""Handles file operations for the Planning class."""

import io
import logging
import os
from abc import ABC

import pandas as pd  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]
from dotenv import load_dotenv

LOGGER = logging.getLogger(__name__)


class DataManager(ABC):
    """Handles file operations for the subclasses."""

    def __init__(self, filename: str) -> None:
        """Initializes the DataManager with a for file operations on Kdrive."""
        load_dotenv(dotenv_path="credentials.env")
        for var in ["KDRIVE_USER", "KDRIVE_PWD", "KDRIVE_ID", "KDRIVE_FOLDER"]:
            if os.environ.get(var) is None:
                raise ValueError(f"{var} environment variable not set")
        self.kdrive_id = os.environ.get("KDRIVE_ID")
        self.kdrive_folder = os.environ.get("KDRIVE_FOLDER")
        self.kdrive_user = os.environ.get("KDRIVE_USER")
        self.kdrive_pwd = os.environ.get("KDRIVE_PWD")
        self.filename = filename

    def load_dataframe(self, filename: str) -> pd.DataFrame:
        """Load the dataframe from file or create it if not found."""
        if not filename.endswith(".parquet"):
            filename = f"{filename.split('.')[0]}.parquet"
        file_url = self.generate_file_url(filename)
        response = requests.get(
            file_url,
            auth=(
                self.kdrive_user,
                self.kdrive_pwd,
            ),  # pyright: ignore[reportArgumentType]
            timeout=200,
        )

        if response.status_code != 200:  # noqa: PLR2004
            LOGGER.warning("File %s not found. Creating a new empty DataFrame.", filename)
            df = pd.DataFrame()
        else:
            df = pd.read_parquet(io.BytesIO(response.content))
            LOGGER.debug("File %s found. Loading it into a DataFrame.", filename)

        return df

    def generate_file_url(self, filename: str) -> str:
        """Generate the file URL for Kdrive."""
        file_path = os.path.join(self.kdrive_folder, filename)  # type: ignore
        LOGGER.debug("Using File path: %s", file_path)
        folder_url = f"https://{self.kdrive_id}.connect.kdrive.infomaniak.com/remote.php/webdav/Common%20documents/"
        file_url = os.path.join(folder_url, file_path).replace(" ", "%20")
        return file_url

    def save_dataframe(self, df: pd.DataFrame, filename: str) -> None:
        """Save the calendar dataframe as CSV and Parquet in Kdrive."""
        LOGGER.debug("Saving DataFrame to Kdrive as CSV and Parquet: %s", filename)
        self.save_dataframe_as_parquet(df, filename)
        try:
            self.save_dataframe_as_csv(df, filename)
        except Exception as exc:
            LOGGER.exception("Error saving DataFrame as CSV %s: %s", filename, exc)

    def save_dataframe_as_parquet(self, df: pd.DataFrame, filename: str) -> None:
        """Save a dataframe as Parquet in Kdrive for data consistency.

        Args:
            df (pd.DataFrame): The DataFrame to save.
            filename (str): The name of the file to save to.
        """
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
            auth=(
                self.kdrive_user,
                self.kdrive_pwd,
            ),  # pyright: ignore[reportArgumentType]
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
        if not filename.endswith(".csv"):
            filename = f"{filename.split('.')[0]}.csv"
        file_url = self.generate_file_url(filename)
        LOGGER.debug("Saving DataFrame to Kdrive as %s", filename)

        csv_data = df.replace(",", ";", regex=True).to_csv(index=True, encoding="utf-8", sep=",")
        response = requests.put(
            file_url,
            data=csv_data,
            auth=(
                self.kdrive_user,
                self.kdrive_pwd,
            ),  # pyright: ignore[reportArgumentType]
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

    def synch_dataframe(self, old_df: pd.DataFrame, new_df: pd.DataFrame, key: str) -> None:
        """Update the dataframe in Kdrive."""
        if key not in new_df.columns:
            LOGGER.warning(
                "Key %s not in new dataframe columns %s. Cannot synch.",
                key,
                new_df.columns,
            )
            self.save_dataframe(old_df, self.filename)
            return None
        if key not in old_df.columns:
            LOGGER.warning(
                "Key %s not in old dataframe columns %s. Cannot synch.",
                key,
                old_df.columns,
            )
            self.save_dataframe(new_df, self.filename)
            return None
        input_df = new_df[~new_df[key].isin(old_df[key])]
        if input_df.empty:
            LOGGER.debug("No new data to update in %s.", self.filename)
            self.save_dataframe(old_df, self.filename)
            return None
        updated_df = pd.concat([old_df, input_df], ignore_index=True)
        self.save_dataframe(updated_df, self.filename)
        LOGGER.debug(
            "New data found and saved in %s: %s",
            self.filename,
            input_df.to_dict(orient="records"),
        )
        return None
