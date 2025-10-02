import io
import json
import logging
import unittest
from unittest import mock

from gardebot.common.logging_configuration import (
    bind_context,
    bind_request_id,
    clear_context,
    clear_request_id,
    configure_logging,
    get_logger,
)


class TestLoggingConfiguration(unittest.TestCase):
    def setUp(self) -> None:
        # Reset root handlers
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)

    def test_json_logging(self) -> None:
        with mock.patch("sys.stdout", new=io.StringIO()) as fake_out:
            configure_logging(force=True, json_logs=True, level="INFO")
            logger = get_logger(__name__)
            logger.info("test_event", answer=42)
            out = fake_out.getvalue().strip().splitlines()[-1]
            parsed = json.loads(out)
            # structlog JSONRenderer uses "event" for the main message
            self.assertEqual(parsed["event"], "test_event")
            self.assertEqual(parsed["answer"], 42)

    def test_human_logging(self) -> None:
        with mock.patch("sys.stdout", new=io.StringIO()) as fake_out:
            configure_logging(force=True, json_logs=False, level="DEBUG")
            logger = get_logger("x.y")
            logger.debug("hello_debug")
            out = fake_out.getvalue()
            self.assertIn("hello_debug", out)

    def test_idempotent(self) -> None:
        with mock.patch("sys.stdout", new=io.StringIO()):
            configure_logging(force=True, json_logs=False, level="INFO")
            root = logging.getLogger()
            before = len(root.handlers)
            configure_logging(force=False)  # should not add handlers
            after = len(root.handlers)
            self.assertEqual(before, after)

    def test_request_id_context(self) -> None:
        with mock.patch("sys.stdout", new=io.StringIO()) as fake_out:
            configure_logging(force=True, json_logs=True, level="INFO")
            bind_request_id("req-123")
            logger = get_logger("ctx")
            logger.info("context_event")
            clear_request_id()
            out = fake_out.getvalue().strip().splitlines()[-1]
            parsed = json.loads(out)
            self.assertEqual(parsed["request_id"], "req-123")
            self.assertEqual(parsed["event"], "context_event")

    def test_additional_context(self) -> None:
        with mock.patch("sys.stdout", new=io.StringIO()) as fake_out:
            configure_logging(force=True, json_logs=True, level="INFO")
            bind_context(user="alice", action="login")
            logger = get_logger("ctx2")
            logger.info("user_action")
            clear_context("user", "action")
            out = fake_out.getvalue().strip().splitlines()[-1]
            parsed = json.loads(out)
            self.assertEqual(parsed["user"], "alice")
            self.assertEqual(parsed["action"], "login")
            self.assertEqual(parsed["event"], "user_action")

    def test_disable_timestamps(self) -> None:
        with mock.patch("sys.stdout", new=io.StringIO()) as fake_out:
            configure_logging(force=True, json_logs=True, level="INFO", timestamps=False)
            logger = get_logger("no_ts")
            logger.info("no_timestamp")
            out = fake_out.getvalue().strip().splitlines()[-1]
            parsed = json.loads(out)
            self.assertNotIn("ts", parsed)
            self.assertEqual(parsed["event"], "no_timestamp")

    def test_log_levels(self) -> None:
        with mock.patch("sys.stdout", new=io.StringIO()) as fake_out:
            configure_logging(force=True, json_logs=True, level="WARNING")
            logger = get_logger("leveltest")
            logger.info("should_not_appear")
            logger.warning("should_appear")
            lines = fake_out.getvalue().strip().splitlines()
            # Only WARNING should be present
            self.assertTrue(any("should_appear" in l for l in lines))
            self.assertFalse(any("should_not_appear" in l for l in lines))
