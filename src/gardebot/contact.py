"""Module to handle contacts from WAHA."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from gardebot.config import API_CONFIG
from gardebot.request import WahaRequest

LOGGER = logging.getLogger(__name__)


class ContactRequest(WahaRequest):
    """Handles contact interactions with the WAHA API."""

    def __init__(self, base_url: str = API_CONFIG["base_url"]) -> None:
        """Initialize with a specific contact ID."""
        super().__init__(base_url=base_url)

    def get_contact_info(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Fetch contact information from the WAHA API.

        Returns:
            Dictionary of contact information
        """
        endpoint = f"/api/contacts?contactId={contact_id}&session={self.session}"
        try:
            response = self.send_get_request(endpoint=endpoint)
            if self._is_success(response.status_code):
                LOGGER.debug("Contact info fetched successfully for contact %s", contact_id)
                contact_info: Dict[str, Any] = response.json()
                contact_info["phone"] = "+" + "".join([a for a in contact_id if a.isdigit()])  # Quick fix to add phone number
                return contact_info
            LOGGER.error(
                "Failed to fetch contact info for contactId %s (%s): %s",
                contact_id,
                response.status_code,
                response.text,
            )
            return None
        except Exception as exc:
            LOGGER.exception("Error fetching contact info: %s", exc)
            return None
