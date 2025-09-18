"""Module to handle contacts from WAHA."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging
from typing import Any, Dict, Optional

from gardebot.request import WahaRequest

LOGGER = logging.getLogger(__name__)


class ContactRequest(WahaRequest):
    """Handles contact interactions with the WAHA API."""

    def __init__(self, contact_id: str) -> None:
        """Initialize with a specific contact ID."""
        super().__init__()
        self.contact_id = contact_id

    def get_contact_info(
        self,
    ) -> Optional[Dict[str, Any]]:
        """Fetch contact information from the WAHA API.

        Returns:
            Dictionary of contact information
        """
        endpoint = f"/api/contacts?contactId={self.contact_id}&session={self.session}"
        try:
            response = self.send_get_request(endpoint=endpoint)
            if self._is_success(response.status_code):
                LOGGER.info(
                    "Contact info fetched successfully for contact %s", self.contact_id
                )
                contact_info: Dict[str, Any] = response.json()
                return contact_info
            LOGGER.error(
                "Failed to fetch contact info for contactId %s (%s): %s",
                self.contact_id,
                response.status_code,
                response.text,
            )
            return None
        except Exception as exc:
            LOGGER.exception("Error fetching contact info: %s", exc)
            return None
