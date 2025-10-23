"""GroupAdapter: group-related operations via WahaClient (composition over inheritance)."""

from __future__ import annotations

from typing import Any, Dict, List, Union

from gardebot.common.logging_configuration import get_logger
from gardebot.config import GROUP_ID_GARDE_ET_PIQUET
from gardebot.errors import ExternalServiceError
from gardebot.integrations.waha_client import WahaClient

LOGGER = get_logger(__name__)


class GroupAdapter(WahaClient):
    """Encapsulates group-related WAHA interactions."""

    def __init__(
        self,
        group_id: str = GROUP_ID_GARDE_ET_PIQUET,
    ) -> None:
        """Initialize with optional custom WahaClient."""
        self.group_id = group_id
        super().__init__()

    def get_group_participants(self) -> List[Dict[str, Any]]:
        """Return list of participants or raise ExternalServiceError."""
        endpoint = f"/api/{self.session}/groups/{self.group_id}/participants"
        try:
            resp = self.get(endpoint, raise_for_status=True)
            data = self.extract_json(resp)  # noqa: SLF001
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
        endpoint = f"/api/{self.session}/groups"
        params = {
            "limit": limit,
            "offset": offset,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        try:
            resp = self.get(endpoint, params=params, raise_for_status=True)
            if isinstance(resp.json(), list):
                data_list: List[Dict[str, Any]] = self.extract_json_list(resp)
                return data_list
            elif isinstance(resp.json(), dict):
                data_dict: Dict[str, Any] = self.extract_json_dict(resp)  # noqa: SLF001
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
