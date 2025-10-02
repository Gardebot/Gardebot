"""Module to handle API requests from/to WAHA."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests  # type: ignore[import-untyped]

from gardebot.config import API_CONFIG, SUCCESS_STATUS_CODE

LOGGER = logging.getLogger(__name__)


class WahaRequest:
    """Handles requests to the WAHA API."""

    def __init__(
        self,
        api_key: str = API_CONFIG["api_key"],
        base_url: str = API_CONFIG["base_url"],
        timeout: int = API_CONFIG["timeout"],
        headers: Optional[Dict[str, str]] = None,
        session: str = API_CONFIG["session"],
    ) -> None:
        """Initialize the WahaRequest instance."""
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.session = session
        if headers is not None:
            self.headers = headers
        else:
            self.headers = {
                "Content-Type": "application/json",
                "X-Api-Key": self.api_key,
            }

    def send_post_request(self, endpoint: str, payload: Dict[str, Any]) -> requests.Response:
        """Send a generic API POST request to WAHA."""
        try:
            url = f"{self.base_url}{endpoint}"
            LOGGER.debug("POST %s payload=%s", url, payload)
            response = requests.post(
                url=url,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=self.timeout,
            )
            LOGGER.debug("Response %s: %s", response.status_code, response.text)
            return response
        except Exception as exc:
            LOGGER.error("Error sending API request: %s", exc)
            return self._sent_error_response(exc)

    def send_get_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """Send a generic API GET request to WAHA."""
        try:
            url = f"{self.base_url}{endpoint}"
            LOGGER.debug("GET %s", url)
            response = requests.get(
                url,
                headers=self.headers,
                timeout=self.timeout,
                params=params,
            )
            LOGGER.debug("Response %s: %s", response.status_code, response.text)
            return response
        except Exception as exc:
            LOGGER.error("Error sending API request: %s", exc)
            return self._sent_error_response(exc)

    def _is_success(self, status: int) -> bool:
        """Check if the status code indicates a successful response."""
        return SUCCESS_STATUS_CODE <= status < 300  # noqa: PLR2004

    def _sent_error_response(self, exc: Exception) -> requests.Response:
        """Generate a mock error response."""
        response = requests.Response()
        response.status_code = 500
        response._content = json.dumps({"error": str(exc)}).encode("utf-8")
        return response
