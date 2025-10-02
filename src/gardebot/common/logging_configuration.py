"""Structured logging configuration using structlog.

Features:
- JSON or pretty console output (env LOG_JSON=true/false)
- Explicit log level via LOG_LEVEL (default: INFO)
- UTC timestamps (ISO 8601)
- Optional color in console mode (LOG_COLOR=true)
- Idempotent configuration (safe to call multiple times)
- Context binding helpers (request_id, arbitrary key/value)
- Ready for later correlation & metrics integration

Environment Variables:
    LOG_LEVEL=INFO|DEBUG|WARNING|ERROR|CRITICAL
    LOG_JSON=true|false
    LOG_COLOR=true|false        (only for non-JSON mode)
    LOG_TIMESTAMPS=true|false   (disable timestamps if needed)

Usage:
    from gardebot.common.logging_configuration import configure_logging, get_logger
    configure_logging()
    logger = get_logger(__name__)
    logger.info("app_started", version="1.2.3")
"""

from __future__ import annotations

import contextvars
import logging
import os
import sys
import time
from typing import Any, Callable, Dict, Optional

import structlog

# -----------------------------------------------------------------------------
# State & Context
# -----------------------------------------------------------------------------

_LOGGING_ALREADY_CONFIGURED = False

# Context variables (per logical request / task)
_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_additional_context_var: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("additional_context", default={})

VALID_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


# -----------------------------------------------------------------------------
# Utility: Level Resolution
# -----------------------------------------------------------------------------
def _resolve_level(level_str: str | None) -> int:
    if not level_str:
        return logging.INFO
    return VALID_LEVELS.get(level_str.upper(), logging.INFO)


# -----------------------------------------------------------------------------
# Processors
# -----------------------------------------------------------------------------
def _inject_context(
    logger: Any,  # noqa: ARG001
    method_name: str,  # noqa: ARG001
    event_dict: Dict[str, Optional[str]],
) -> Dict[str, Optional[str]]:
    """Processor that injects bound contextvars into the event dict."""
    req_id = _request_id_var.get()
    if req_id:
        event_dict.setdefault("request_id", req_id)

    extra_ctx = _additional_context_var.get()
    if extra_ctx:
        # Do not overwrite existing keys explicitly set on the log call
        for key, value in extra_ctx.items():
            event_dict.setdefault(key, value)

    return event_dict


def _utc_iso_time(_: Any, __: str, event_dict: Dict[str, Any]) -> Dict[str, str]:
    # Timestamp injection (if enabled)
    event_dict["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    return event_dict


# -----------------------------------------------------------------------------
# Public Context API
# -----------------------------------------------------------------------------
def bind_request_id(request_id: str) -> None:
    """Bind a request ID to subsequent log calls in this context."""
    _request_id_var.set(request_id)


def clear_request_id() -> None:
    """Clear the bound request ID."""
    _request_id_var.set(None)


def bind_context(**kwargs: Any) -> None:
    """Bind arbitrary contextual key/value pairs (non-destructive)."""
    current = _additional_context_var.get().copy()
    current.update(kwargs)
    _additional_context_var.set(current)


def clear_context(*keys: str) -> None:
    """Clear specific context keys or all if none specified."""
    if not keys:
        _additional_context_var.set({})
        return
    current = _additional_context_var.get().copy()
    for k in keys:
        current.pop(k, None)
    _additional_context_var.set(current)


# -----------------------------------------------------------------------------
# Main Configuration
# -----------------------------------------------------------------------------
def configure_logging(
    *,
    force: bool = False,
    level: str | None = None,
    json_logs: bool | None = None,
    color: bool | None = None,
    timestamps: bool | None = None,
) -> None:
    """Configure structured logging with structlog + stdlib bridging.

    Args:
        force: Reconfigure even if already configured.
        level: Override LOG_LEVEL environment.
        json_logs: Override LOG_JSON environment.
        color: Override LOG_COLOR (only applied when not JSON).
        timestamps: Override LOG_TIMESTAMPS (disable for performance).
    """
    global _LOGGING_ALREADY_CONFIGURED  # noqa: PLW0603

    if _LOGGING_ALREADY_CONFIGURED and not force:
        return

    env_level = level or os.getenv("LOG_LEVEL", "INFO")
    env_json = json_logs if json_logs is not None else os.getenv("LOG_JSON", "true").lower() == "true"
    env_color = color if color is not None else os.getenv("LOG_COLOR", "false").lower() == "true"
    env_timestamps = timestamps if timestamps is not None else os.getenv("LOG_TIMESTAMPS", "true").lower() == "true"

    resolved_level = _resolve_level(env_level)

    # Configure stdlib root logger (structlog will wrap this)
    logging.basicConfig(
        level=resolved_level,
        format="%(message)s",  # structlog will render final shape
        stream=sys.stdout,
    )

    # Chain of processors BEFORE final rendering
    shared_processors: list[Callable[..., Any]] = [
        _inject_context,
    ]
    if env_timestamps:
        shared_processors.append(_utc_iso_time)

    shared_processors.extend(
        [
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Ensure event_dict keys are all native strings
            structlog.processors.UnicodeDecoder(),
        ]
    )

    if env_json:
        renderer: Any = structlog.processors.JSONRenderer(sort_keys=True)
    else:
        # Pretty console renderer
        renderer = structlog.dev.ConsoleRenderer(colors=env_color)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _LOGGING_ALREADY_CONFIGURED = True

    # Log bootstrap info using the new system
    logger = get_logger(__name__)
    logger.info(
        "logging_configured",
        level=env_level,
        effective_level=resolved_level,
        json=env_json,
        color=env_color,
        timestamps=env_timestamps,
    )


# -----------------------------------------------------------------------------
# Logger Getter
# -----------------------------------------------------------------------------
def get_logger(name: str | None = None) -> Any:
    """Get a structlog logger (wrapper around stdlib logger)."""
    if name is None:
        return structlog.get_logger()
    return structlog.get_logger(name)
