"""Validation utilities for inbound events.

Currently only specialized validation for 'message' events.
Other events use minimal presence checking until later refactors.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import ValidationError

from gardebot.models.message_event import MessageEventEnvelope


class MessageValidationError(Exception):
    """Raised when a message event fails validation."""


def validate_message_event(data: Dict[str, Any]) -> MessageEventEnvelope:
    """Validate a 'message' event payload into a typed Pydantic structure.

    Raises:
        MessageValidationError: if validation fails.
    """
    try:
        return MessageEventEnvelope(**data)
    except ValidationError as exc:
        raise MessageValidationError(str(exc)) from exc


def basic_event_presence_check(data: Dict[str, Any]) -> bool:
    """Minimal check for non-message events (presence of 'event' key).

    Returns:
        bool: True if 'event' appears to be a non-empty string.
    """
    evt = data.get("event")
    return isinstance(evt, str) and len(evt) > 0
