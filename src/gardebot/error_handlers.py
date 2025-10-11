"""Centralized error handlers for Gardebot."""

from __future__ import annotations

from typing import Any, Dict, Optional

from flask import Flask, Response, jsonify

from gardebot.common.logging_configuration import get_logger

LOGGER = get_logger(__name__)


class GardebotError(Exception):
    """Base domain error to allow fine-grained HTTP mapping later."""

    code = "internal_error"
    http_status = 500
    safe_message = "Internal error."
    detail: Optional[Dict[str, Any]] = None

    def __init__(self, message: Optional[str] = None, *, detail: Optional[Dict[str, Any]] = None):
        """Initialize the error with an optional message and detail."""
        super().__init__(message or self.safe_message)
        self.detail = detail or {}


class ValidationError(GardebotError):
    """Error raised for validation issues with incoming requests."""

    code = "validation_error"
    http_status = 422
    safe_message = "Invalid request."


class ExternalServiceError(GardebotError):
    """Error raised when an external service call fails."""

    code = "external_service_error"
    http_status = 502
    safe_message = "Upstream service error."


def register_error_handlers(app: Flask) -> None:
    """Attach error handlers to the Flask app."""

    @app.errorhandler(GardebotError)
    def handle_gardebot_error(exc: GardebotError) -> tuple[Response, int]:
        """Handle known GardebotError exceptions."""
        LOGGER.warning(
            "domain_error",
            code=exc.code,
            detail=exc.detail,
            message=str(exc),
            http_status=exc.http_status,
        )
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
