"""Module to handle incoming messages and statuses from WAHA."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access
import json
import logging
from typing import Any, Dict, List

import requests  # type: ignore[import-untyped]

from gardebot.config import API_CONFIG

LOGGER = logging.getLogger(__name__)


def process_messages(data: Dict[str, Any]) -> None:
    """Process incoming messages from WAHA."""
    try:
        payload = data.get("payload")
        if payload is None:
            LOGGER.info("No payload to process with data %s.", data)
            return
        if not payload.get("fromMe"):
            body = payload.get("body")
            timestamp = payload.get("timestamp")
            from_number = payload.get("from")

            send_text(
                chat_id=from_number,
                message_text=f"Echoing : {body} sent at {timestamp}",
            )
            LOGGER.info(
                "Processed message from %s at %s: %s", from_number, timestamp, body
            )
        else:
            LOGGER.debug("Ignoring message sent from myself with data %s.", data)
    except Exception as exc:
        LOGGER.exception("Error in process_messages: %s", exc)


def process_statuses(data: Dict[str, Any]) -> None:
    """Process status updates from WAHA."""
    try:
        statuses = data.get("statuses")
        if statuses is None:
            LOGGER.debug("No statuses in payload.")
            return
        for status in statuses:
            status_id = status.get("id")
            status_type = status.get("status")
            recipient = status.get("recipient_id") or status.get("recipientId")
            LOGGER.info(
                "Message %s to %s status: %s", status_id, recipient, status_type
            )
    except Exception as exc:
        LOGGER.exception("Error in process_statuses: %s", exc)


def send_api_request(url: str, payload: Dict[str, Any]) -> requests.Response:
    """Send a generic API request to WAHA."""
    try:
        headers = {"Content-Type": "application/json"}
        LOGGER.debug("POST %s payload=%s", url, payload)
        response = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=API_CONFIG["timeout"],
        )
        LOGGER.debug("Response %s: %s", response.status_code, response.text)
        return response
    except Exception as exc:
        LOGGER.error("Error sending API request: %s", exc)
        response = requests.Response()
        response.status_code = 500
        response._content = json.dumps({"error": str(exc)}).encode("utf-8")
        return response


def _is_success(status: int) -> bool:
    return 200 <= status < 300


def send_poll(
    chat_id: str,
    poll_title: str,
    poll_options: List[str],
    multiple_answers: bool = False,
) -> None:
    """Send a poll using WAHA."""
    try:
        url = f"{API_CONFIG['base_url']}/api/sendPoll"
        payload = {
            "chatId": chat_id,
            "poll": {
                "name": poll_title,
                "options": poll_options,
                "multipleAnswers": multiple_answers,
            },
            "session": API_CONFIG["session"],
        }

        response = send_api_request(url, payload)

        if _is_success(response.status_code):
            LOGGER.info("Poll sent successfully to %s", chat_id)
        else:
            LOGGER.error(
                "Failed to send poll (%s): %s", response.status_code, response.text
            )
    except Exception as exc:
        LOGGER.exception("Error sending poll: %s", exc)


def send_text(chat_id: str, message_text: str) -> None:
    """Send a reply using WAHA."""
    try:
        url = f"{API_CONFIG['base_url']}/api/sendText"
        payload = {
            "session": API_CONFIG["session"],
            "chatId": chat_id,
            "text": message_text,
        }
        response = send_api_request(url, payload)
        if _is_success(response.status_code):
            LOGGER.info("Message sent successfully to %s", chat_id)
        else:
            LOGGER.error(
                "Failed to send message (%s): %s", response.status_code, response.text
            )
    except Exception as exc:
        LOGGER.exception("Error sending message: %s", exc)
