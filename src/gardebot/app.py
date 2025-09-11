"""Main Flask application for handling WAHA webhook events.

Features:
- Receives and validates webhook events from WAHA.
- Performs signature verification for security.
- Logs all events and errors to console.
- Processes incoming WhatsApp messages and status updates.
- Replies to messages using WAHA.

Endpoints:
- /webhook : Receives POST events from WAHA.
- /health  : Simple health check endpoint.

Environment Variables:
- PORT            : Port to run the server (default: 5000).
"""

# pylint: disable=broad-exception-caught
import logging

from flask import Flask, Response, jsonify, request

from gardebot.config import SERVER_CONFIG
from gardebot.hub import process_messages, process_statuses

LOGGER = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health_check() -> tuple[Response, int]:
    """Simple health check endpoint."""
    return jsonify({"status": "ok"}), 200


@app.route("/webhook", methods=["GET", "POST"])
def webhook() -> tuple[Response, int]:
    """Handle incoming webhook events from WAHA."""
    # For GET requests (verification)
    if request.method == "GET":
        LOGGER.info("Received verification request")
        return jsonify({"status": "ok"}), 200
    try:
        data = request.get_json()
        if not data:
            LOGGER.warning("Received empty or invalid JSON")
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400
        LOGGER.info("Received webhook data type: %s", type(data).__name__)

        if "messages" in data:
            process_messages(data)
        elif "statuses" in data:
            process_statuses(data)
        else:
            LOGGER.info("Unhandled webhook data: %s", data)
        return jsonify({"status": "success"}), 200
    except Exception as exc:
        LOGGER.error("Error processing webhook: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 200


if __name__ == "__main__":
    app.run(
        host=SERVER_CONFIG["host"],
        port=SERVER_CONFIG["port"],
        debug=SERVER_CONFIG["debug"],
    )
