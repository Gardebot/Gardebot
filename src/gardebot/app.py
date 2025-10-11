"""Main Flask application for handling WAHA webhook events and providing an internal send_text helper."""

from __future__ import annotations

from flask import Flask, jsonify, request
from flask.wrappers import Response

from gardebot.common.logging_configuration import configure_logging, get_logger
from gardebot.dispatcher import EventDispatcher
from gardebot.error_handlers import register_error_handlers
from gardebot.gardebot import Gardebot
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

        handled = dispatcher.dispatch(data)
        return jsonify({"status": "success", "handled": handled}), 200

    return app


if __name__ == "__main__":
    create_app().run(
        host=settings.server.host,
        port=settings.server.port,
        debug=settings.server.debug,
    )
