"""Main Flask application for handling WAHA webhook events and providing an internal send_text helper."""

from __future__ import annotations

from flask import Flask, jsonify, request
from requests import Response  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import configure_logging, get_logger
from gardebot.gardebot import Gardebot
from gardebot.settings import settings

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

    @app.route("/health", methods=["GET"])
    def health() -> tuple[Response, int]:
        """Simple health check endpoint."""
        return jsonify({"status": "ok"}), 200

    @app.route("/webhook", methods=["GET", "POST"])
    def webhook() -> tuple[Response, int]:
        """Handle incoming webhook events from WAHA (messages / statuses)."""
        bot = Gardebot()
        if request.method == "GET":
            LOGGER.info("webhook_ping")
            return jsonify({"status": "ok"}), 200

        data = request.get_json(silent=True)
        if data is None:
            LOGGER.warning("invalid_json")
            return jsonify({"status": "error", "message": "invalid_json"}), 400

        event = data.get("event")
        if event is None:
            LOGGER.error("missing_event")
            return jsonify({"status": "error", "message": "missing_event"}), 400
        LOGGER.debug("incoming_event", extra={"event": event})
        try:
            if "message" in event:
                bot.process_messages(data)
            elif "poll.vote" in event:
                bot.process_vote(data)
            elif "session.status" in event:
                payload = data.get("payload") or {}
                if "WORKING" in payload.get("status", ""):
                    bot.initialize()
            elif "group.v2.participants" in event:
                bot.update_sapeurs()
            else:
                LOGGER.info("unhandled_event", extra={"event": event})
            return jsonify({"status": "success"}), 200
        except Exception as exc:
            LOGGER.exception("webhook_error", error=str(exc))
            return jsonify({"status": "error", "message": "internal_error"}), 500

    return app


if __name__ == "__main__":
    create_app().run(
        host=settings.server.host,
        port=settings.server.port,
        debug=settings.server.debug,
    )
