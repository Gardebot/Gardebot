"""Dispatcher for WAHA events to Gardebot handlers."""

from __future__ import annotations

from typing import Any, Callable, Dict

from gardebot.common.debounce import Debouncer
from gardebot.common.logging_configuration import configure_logging, get_logger
from gardebot.gardebot import Gardebot
from gardebot.settings import settings

configure_logging(
    level=settings.logging.level,
    json_logs=bool(settings.logging.json_logs),
    color=settings.logging.color,
    timestamps=settings.logging.timestamps,
)
LOGGER = get_logger(__name__)
Handler = Callable[[Dict[Any, Any]], None]


class EventDispatcher:
    """Maps inbound WAHA events to handler callables.

    Matching strategy: substring membership (backward compatible).
    """

    def __init__(self, gardebot: Gardebot) -> None:
        """Initialize with a Gardebot instance."""
        self.gardebot = gardebot
        self._mapping: Dict[str, Handler] = {
            "message": self.gardebot.handle_incoming_message,
            "poll.vote": self.gardebot.process_vote,
            "session.status": self._handle_session_status,
            "group.v2.participants": self._handle_group_participants,
        }
        self._participant_debouncer = Debouncer(settings.server.postpone_sync_time, self.gardebot.update_sapeurs)
        self._initialize_debouncer = Debouncer(settings.server.postpone_sync_time, self.gardebot.initialize)

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
        tmp_payload = payload.get("payload")
        if not tmp_payload:
            LOGGER.debug("session_status_no_payload")
            return

        status = tmp_payload.get("status")
        if "WORKING" in status:
            LOGGER.info("session_status_change %s. Starting gardebot.initialize in %s seconds.", status, settings.server.postpone_sync_time)
            self._initialize_debouncer.trigger()
        return None

    def _handle_group_participants(self, _payload: Dict[str, Any]) -> None:
        """Handle group participant changes with debouncing."""
        LOGGER.info("participants_change_trigger")
        self._participant_debouncer.trigger()
