"""Service to handle incoming messages and respond to commands."""

from __future__ import annotations

from typing import Any, Dict

from gardebot.common.logging_configuration import get_logger

LOGGER = get_logger(__name__)


class MessageService:
    """Service to handle incoming messages and respond to commands."""

    def __init__(self, waha_client: Any, data_manager: Any) -> None:
        """Initializes the MessageService with WAHA client and DataManager."""
        self.waha = waha_client
        self.data = data_manager

    def handle(self, payload: Dict[str, Any]) -> None:
        """Process incoming message payloads and respond to commands."""
        message = (payload.get("payload") or {}).get("message")
        if not isinstance(message, Dict):
            LOGGER.warning("message_missing")
            return
        text = message.get("text") or ""
        if text.startswith("!ping"):
            self._reply(message, "pong")
        return

    def _reply(self, message: Dict[str, Any], text: str) -> None:
        """Send a reply to the given message."""
        chat_id = message.get("from")
        if not chat_id:
            LOGGER.warning("missing_from_field")
            return
        try:
            self.waha.send_text(chat_id=chat_id, text=text)
            LOGGER.info("message_replied", chat=chat_id)
        except Exception as exc:  # replaced later
            LOGGER.exception("reply_failed", error=str(exc))
        return
