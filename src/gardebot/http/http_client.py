"""HTTP client wrapper around requests with retries, exponential backoff and structured error handling."""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional, Union

import requests  # type: ignore[import-untyped]

from gardebot.errors import ExternalServiceError
from gardebot.settings import settings

LOGGER = logging.getLogger(__name__)


def _exponential_backoff(attempt: int, base: float, cap: float, jitter: bool = True) -> float:
    """Compute exponential backoff (attempt is 0-based)."""
    delay: float = min(cap, base * (2**attempt))
    if jitter:
        delay = random.uniform(0, delay)
    return delay


def safe_response_preview(resp: requests.Response, limit: int = 500) -> str:
    """Get a safe preview of the response text, limited to `limit` characters."""
    try:
        response: str = resp.text[:limit]
        return response
    except Exception:  # pragma: no cover
        return "<unreadable>"


class HttpClient:
    """Thin wrapper around requests.

    - Base URL joining
    - Timeouts
    - Configurable retries with exponential backoff + jitter
    - Structured exceptions (ExternalServiceError)
    """

    def __init__(
        self,
        base_url: str = settings.api.base_url,
        timeout: Union[int, float] = settings.api.timeout_seconds,
        headers: Optional[Dict[str, str]] = None,
        retries: int = settings.api.retry_attempts,
        backoff_base: float = settings.api.retry_backoff_seconds,
        backoff_cap: float = settings.api.retry_backoff_max_seconds,
        jitter: bool = True,
    ) -> None:
        """Initialize the HTTP client."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self.retries = max(0, retries)
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.jitter = jitter

    def _full_url(self, endpoint: str) -> str:
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"{self.base_url}{endpoint}"

    def is_success(self, status: int) -> bool:
        """Check if the status code is a success (2xx)."""
        return 200 <= status < 300  # noqa: PLR2004

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        raise_for_status: bool = False,
    ) -> requests.Response:
        """Make an HTTP request with retries + exponential backoff.

        raise_for_status:
            If True, non-2xx statuses raise ExternalServiceError.
        """
        url = self._full_url(endpoint)
        last_exc: Optional[Exception] = None

        for attempt in range(self.retries + 1):
            try:
                LOGGER.debug(
                    "http_request",
                    extra={
                        "method": method.upper(),
                        "url": url,
                        "json_body": json_body,
                        "params": params,
                        "attempt": attempt,
                        "retries": self.retries,
                    },
                    exc_info=True,
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
                        "body_excerpt": safe_response_preview(resp),
                    },
                )
                if raise_for_status and not self.is_success(resp.status_code):
                    raise ExternalServiceError(
                        f"Non-success status {resp.status_code}",
                        detail={
                            "status": resp.status_code,
                            "url": url,
                            "body": safe_response_preview(resp),
                        },
                    )
                return resp
            except (requests.RequestException, ExternalServiceError) as exc:
                last_exc = exc
                should_retry = attempt < self.retries
                LOGGER.warning(
                    "http_attempt_failed",
                    extra={
                        "url": url,
                        "attempt": attempt,
                        "will_retry": should_retry,
                        "error": str(exc),
                    },
                    exc_info=True,
                )
                if should_retry:
                    delay = _exponential_backoff(
                        attempt=attempt,
                        base=self.backoff_base,
                        cap=self.backoff_cap,
                        jitter=self.jitter,
                    )
                    LOGGER.info(
                        "http_retry_scheduled",
                        extra={"url": url, "next_attempt": attempt + 1, "sleep": round(delay, 3)},
                    )
                    time.sleep(delay)

        if isinstance(last_exc, ExternalServiceError):
            raise last_exc
        raise ExternalServiceError(
            "HTTP request failed",
            detail={"url": url, "error": str(last_exc) if last_exc else "unknown"},
        )
