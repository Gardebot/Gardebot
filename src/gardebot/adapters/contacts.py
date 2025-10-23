"""ContactAdapter: contact-related operations via WahaClient (composition over inheritance)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from gardebot.common.logging_configuration import get_logger
from gardebot.errors import ExternalServiceError
from gardebot.integrations.waha_client import WahaClient

LOGGER = get_logger(__name__)


class ContactAdapter(WahaClient):
    """Encapsulates contact-related WAHA interactions."""

    def __init__(
        self,
    ) -> None:
        """Initialize with optional custom WahaClient."""
        super().__init__()

    def get_contact_info(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Fetch contact information from the WAHA API.

        Returns:
            Dictionary of contact information
        """
        endpoint = f"/api/contacts?contactId={contact_id}&session={self.session}"
        try:
            response = self.get(endpoint, raise_for_status=True)
            LOGGER.debug("Contact info fetched successfully for contact %s", contact_id)
            contact_info: Dict[str, Any] = response.json()
            contact_info["phone"] = "+" + "".join([a for a in contact_id if a.isdigit()])  # Quick fix to add phone number
            return contact_info
        except Exception as exc:
            raise ExternalServiceError("Failed to fetch contact info", detail={"error": str(exc)})
