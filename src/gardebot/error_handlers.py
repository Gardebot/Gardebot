"""Centralized error handlers for Gardebot."""

from __future__ import annotations

from flask import Flask, Response, jsonify

from gardebot.common.logging_configuration import get_logger
from gardebot.errors import GardebotError

LOGGER = get_logger(__name__)


def register_error_handlers(app: Flask) -> None:
    """Attach error handlers to the Flask app."""

    @app.errorhandler(GardebotError)
    def handle_gardebot_error(exc: GardebotError) -> tuple[Response, int]:
        """Handle known GardebotError exceptions."""
        LOGGER.warning("domain_error", code=exc.code, detail=exc.detail, message=str(exc), http_status=exc.http_status, exc_info=True)
        return (
            jsonify(
                {
                    "status": "error",
                    "code": exc.code,
                    "message": exc.safe_message,
                    "detail": exc.detail or {},
                }
            ),
            exc.http_status,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception) -> tuple[Response, int]:
        """Catch-all handler for unexpected exceptions."""
        # Log stack trace
        LOGGER.exception("unhandled_exception", error=str(exc))
        # Generic sanitized response
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "internal_error",
                    "message": "Internal error.",
                }
            ),
            500,
        )
