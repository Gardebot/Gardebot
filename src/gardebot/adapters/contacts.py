"""ContactAdapter: contact-related operations via WahaClient (composition over inheritance)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from gardebot.errors import ExternalServiceError
from gardebot.integrations.waha_client import WahaClient
from gardebot.settings import settings

LOGGER = logging.getLogger(__name__)


class ContactAdapter:
    """Encapsulates group-related WAHA interactions."""

    def __init__(
        self,
        waha_client: Optional[WahaClient] = None,
    ) -> None:
        """Initialize with optional custom WahaClient."""
        self._client = waha_client or WahaClient(
            api_key=settings.api.api_key,
            base_url=settings.api.base_url,
            session=settings.api.session,
            timeout=settings.api.timeout_seconds,
            retries=settings.api.retry_attempts,
        )

    def get_contact_info(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Fetch contact information from the WAHA API.

        Returns:
            Dictionary of contact information
        """
        endpoint = f"/api/contacts?contactId={contact_id}&session={self._client.session}"
        try:
            response = self._client._http.request("GET", endpoint, raise_for_status=True)  # noqa: SLF001
            LOGGER.debug("Contact info fetched successfully for contact %s", contact_id)
            contact_info: Dict[str, Any] = response.json()
            contact_info["phone"] = "+" + "".join([a for a in contact_id if a.isdigit()])  # Quick fix to add phone number
            return contact_info
        except Exception as exc:
            raise ExternalServiceError("Failed to fetch contact info", detail={"error": str(exc)})
