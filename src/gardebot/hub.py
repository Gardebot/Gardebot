"""Module to handle incoming messages and statuses from WAHA."""

# pylint: disable=broad-exception-caught
import json
import logging
from typing import Any, Dict, List

import requests  # type: ignore[import-untyped]

from gardebot.config import API_CONFIG

LOGGER = logging.getLogger(__name__)


def process_messages(data: Dict[str, Any]) -> None:
    """Process incoming messages from WAHA."""
    try:
        messages = data.get("messages", [])
        for message in messages:
            message_type = message.get("type")
            from_number = message.get("from")
            if message_type == "text":
                text_content = message.get("text", {}).get("body", "")
                LOGGER.info("Received text from %s : %s", from_number, text_content)
                send_reply(from_number, f"Echoing: {text_content}")
            elif message_type == "image":
                LOGGER.info("Received image from %s", from_number)
                # Handle image processing here
            elif message_type == "document":
                LOGGER.info("Received document from %s ", from_number)
                # Handle document processing here
            elif message_type == "audio":
                LOGGER.info("Received audio from %s", from_number)
                # Handle audio processing here
            elif message_type == "video":
                LOGGER.info("Received video from %s", from_number)
                # Handle video processing here
            else:
                LOGGER.info(
                    "Received unsupported message type %s with data %s",
                    message_type,
                    data,
                )
    except Exception as exc:
        LOGGER.error("Error in process_messages: %s", exc)


def process_statuses(data: Dict[str, Any]) -> None:
    """Process status updates from WAHA."""
    try:
        statuses = data.get("statuses", [])
        for status in statuses:
            status_id = status.get("id")
            status_type = status.get("status")
            recipient = status.get("recipient_id")
            LOGGER.info(
                "Message %s to %s status: %s", status_id, recipient, status_type
            )
    except Exception as exc:
        LOGGER.error("Error in process_statuses: %s", exc)


def send_api_request(url: str, payload: Dict[str, Any]) -> requests.Response:
    """Send a generic API request to WAHA."""
    try:
        headers = {
            "Content-Type": "application/json",
        }

        response = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=API_CONFIG["timeout"],
        )
        return response
    except Exception as exc:
        LOGGER.error("Error sending API request: %s", exc)
        return None


def send_poll(
    to_number: str, poll_title: str, poll_options: List[str], poll_count: int
) -> None:
    """Send a poll using WAHA."""
    try:
        url = f"{API_CONFIG['base_url']}/messages/poll"
        payload = {
            "to": to_number,
            "options": poll_options,
            "title": poll_title,
            "count": poll_count,
        }

        response = send_api_request(url, payload)

        if response.status_code == 200:
            LOGGER.info("Poll sent successfully to %s", to_number)
        else:
            LOGGER.error("Failed to send poll: %s", response.text)
    except Exception as exc:
        LOGGER.error("Error sending poll: %s", exc)


def send_reply(to_number: str, message_text: str) -> None:
    """Send a reply using WAHA."""
    try:
        url = f"{API_CONFIG['base_url']}/messages/text"

        payload = {"to": to_number, "body": message_text}
        response = send_api_request(url, payload)
        if response.status_code == 200:
            LOGGER.info("Message sent successfully to %s", to_number)
        else:
            LOGGER.error("Failed to send message: %s", response.text)
    except Exception as exc:
        LOGGER.error("Error sending message: %s", exc)
