"""Message service: parsing, command routing, echo behavior."""

from __future__ import annotations

from typing import Any, Dict, Optional

from gardebot.common.logging_configuration import get_logger

LOGGER = get_logger(__name__)


class MessageService:
    """Encapsulates MESSAGE domain logic (parsing, command routing, echo behavior).

    It delegates actual sending to a sender object (Gardebot or a Waha adapter)
    that exposes send_text(to_number: str, message_text: str).
    """

    def __init__(self, sender: Any) -> None:
        """Sender: object providing send_text(to_number: str, message_text: str) and (optionally later) other message-related operations."""
        self._sender = sender

    def handle_webhook_payload(self, data: Dict[str, Any]) -> None:
        """Public entry point to process an inbound message event.

        (Will accept typed model in PR 4; currently raw dict.)
        """
        payload = data.get("payload")
        if payload is None:
            LOGGER.info("message_no_payload")
            return

        try:
            if payload.get("from_me"):
                LOGGER.debug("message_ignored_from_self")
                return

            body: Optional[str] = payload.get("body")
            from_number: Optional[str] = payload.get("from")
            timestamp = payload.get("timestamp")

            if not from_number:
                LOGGER.warning("message_missing_from_field")
                return

            # Basic classification (extend after PR 4 with typed model)
            if body is None:
                LOGGER.info("message_empty_body", sender=from_number)
                return

            if self._is_command(body):
                self._handle_command(body, from_number)
            else:
                self._echo(body, from_number, timestamp)
        except Exception as exc:  # PR 6: replace by domain error
            LOGGER.exception("message_processing_error", error=str(exc), raw=data)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _is_command(self, text: str) -> bool:
        return bool(text) and text.startswith("!")

    def _handle_command(self, text: str, from_number: str) -> None:
        # Simple demonstration; later expand a command registry/dispatcher.
        cmd, _, args = text.partition(" ")
        cmd_lower = cmd.lower()
        if cmd_lower == "!ping":
            self._sender.send_text(
                to_number=from_number,
                message_text=f"[pong] {args or ''}".strip(),
            )
            LOGGER.info("command_ping_executed", sender=from_number)
        else:
            self._sender.send_text(
                to_number=from_number,
                message_text=f"Unknown command: {cmd}",
            )
            LOGGER.info("command_unknown", command=cmd, sender=from_number)

    def _echo(self, body: str, from_number: str, timestamp: Any) -> None:
        self._sender.send_text(
            to_number=from_number,
            message_text=f"Echoing, you sent : '{body}' at {timestamp}",
        )
        LOGGER.info("message_echo_sent", sender=from_number, body=body)
