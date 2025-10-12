"""High-level WAHA client returning parsed JSON or raising ExternalServiceError."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from gardebot.errors import ExternalServiceError
from gardebot.http.http_client import HttpClient
from gardebot.settings import settings

LOGGER = logging.getLogger(__name__)


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

    def send_text(self, to_number: str, text: str) -> Dict[str, Any]:
        """Send a text message to a WhatsApp number."""
        payload = {"session": self.session, "chatId": to_number, "text": text}
        resp = self._http.request("POST", "/api/sendText", json_body=payload, raise_for_status=True)
        return self._extract_json(resp)

    def send_event(
        self,
        to_number: str,
        name: str,
        description: str,
        start_time: int,
        end_time: int,
        location: str,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a calendar event to a chat."""
        payload = {
            "chatId": to_number,
            "event": {
                "name": name,
                "description": description,
                "startTime": start_time,
                "endTime": end_time,
                "location": {"name": location},
            },
        }
        if reply_to:
            payload["reply_to"] = reply_to
        endpoint = f"/api/{self.session}/events"
        resp = self._http.request("POST", endpoint, json_body=payload, raise_for_status=True)
        return self._extract_json(resp)

    def get_message(self, chat_id: str, message_id: str) -> Dict[str, Any]:
        """Fetch a message by ID."""
        endpoint = f"/api/{self.session}/chats/{chat_id}/messages/{message_id}"
        resp = self._http.request("GET", endpoint, raise_for_status=True)
        return self._extract_json(resp)

    @staticmethod
    def _extract_json(resp: Any) -> Dict[str, Any]:
        """Extract JSON from response or raise ExternalServiceError."""
        try:
            return dict(resp.json())
        except Exception as exc:  # pragma: no cover
            raise ExternalServiceError("Invalid JSON response", detail={"text": resp.text}) from exc

    def _ensure_success(self, resp: Any, error_message: str) -> None:
        """Raise ExternalServiceError if response status is not successful."""
        if not self._http.is_success(resp.status_code):
            raise ExternalServiceError(
                error_message,
                detail={"status": resp.status_code, "body": resp.text},
            )
