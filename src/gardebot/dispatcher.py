"""Dispatcher for WAHA events to Gardebot handlers."""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict

import structlog

from gardebot.gardebot import Gardebot
from gardebot.settings import settings

LOGGER = structlog.get_logger(__name__)
Handler = Callable[[Dict[Any, Any]], None]


class EventDispatcher:
    """Maps inbound WAHA events to handler callables.

    Matching strategy: substring membership (backward compatible).
    """

    def __init__(self, gardebot: Gardebot) -> None:
        """Initialize with a Gardebot instance."""
        self.gardebot = gardebot
        self._mapping: Dict[str, Handler] = {
            "message": self.gardebot.process_messages,
            "poll.vote": self.gardebot.process_vote,
            "session.status": self._handle_session_status,
            "group.v2.participants": self._handle_group_participants,
        }

    def dispatch(self, payload: Dict[str, Any]) -> bool:
        """Dispatch the event to the appropriate handler."""
        event = payload.get("event")
        if not isinstance(event, str):
            LOGGER.warning("invalid_event_field", got=event)
            return False
        for key, func in self._mapping.items():
            if key in event:
                func(payload)
                return True
        LOGGER.info("unhandled_event", event=event)
        return False

    def _handle_session_status(self, payload: Dict[str, Any]) -> None:
        """Handle session status changes."""
        status = (payload.get("payload") or {}).get("status", "")
        if "WORKING" in status:
            LOGGER.info("session_status_working")
            self.gardebot.initialize()

    def _handle_group_participants(self, _payload: Dict[str, Any]) -> None:
        LOGGER.info(
            "participants_change_scheduled",
            delay=settings.server.postpone_sync_time,
        )
        threading.Timer(
            settings.server.postpone_sync_time,
            self.gardebot.update_sapeurs,
        ).start()
