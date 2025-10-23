"""High-level WAHA client returning parsed JSON or raising ExternalServiceError."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import requests  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.errors import ExternalServiceError
from gardebot.http.http_client import HttpClient
from gardebot.settings import settings

LOGGER = get_logger(__name__)


class WahaClient:
    """High-level WAHA client returning parsed JSON or raising ExternalServiceError."""

    def __init__(
        self,
        api_key: str = settings.api.api_key,
        base_url: str = settings.api.base_url,
        session: str = settings.api.session,
        timeout: int = settings.api.timeout_seconds,
        retries: int = settings.api.retry_attempts,
    ) -> None:
        """Initialize the WahaClient with API key and base URL."""
        self.session = session
        self._http = HttpClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": api_key,
            },
            retries=retries,
        )

    def extract_json(self, resp: Any) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Extract JSON from response or raise ExternalServiceError."""
        if isinstance(resp.json(), dict):
            return self.extract_json_dict(resp)
        elif isinstance(resp.json(), list):
            return self.extract_json_list(resp)
        else:
            raise ExternalServiceError(
                "Unexpected JSON response type",
                detail={"type": type(resp.json()).__name__},
            )

    @staticmethod
    def extract_json_dict(resp: Any) -> Dict[str, Any]:
        """Extract JSON from response or raise ExternalServiceError."""
        try:
            return dict(resp.json())
        except Exception as exc:  # pragma: no cover
            raise ExternalServiceError("Invalid JSON response", detail={"text": resp.text}) from exc

    @staticmethod
    def extract_json_list(resp: Any) -> List[Dict[str, Any]]:
        """Extract JSON list from response or raise ExternalServiceError."""
        try:
            data = resp.json()
            if not isinstance(data, list):
                raise ExternalServiceError(
                    "Expected JSON list response",
                    detail={"type": type(data).__name__},
                )
            return data
        except Exception as exc:  # pragma: no cover
            raise ExternalServiceError("Invalid JSON response", detail={"text": resp.text}) from exc

    def _ensure_success(self, resp: Any, error_message: str) -> None:
        """Raise ExternalServiceError if response status is not successful."""
        if not self._http.is_success(resp.status_code):
            raise ExternalServiceError(
                error_message,
                detail={"status": resp.status_code, "body": resp.text},
            )

    def get(
        self,
        endpoint: str,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        raise_for_status: bool = False,
    ) -> requests.Response:
        """Make a GET request to the WAHA API."""
        return self._http.request(
            method="GET",
            endpoint=endpoint,
            json_body=json_body,
            params=params,
            raise_for_status=raise_for_status,
        )

    def post(
        self,
        endpoint: str,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        raise_for_status: bool = False,
    ) -> requests.Response:
        """Make a POST request to the WAHA API."""
        return self._http.request(
            method="POST",
            endpoint=endpoint,
            json_body=json_body,
            params=params,
            raise_for_status=raise_for_status,
        )
