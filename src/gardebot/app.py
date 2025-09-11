"""Main Flask application for handling WAHA webhook events and simple outbound sends."""

# pylint: disable=broad-exception-caught
import logging
from typing import Any

import requests  # type: ignore[import-untyped]
from flask import Flask, Response, jsonify, request

from gardebot.config import API_CONFIG, SERVER_CONFIG
from gardebot.hub import process_messages, process_statuses

LOGGER = logging.getLogger(__name__)

app = Flask(__name__)

WAHA_BASE_URL = API_CONFIG.get("base_url", "http://waha:3000")
WAHA_SESSION = str(API_CONFIG.get("session", "default"))


def send_text(chat_id: str, text: str, session: str = WAHA_SESSION) -> dict[str, Any]:
    """Send a text message via WAHA.

    chat_id: WhatsApp ID; use full international number without '+' then append '@c.us'
             Example: '12345550000@c.us'
    """
    payload = {
        "session": session,
        "chatId": chat_id,
        "text": text,
    }

    url = f"{WAHA_BASE_URL}/api/sendText"
    try:
        LOGGER.info("Sending text via WAHA: %s -> %s", chat_id, text)
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return {"ok": True, "response": resp.json()}
    except Exception as exc:
        LOGGER.error("Failed to send text: %s", exc)
        return {"ok": False, "error": str(exc)}


@app.route("/health", methods=["GET"])
def health_check() -> tuple[Response, int]:
    """Simple health check endpoint."""
    return jsonify({"status": "ok"}), 200


@app.route("/webhook", methods=["GET", "POST"])
def webhook() -> tuple[Response, int]:
    """Handle incoming webhook events from WAHA."""
    if request.method == "GET":
        LOGGER.info("Received verification request")
        return jsonify({"status": "ok"}), 200

    try:
        data = request.get_json(silent=True)
        if not data:
            LOGGER.warning("Received empty or invalid JSON")
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400

        LOGGER.info("Webhook payload keys: %s", list(data.keys()))

        if "messages" in data:
            process_messages(data)
        elif "statuses" in data:
            process_statuses(data)
        else:
            LOGGER.info("Unhandled webhook data: %s", data)

        return jsonify({"status": "success"}), 200
    except Exception as exc:
        LOGGER.error("Error processing webhook: %s", exc)
        # Still return 200 so WAHA doesn’t keep retrying endlessly during early development
        return jsonify({"status": "error", "message": str(exc)}), 200


@app.route("/send", methods=["POST"])
def send_route() -> tuple[Response, int]:
    """Simple endpoint to trigger an outbound message.

    JSON body:
      {
        "chatId": "12345550000@c.us",
        "text": "Hello!",
        "session": "optional-session-name"
      }
    """
    body = request.get_json()
    chat_id = body.get("chatId")
    text = body.get("text")
    session = body.get("session")

    if not chat_id or not text:
        return jsonify({"error": "chatId and text required"}), 400

    result = send_text(chat_id, text, session=session)
    status = 200 if result.get("ok") else 500
    return jsonify(result), status


if __name__ == "__main__":
    app.run(
        host=SERVER_CONFIG["host"],
        port=SERVER_CONFIG["port"],
        debug=SERVER_CONFIG["debug"],
    )
