"""GroupAdapter: group-related operations via WahaClient (composition over inheritance)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from gardebot.config import GROUP_ID_GARDE_ET_PIQUET
from gardebot.errors import ExternalServiceError
from gardebot.integrations.waha_client import WahaClient
from gardebot.settings import settings

LOGGER = logging.getLogger(__name__)


class GroupAdapter:
    """Encapsulates group-related WAHA interactions."""

    def __init__(
        self,
        group_id: str = GROUP_ID_GARDE_ET_PIQUET,
        waha_client: Optional[WahaClient] = None,
    ) -> None:
        """Initialize with optional custom WahaClient."""
        self.group_id = group_id
        self._client = waha_client or WahaClient(
            api_key=settings.api.api_key,
            base_url=settings.api.base_url,
            session=settings.api.session,
            timeout=settings.api.timeout_seconds,
            retries=settings.api.retry_attempts,
        )

    def get_group_participants(self) -> List[Dict[str, Any]]:
        """Return list of participants or raise ExternalServiceError."""
        endpoint = f"/api/{self._client.session}/groups/{self.group_id}/participants"
        try:
            resp = self._client._http.request("GET", endpoint, raise_for_status=True)  # noqa: SLF001
            data = self._client._extract_json(resp)  # noqa: SLF001
            if not isinstance(data, list):
                raise ExternalServiceError(
                    "Unexpected participants data shape",
                    detail={"type": type(data).__name__},
                )
            LOGGER.debug("group_participants_fetched", extra={"group_id": self.group_id, "count": len(data)})
            return data
        except ExternalServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceError("Failed to fetch group participants", detail={"error": str(exc)}) from exc

    def get_groups(
        self,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "subject",
        sort_order: str = "desc",
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Fetch groups with pagination."""
        endpoint = f"/api/{self._client.session}/groups"
        params = {
            "limit": limit,
            "offset": offset,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        try:
            resp = self._client._http.request("GET", endpoint, params=params, raise_for_status=True)  # noqa: SLF001
            if isinstance(resp.json(), list):
                data_list: List[Dict[str, Any]] = self._client._extract_json_list(resp)  # noqa: SLF001
                return data_list
            elif isinstance(resp.json(), dict):
                data_dict: Dict[str, Any] = self._client._extract_json_dict(resp)  # noqa: SLF001
                return data_dict
            else:
                raise ExternalServiceError(
                    "Unexpected groups response data shape",
                    detail={"type": type(resp.json()).__name__},
                )
        except ExternalServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceError("Failed to fetch groups", detail={"error": str(exc)}) from exc
