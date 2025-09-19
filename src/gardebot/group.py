"""Module to handle groups from WAHA."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.config import API_CONFIG, GROUP_ID_GARDE_ET_PIQUET
from gardebot.contact import ContactRequest
from gardebot.datamanager import DataManager
from gardebot.request import WahaRequest

LOGGER = logging.getLogger(__name__)


class GroupRequest(WahaRequest):
    """Handles group interactions with the WAHA API."""

    def __init__(
        self,
        base_url: str = API_CONFIG["base_url"],
        group_id: str = GROUP_ID_GARDE_ET_PIQUET,
    ) -> None:
        """Initialize with a specific group ID."""
        super().__init__(base_url=base_url)
        self.group_id = group_id

    def get_group_participants(
        self,
    ) -> Optional[List[Dict[str, Any]]]:
        """Fetch participants of a specific group from the WAHA API.

        Returns:
            Dictionary of participant information
        """
        endpoint = f"/api/{self.session}/groups/{self.group_id}/participants"
        try:
            response = self.send_get_request(endpoint=endpoint)
            if self._is_success(response.status_code):
                LOGGER.info(
                    "Participants fetched successfully for group %s", self.group_id
                )
                participants: List[Dict[str, Any]] = response.json()
                return participants
            LOGGER.error(
                "Failed to fetch participants for groupId %s (%s): %s",
                self.group_id,
                response.status_code,
                response.text,
            )
            return None
        except Exception as exc:
            LOGGER.exception("Error fetching participants: %s", exc)
            return None

    def get_groups(
        self,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "subject",
        sort_order: str = "desc",
    ) -> Optional[Dict[str, Any]]:
        """Get groups from the WAHA API with pagination and sorting.

        Args:
            limit: Maximum number of groups to return
            offset: Number of groups to skip
            sort_by: Field to sort by (e.g., "subject", "creation")
            sort_order: Sort order ("asc" or "desc")

        Returns:
            Dictionary of group information
        """
        endpoint = f"/api/{self.session}/groups"
        params = {
            "limit": limit,
            "offset": offset,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        try:
            response = self.send_get_request(endpoint=endpoint, params=params)
            if self._is_success(response.status_code):
                LOGGER.info("Groups fetched successfully")
                groups: Dict[str, Any] = response.json()
                return groups
            LOGGER.error(
                "Failed to fetch groups (%s): %s", response.status_code, response.text
            )
            return None
        except Exception as exc:
            LOGGER.exception("Error fetching groups: %s", exc)
            return None

    def fetch_group_participants_table(
        self,
    ) -> pd.DataFrame:
        """Fetch and format a table of group participants with contact info.

        Args:
            groups_id: Unique identifier of the group
        Returns:
            DataFrame of participant contact information
        """
        group_participants = self.get_group_participants()
        if group_participants is None:
            LOGGER.error("No participants found for group %s", self.group_id)
            return pd.DataFrame()
        contact_id_list = [
            "".join([char for char in contact_data["PhoneNumber"] if char.isnumeric()])
            for contact_data in group_participants
        ]

        contact_info_list = []
        for contact_id in contact_id_list:
            contact_request = ContactRequest(base_url=self.base_url)
            contact_info = contact_request.get_contact_info(contact_id=contact_id)
            if contact_info is None:
                LOGGER.warning("No contact info found for contact %s", contact_id)
            else:
                contact_info_list.append(contact_info)
        df = pd.DataFrame(contact_info_list)
        df["phone"] = df["id"].str.extract(r"(\d+)")[0].apply(lambda s: "+" + s)
        df["joined_date"] = pd.Timestamp.now(tz="Europe/Zurich")
        df["group_id"] = self.group_id

        return df

    def sync_whatsapp_group_participants(
        self,
    ) -> None:
        """Fetch and format a table of group participants with contact info."""
        data_manager = DataManager()
        actual_participants_df = self.fetch_group_participants_table()
        participants_in_database_df = data_manager.load_dataframe("group_participants")
        if participants_in_database_df.empty:
            LOGGER.info(
                "No existing participants in database. Saved current participants."
            )
            data_manager.save_dataframe(actual_participants_df, "group_participants")
            return None

        if actual_participants_df["id"].equals(participants_in_database_df["id"]):
            LOGGER.debug("No changes in group %s participants.", self.group_id)
            return None

        left_group_mask = ~participants_in_database_df["id"].isin(
            actual_participants_df["id"]
        )
        join_group_mask = ~actual_participants_df["id"].isin(
            participants_in_database_df["id"]
        )
        new_members = actual_participants_df[join_group_mask]
        if join_group_mask.any():
            LOGGER.info(
                "Members who joined the group %s: %s",
                self.group_id,
                new_members[["id", "name", "phone"]].to_dict(orient="records"),
            )

        updated_df = pd.concat(
            [participants_in_database_df[~left_group_mask], new_members],
            ignore_index=True,
        )
        data_manager.save_dataframe(updated_df, "group_participants")
        return None
