"""Module to handle API requests from/to WAHA.

Adapted to use HttpClient internally while preserving original interface.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests  # type: ignore[import-untyped]

from gardebot.errors import ExternalServiceError
from gardebot.http.http_client import HttpClient
from gardebot.settings import settings

LOGGER = logging.getLogger(__name__)


class WahaRequest:
    """Handles requests to the WAHA API (legacy interface, now backed by HttpClient)."""

    def __init__(
        self,
        api_key: str = settings.api.api_key,
        base_url: str = settings.api.base_url,
        timeout: int = settings.api.timeout_seconds,
        headers: Optional[Dict[str, str]] = None,
        session: str = settings.api.session,
        retries: int = settings.api.retry_attempts,
    ) -> None:
        """Initialize the WahaRequest with API key and base URL."""
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.session = session
        self.headers = headers or {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
        }
        self._http = HttpClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self.headers,
            retries=retries,
        )

    def send_post_request(self, endpoint: str, payload: Dict[str, Any]) -> requests.Response:
        """Send a generic API POST request to WAHA."""
        try:
            resp = self._http.request("POST", endpoint, json_body=payload, raise_for_status=False)
            return resp
        except ExternalServiceError as exc:
            LOGGER.error("Error sending POST request: %s", exc)
            return self._sent_error_response(exc)
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Unexpected error in send_post_request: %s", exc)
            return self._sent_error_response(exc)

    def send_get_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """Send a generic API GET request to WAHA."""
        try:
            resp = self._http.request("GET", endpoint, params=params, raise_for_status=False)
            return resp
        except ExternalServiceError as exc:
            LOGGER.error("Error sending GET request: %s", exc)
            return self._sent_error_response(exc)
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Unexpected error in send_get_request: %s", exc)
            return self._sent_error_response(exc)

    def _is_success(self, status: int) -> bool:
        """Return True if the HTTP status code indicates success (2xx).

        Args:
            status (int): The HTTP status code to check.

        Returns:
            bool: True if status is in the range [200, 300), False otherwise.
        """
        return 200 <= status < 300  # noqa: PLR2004

    def _sent_error_response(self, exc: Exception) -> requests.Response:
        """Generate a mock error response (backwards-compatible)."""
        response = requests.Response()
        response.status_code = 500
        response._content = json.dumps({"error": str(exc)}).encode("utf-8")
        return response
