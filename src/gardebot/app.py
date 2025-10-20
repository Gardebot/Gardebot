"""Main Flask application for handling WAHA webhook events and providing metrics."""

from __future__ import annotations

import uuid
from time import time
from typing import Dict

from flask import Flask, jsonify, request
from flask.wrappers import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from gardebot.common.logging_configuration import bind_request_id, clear_request_id, configure_logging, get_logger
from gardebot.dispatcher import EventDispatcher
from gardebot.error_handlers import register_error_handlers
from gardebot.gardebot import Gardebot
from gardebot.metrics import record_error, record_event
from gardebot.settings import settings
from gardebot.validation import (
    MessageValidationError,
    basic_event_presence_check,
    validate_message_event,
)

# Single logging bootstrap (avoid multi-module reconfiguration)
configure_logging(
    level=settings.logging.level,
    json_logs=bool(settings.logging.json_logs),
    color=settings.logging.color,
    timestamps=settings.logging.timestamps,
)
LOGGER = get_logger(__name__)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    bot = Gardebot()
    dispatcher = EventDispatcher(bot)
    register_error_handlers(app)

    @app.route("/health", methods=["GET"])
    def health() -> tuple[Response, int]:
        """Simple health check endpoint."""
        return jsonify({"status": "ok"}), 200

    @app.route("/metrics", methods=["GET"])
    def metrics() -> tuple[bytes, int, Dict[str, str]]:
        """Prometheus metrics endpoint."""
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    @app.route("/webhook", methods=["GET", "POST"])
    def webhook() -> tuple[Response, int]:
        correlation_id = str(uuid.uuid4())
        bind_request_id(correlation_id)
        try:
            if request.method == "GET":
                LOGGER.info("webhook_ping")
                return jsonify({"status": "ok", "correlation_id": correlation_id}), 200

            data = request.get_json(silent=True)
            if data is None:
                LOGGER.warning("invalid_json")
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "invalid_json",
                            "correlation_id": correlation_id,
                        }
                    ),
                    400,
                )

            event_value = data.get("event", "Unknown")
            if event_value == "message":
                try:
                    _ = validate_message_event(data)
                except MessageValidationError as exc:
                    LOGGER.warning("invalid_message_payload", detail=str(exc), exc_info=True)
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "invalid_message_payload",
                                "correlation_id": correlation_id,
                            }
                        ),
                        422,
                    )
            elif not basic_event_presence_check(data):
                LOGGER.warning("invalid_non_message_event_shape")
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "invalid_event",
                            "correlation_id": correlation_id,
                        }
                    ),
                    400,
                )

            start = time()
            event_name = str(event_value or "unknown")
            handled = dispatcher.dispatch(data)
            record_event(event_name, handled, time() - start)
            return (
                jsonify(
                    {
                        "status": "success",
                        "handled": handled,
                        "event": event_name,
                        "correlation_id": correlation_id,
                    }
                ),
                200,
            )
        except Exception as exc:  # Let global handlers record sanitized output
            record_error(event_value, getattr(exc, "code", "internal_error"))
            raise
        finally:
            clear_request_id()

    return app


if __name__ == "__main__":
    create_app().run(
        host=settings.server.host,
        port=settings.server.port,
        debug=settings.server.debug,
    )
