# mypy: disable-error-code="method-assign, attr-defined, type-var"
"""Unit tests for error handlers module."""

import unittest
from unittest.mock import patch

from flask import Flask

from gardebot.error_handlers import register_error_handlers
from gardebot.errors import (
    AlreadyAssignedError,
    ExternalServiceError,
    GardebotError,
    NotFoundError,
    ValidationError,
)


class TestErrorHandlers(unittest.TestCase):
    """Test cases for error handlers."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.app = Flask(__name__)
        register_error_handlers(self.app)
        self.client = self.app.test_client()

    def test_gardebot_error_handler(self) -> None:
        """Test GardebotError handling."""

        @self.app.route("/test-error")
        def test_route() -> None:
            raise ValidationError("Test validation error", {"field": "value"})

        response = self.client.get("/test-error")

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["code"], "validation_error")
        self.assertEqual(data["message"], "Invalid request.")
        self.assertEqual(data["detail"], {"field": "value"})

    def test_external_service_error_handler(self) -> None:
        """Test ExternalServiceError handling."""

        @self.app.route("/test-external-error")
        def test_route() -> None:
            raise ExternalServiceError("Service unavailable")

        response = self.client.get("/test-external-error")

        self.assertEqual(response.status_code, 502)
        data = response.get_json()
        self.assertEqual(data["code"], "external_service_error")

    def test_not_found_error_handler(self) -> None:
        """Test NotFoundError handling."""

        @self.app.route("/test-not-found")
        def test_route() -> None:
            raise NotFoundError("Resource not found")

        response = self.client.get("/test-not-found")

        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertEqual(data["code"], "not_found")

    def test_already_assigned_error_handler(self) -> None:
        """Test AlreadyAssignedError handling."""

        @self.app.route("/test-already-assigned")
        def test_route() -> None:
            raise AlreadyAssignedError("Event already assigned")

        response = self.client.get("/test-already-assigned")

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["code"], "already_assigned")

    def test_generic_exception_handler(self) -> None:
        """Test generic exception handling."""

        @self.app.route("/test-generic-error")
        def test_route() -> None:
            raise RuntimeError("Unexpected error")

        response = self.client.get("/test-generic-error")

        self.assertEqual(response.status_code, 500)
        data = response.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["code"], "internal_error")
        self.assertEqual(data["message"], "Internal error.")
        self.assertNotIn("detail", data)

    def test_custom_gardebot_error(self) -> None:
        """Test custom GardebotError subclass."""

        class CustomError(GardebotError):
            code = "custom_error"
            http_status = 418
            safe_message = "Custom error message"

        @self.app.route("/test-custom-error")
        def test_route() -> None:
            raise CustomError("Internal custom error", {"custom": "data"})

        response = self.client.get("/test-custom-error")

        self.assertEqual(response.status_code, 418)
        data = response.get_json()
        self.assertEqual(data["code"], "custom_error")
        self.assertEqual(data["message"], "Custom error message")
        self.assertEqual(data["detail"], {"custom": "data"})

    def test_gardebot_error_without_detail(self) -> None:
        """Test GardebotError without detail."""

        @self.app.route("/test-no-detail")
        def test_route() -> None:
            raise ValidationError("Simple error")

        response = self.client.get("/test-no-detail")

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["detail"], {})

    def test_error_logging(self) -> None:
        """Test that errors are logged appropriately."""

        @self.app.route("/test-logging")
        def test_route() -> None:
            raise ValidationError("Test for logging")

        with patch("gardebot.error_handlers.LOGGER") as mock_logger:
            response = self.client.get("/test-logging")

        self.assertEqual(response.status_code, 422)
        mock_logger.warning.assert_called_once()

        # Check log call arguments
        call_args = mock_logger.warning.call_args
        self.assertEqual(call_args[0][0], "domain_error")
        self.assertEqual(call_args[1]["code"], "validation_error")

    def test_generic_error_logging(self) -> None:
        """Test that generic errors are logged with exception info."""

        @self.app.route("/test-generic-logging")
        def test_route() -> None:
            raise ValueError("Test generic error")

        with patch("gardebot.error_handlers.LOGGER") as mock_logger:
            response = self.client.get("/test-generic-logging")

        self.assertEqual(response.status_code, 500)
        mock_logger.exception.assert_called_once()

        # Check log call arguments
        call_args = mock_logger.exception.call_args
        self.assertEqual(call_args[0][0], "unhandled_exception")


if __name__ == "__main__":
    unittest.main()
