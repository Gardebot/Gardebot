"""Module to handle groups from WAHA."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]

from gardebot.config import GROUP_ID_GARDE_ET_PIQUET
from gardebot.contact import ContactRequest
from gardebot.request import WahaRequest
from gardebot.settings import settings

LOGGER = logging.getLogger(__name__)


class GroupRequest(WahaRequest):
    """Handles group interactions with the WAHA API."""

    def __init__(
        self,
        base_url: str = settings.api.base_url,
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
                LOGGER.debug("Participants fetched successfully for group %s", self.group_id)
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

    def refresh_group_server(self) -> requests.Response:
        """Trigger a refresh of the group data on the WAHA server."""
        endpoint = f"/api/{self.session}/groups/refresh"
        try:
            response = self.send_post_request(endpoint=endpoint, payload={})
            if self._is_success(response.status_code):
                LOGGER.info("Group refresh initiated successfully for group %s", self.group_id)
                return response
            LOGGER.error(
                "Failed to refresh group %s (%s): %s",
                self.group_id,
                response.status_code,
                response.text,
            )
            return response
        except Exception as exc:
            LOGGER.exception("Error refreshing group: %s", exc)
            return self._sent_error_response(exc)

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
            LOGGER.error("Failed to fetch groups (%s): %s", response.status_code, response.text)
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
            "".join([char for char in contact_data["PhoneNumber"] if char.isnumeric()]) for contact_data in group_participants
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
        df["joined_date"] = pd.Timestamp.now(tz="Europe/Zurich")
        df["group_id"] = self.group_id
        df.rename(columns={"id": "uid"}, inplace=True)

        return df
