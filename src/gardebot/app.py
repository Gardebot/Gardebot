"""Main Flask application for handling WAHA webhook events and providing an internal send_text helper."""

from __future__ import annotations

from time import time
from typing import Dict

from flask import Flask, jsonify, request
from flask.wrappers import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from gardebot.common.logging_configuration import configure_logging, get_logger
from gardebot.dispatcher import EventDispatcher
from gardebot.error_handlers import register_error_handlers
from gardebot.gardebot import Gardebot
from gardebot.metrics import record_error, record_event
from gardebot.settings import settings
from gardebot.validation import MessageValidationError, basic_event_presence_check, validate_message_event

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
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    @app.route("/webhook", methods=["GET", "POST"])
    def webhook() -> tuple[Response, int]:
        """Handle incoming webhook events from WAHA (messages / statuses)."""
        if request.method == "GET":
            LOGGER.info("webhook_ping")
            return jsonify({"status": "ok"}), 200

        data = request.get_json(silent=True)
        if data is None:
            LOGGER.warning("invalid_json")
            return jsonify({"status": "error", "message": "invalid_json"}), 400

        event_value = data.get("event", "")
        if isinstance(event_value, str) and event_value == "message":
            # Perform message-specific validation
            try:
                _envelope = validate_message_event(data)
                # For now we still pass the original dict to dispatcher.
            except MessageValidationError as exc:
                LOGGER.warning("invalid_message_payload", detail=str(exc))
                return jsonify({"status": "error", "message": "invalid_message_payload"}), 422
        elif not basic_event_presence_check(data):
            LOGGER.warning("invalid_non_message_event_shape")
            return jsonify({"status": "error", "message": "invalid_event"}), 400

        start = time()
        event_name = str(data.get("event", "unknown"))
        try:
            handled = dispatcher.dispatch(data)
            record_event(event_name, handled, time() - start)
            return jsonify({"status": "success", "handled": handled}), 200
        except Exception as exc:
            record_error(event_name, getattr(exc, "code", "internal_error"))
            raise exc

    return app


if __name__ == "__main__":
    create_app().run(
        host=settings.server.host,
        port=settings.server.port,
        debug=settings.server.debug,
    )
