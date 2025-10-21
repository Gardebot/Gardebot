"""Dispatcher for WAHA events to Gardebot handlers (exact matching)."""

from __future__ import annotations

from typing import Any, Callable, Dict

from gardebot.common.debounce import Debouncer
from gardebot.common.logging_configuration import get_logger
from gardebot.gardebot import Gardebot
from gardebot.metrics import record_participant_sync
from gardebot.settings import settings

LOGGER = get_logger(__name__)
Handler = Callable[[Dict[str, Any]], None]


class EventDispatcher:
    """Maps inbound WAHA events to handler callables using exact event names."""

    def __init__(self, gardebot: Gardebot) -> None:
        """Initialize with a Gardebot instance."""
        self.gardebot = gardebot
        self._handlers: Dict[str, Handler] = {
            "message": self.gardebot.handle_incoming_message,
            "poll.vote": self.gardebot.handle_incoming_vote,
            "session.status": self._handle_session_status,
            "group.v2.participants": self._handle_group_participants,
        }
        self._participant_debouncer = Debouncer(settings.server.postpone_sync_time, self._debounced_participant_sync)
        self._initialize_debouncer = Debouncer(settings.server.postpone_sync_time, self._debounced_initialize)

    def dispatch(self, payload: Dict[str, Any]) -> bool:
        """Dispatch exact event; return True if handled."""
        event = payload.get("event")
        if not isinstance(event, str):
            LOGGER.warning("invalid_event_field", got=event)
            return False
        handler = self._handlers.get(event)
        if handler is None:
            LOGGER.info("unhandled_event", event=event)
            return False
        handler(payload)
        return True

    def _handle_session_status(self, payload: Dict[str, Any]) -> None:
        """Handle session status changes."""
        tmp_payload = payload.get("payload")
        if not tmp_payload:
            LOGGER.debug("session_status_no_payload")
            return

        status = tmp_payload.get("status")
        if "WORKING" in status:  # TODO: UNCOMMENT WHEN READY
            LOGGER.info("session_status_change %s. Starting gardebot.initialize in %s seconds.", status, settings.server.postpone_sync_time)
            self._initialize_debouncer.trigger()

    def _handle_group_participants(self, _payload: Dict[str, Any]) -> None:
        """Handle group participant changes with debouncing."""
        LOGGER.info("participants_change_trigger")
        self._participant_debouncer.trigger()

    def _debounced_participant_sync(self) -> None:
        """Sync participants after debounce period."""
        record_participant_sync()
        self.gardebot.sapeur_service.synchronize_sapeurs()

    def _debounced_initialize(self) -> None:
        """Initialize Gardebot after debounce period."""
        self.gardebot.initialize()
