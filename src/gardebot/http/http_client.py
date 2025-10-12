"""HTTP client wrapper around requests with retries and structured error handling."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

import requests  # type: ignore[import-untyped]

from gardebot.errors import ExternalServiceError  # ensure this exists
from gardebot.settings import settings

LOGGER = logging.getLogger(__name__)


class HttpClient:
    """Thin wrapper around requests.

    - Base URL joining
    - Timeouts
    - Optional retries (simple loop)
    - Structured exceptions (ExternalServiceError)
    """

    def __init__(
        self,
        base_url: str = settings.api.base_url,
        timeout: Union[int, float] = settings.api.timeout_seconds,
        headers: Optional[Dict[str, str]] = None,
        retries: int = settings.api.retry_attempts,
    ) -> None:
        """Basic constructor."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self.retries = max(0, retries)

    def _full_url(self, endpoint: str) -> str:
        """Construct full URL from base and endpoint."""
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return f"{self.base_url}{endpoint}"

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        json_body: Dict[str, Any] | None = None,
        params: Dict[str, Any] | None = None,
        raise_for_status: bool = False,
    ) -> requests.Response:
        """Make an HTTP request with retries and error handling."""
        url = self._full_url(endpoint)
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                LOGGER.debug(
                    "http_request",
                    extra={
                        "method": method,
                        "url": url,
                        "json_body": json_body,
                        "params": params,
                        "attempt": attempt,
                    },
                )
                resp = requests.request(
                    method=method.upper(),
                    url=url,
                    headers=self.headers,
                    json=json_body,
                    params=params,
                    timeout=self.timeout,
                )
                LOGGER.debug(
                    "http_response",
                    extra={
                        "status": resp.status_code,
                        "url": url,
                        "text": resp.text[:500],
                    },
                )
                if raise_for_status and not self.is_success(resp.status_code):
                    raise ExternalServiceError(
                        f"Non-success status {resp.status_code}",
                        detail={"status": resp.status_code, "url": url, "body": safe_response_preview(resp)},
                    )
                return resp
            except (requests.RequestException, ExternalServiceError) as exc:
                last_exc = exc
                LOGGER.warning(
                    "http_attempt_failed",
                    extra={"url": url, "attempt": attempt, "error": str(exc)},
                )
        if isinstance(last_exc, ExternalServiceError):
            raise last_exc
        raise ExternalServiceError(
            "HTTP request failed",
            detail={"url": url, "error": str(last_exc)},
        )

    def is_success(self, status: int) -> bool:
        """Return True if the HTTP status code indicates success (2xx)."""
        return 200 <= status < 300  # noqa: PLR2004


def safe_response_preview(resp: requests.Response, limit: int = 500) -> Union[Any, str]:
    """Get a safe preview of the response text, limited to `limit` characters."""
    try:
        return resp.text[:limit]
    except Exception:
        return "<unreadable>"
