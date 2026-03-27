# mypy: disable-error-code="method-assign, attr-defined"
"""Unit tests for logging configuration module."""

import logging
import os
import unittest
from contextlib import contextmanager
from io import StringIO
from typing import Any
from unittest.mock import patch

import gardebot.common.logging_configuration
from gardebot.common.logging_configuration import (
    _additional_context_var,
    _request_id_var,
    _resolve_level,
    bind_context,
    bind_request_id,
    clear_context,
    clear_request_id,
    configure_logging,
    get_logger,
)


class TestLoggingConfiguration(unittest.TestCase):
    """Test cases for logging configuration."""

    def setUp(self) -> None:
        """Set up test fixtures."""

        gardebot.common.logging_configuration._LOGGING_ALREADY_CONFIGURED = False

    def test_resolve_level(self) -> None:
        """Test log level resolution."""
        self.assertEqual(_resolve_level("DEBUG"), logging.DEBUG)
        self.assertEqual(_resolve_level("INFO"), logging.INFO)
        self.assertEqual(_resolve_level("WARNING"), logging.WARNING)
        self.assertEqual(_resolve_level("ERROR"), logging.ERROR)
        self.assertEqual(_resolve_level("CRITICAL"), logging.CRITICAL)
        self.assertEqual(_resolve_level("INVALID"), logging.INFO)
        self.assertEqual(_resolve_level(None), logging.INFO)
        self.assertEqual(_resolve_level("debug"), logging.DEBUG)  # Case insensitive

    def test_bind_request_id(self) -> None:
        """Test binding request ID."""
        bind_request_id("test-123")

        self.assertEqual(_request_id_var.get(), "test-123")

    def test_clear_request_id(self) -> None:
        """Test clearing request ID."""
        bind_request_id("test-123")
        clear_request_id()

        self.assertIsNone(_request_id_var.get())

    def test_bind_context(self) -> None:
        """Test binding additional context."""
        bind_context(user_id="123", action="test")

        context = _additional_context_var.get()
        self.assertEqual(context["user_id"], "123")
        self.assertEqual(context["action"], "test")

    def test_clear_context_all(self) -> None:
        """Test clearing all context."""
        bind_context(user_id="123", action="test")
        clear_context()

        self.assertEqual(_additional_context_var.get(), {})

    def test_clear_context_specific_keys(self) -> None:
        """Test clearing specific context keys."""
        bind_context(user_id="123", action="test", session="abc")
        clear_context("user_id", "nonexistent")

        context = _additional_context_var.get()
        self.assertNotIn("user_id", context)
        self.assertIn("action", context)
        self.assertIn("session", context)

    @patch.dict(os.environ, {}, clear=True)
    def test_configure_logging_defaults(self) -> None:
        """Test logging configuration with defaults."""
        configure_logging()

        # Should not raise error and should be configured
        logger = get_logger(__name__)
        self.assertIsNotNone(logger)

    @patch.dict(os.environ, {"LOG_LEVEL": "DEBUG", "LOG_JSON": "true", "LOG_COLOR": "true", "LOG_TIMESTAMPS": "false"})
    def test_configure_logging_env_vars(self) -> None:
        """Test logging configuration with environment variables."""
        configure_logging()

        logger = get_logger(__name__)
        self.assertIsNotNone(logger)

    def test_configure_logging_explicit_params(self) -> None:
        """Test logging configuration with explicit parameters."""
        configure_logging(level="WARNING", json_logs=False, color=True, timestamps=False)

        logger = get_logger(__name__)
        self.assertIsNotNone(logger)

    def test_configure_logging_idempotent(self) -> None:
        """Test that configure_logging can be called multiple times safely."""
        configure_logging()
        configure_logging()  # Should not cause issues

        logger = get_logger(__name__)
        self.assertIsNotNone(logger)

    def test_configure_logging_force(self) -> None:
        """Test forcing reconfiguration."""
        configure_logging()
        configure_logging(force=True, level="ERROR")

        logger = get_logger(__name__)
        self.assertIsNotNone(logger)

    def test_get_logger_with_name(self) -> None:
        """Test getting logger with specific name."""
        configure_logging()
        logger = get_logger("test.module")
        self.assertIsNotNone(logger)

    def test_get_logger_without_name(self) -> None:
        """Test getting logger without name."""
        configure_logging()
        logger = get_logger()
        self.assertIsNotNone(logger)

    @contextmanager
    def capture_logs(self) -> Any:
        """Context manager to capture log output."""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        try:
            yield log_capture
        finally:
            root_logger.removeHandler(handler)

    def test_context_injection(self) -> None:
        """Test that context is injected into logs."""
        configure_logging(json_logs=False)

        bind_request_id("req-123")
        bind_context(user="testuser")

        logger = get_logger(__name__)

        with self.capture_logs() as _:
            logger.info("test message")

        clear_request_id()
        clear_context()

    def test_timestamp_injection(self) -> None:
        """Test timestamp injection."""
        configure_logging(timestamps=True, json_logs=False)

        logger = get_logger(__name__)

        with self.capture_logs() as _:
            logger.info("test with timestamp")

    def test_logging_bootstrap_message(self) -> None:
        """Test that bootstrap message is logged."""
        with self.capture_logs() as log_output:
            configure_logging(level="DEBUG")
            log_content = log_output.getvalue()

        # Should contain configuration info
        self.assertIn("logging_configured", log_content)


if __name__ == "__main__":
    unittest.main()
