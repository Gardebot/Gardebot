"""GroupAdapter: group-related operations via WahaClient (composition over inheritance)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

import pandas as pd  # type: ignore[import-untyped]

from gardebot.adapters.contacts import ContactAdapter
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
        self.contact = ContactAdapter(waha_client=self._client)

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

    def refresh_group_server(self) -> Dict[str, Any]:
        """Trigger WAHA group refresh."""
        endpoint = f"/api/{self._client.session}/groups/refresh"
        try:
            resp = self._client._http.request("POST", endpoint, json_body={}, raise_for_status=True)  # noqa: SLF001
            data = self._client._extract_json_dict(resp)  # noqa: SLF001
            LOGGER.info("group_refresh_triggered", extra={"group_id": self.group_id})
            return data
        except ExternalServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceError("Group refresh failed", detail={"error": str(exc)}) from exc

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
                data = self._client._extract_json_list(resp)  # noqa: SLF001
            elif isinstance(resp.json(), dict):
                data = self._client._extract_json_list(resp)  # noqa: SLF001
            else:
                LOGGER.info("groups_fetched", extra={"count": len(data) if isinstance(data, list) else "unknown"})
            return data
        except ExternalServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceError("Failed to fetch groups", detail={"error": str(exc)}) from exc

    def fetch_group_participants_table(self) -> pd.DataFrame:
        """Return DataFrame of participant contact info enriched with joined_date and group_id."""
        participants = self.get_group_participants()
        contact_ids = ["".join([char for char in p.get("PhoneNumber", "") if char.isnumeric()]) for p in participants]
        rows: List[Dict[str, Any]] = []
        for cid in contact_ids:
            info = self.contact.get_contact_info(contact_id=cid)
            if info:
                rows.append(info)
            else:
                LOGGER.warning("contact_info_missing", extra={"contact_id": cid}, exc_info=True)
        df = pd.DataFrame(rows)
        if not df.empty:
            df["joined_date"] = pd.Timestamp.now(tz="Europe/Zurich")
            df["group_id"] = self.group_id
            if "id" in df.columns:
                df.rename(columns={"id": "uid"}, inplace=True)
        return df
