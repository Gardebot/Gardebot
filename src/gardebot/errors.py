"""Custom error classes for Gardebot."""

from typing import Any, Dict, Optional


class GardebotError(Exception):
    """Base class for Gardebot errors."""

    code = "internal_error"
    http_status = 500
    safe_message = "Internal error."

    def __init__(self, message: Optional[str] = None, detail: Optional[Dict[str, Any]] = None) -> None:
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


class NotFoundError(GardebotError):
    """Error raised when a requested resource is not found."""

    code = "not_found"
    http_status = 404
    safe_message = "Resource not found."


class AlreadyAssignedError(GardebotError):
    """Error raised when an assignment is attempted on an already assigned event."""

    code = "already_assigned"
    http_status = 400
    safe_message = "Event is already assigned."
