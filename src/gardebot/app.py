"""Main Flask application for handling WAHA webhook events and providing an internal send_text helper."""

# pylint: disable=broad-exception-caught
from __future__ import annotations

import logging

from flask import Flask, Response, jsonify, request

from gardebot.config import API_CONFIG, SERVER_CONFIG
from gardebot.datamanager import DataManager
from gardebot.gardebot import Gardebot

LOGGER = logging.getLogger(__name__)

app = Flask(__name__)

WAHA_BASE_URL = str(API_CONFIG.get("base_url", "http://waha:3000"))
WAHA_SESSION = str(API_CONFIG.get("session", "default"))


@app.route("/health", methods=["GET"])
def health_check() -> tuple[Response, int]:
    """Simple health check endpoint."""
    return jsonify({"status": "ok"}), 200


@app.route("/webhook", methods=["GET", "POST"])
def webhook() -> tuple[Response, int]:
    """Handle incoming webhook events from WAHA (messages / statuses)."""
    gardebot = Gardebot()
    if request.method == "GET":
        LOGGER.info("Received verification/ping request on /webhook")
        return jsonify({"status": "ok"}), 200

    try:
        data = request.get_json(silent=True)
        if data is None:
            LOGGER.warning("Received empty or invalid JSON on /webhook")
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400

        LOGGER.debug("Raw webhook payload: %r", data)
        LOGGER.info("Webhook payload keys: %s", list(data.keys()))

        if "message" in data.get("event"):
            gardebot.process_messages(data)
        elif "poll.vote" in data.get("event"):
            gardebot.process_vote(data)
        elif "session.status" in data.get("event"):
            if "WORKING" in data.get("payload").get("status"):
                LOGGER.info("Session is now WORKING")
                data_manager = DataManager()
                df = gardebot.fetch_group_participants_table()
                data_manager.save_dataframe(df, "group_participants")
            else:
                LOGGER.info(
                    "Session status changed: %s", data.get("payload").get("status")
                )

        else:
            LOGGER.info("Unhandled webhook data shape: %s", data)

        return jsonify({"status": "success"}), 200
    except Exception as exc:
        LOGGER.exception("Error processing webhook: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


if __name__ == "__main__":
    app.run(
        host=SERVER_CONFIG["host"],
        port=SERVER_CONFIG["port"],
        debug=SERVER_CONFIG["debug"],
    )
