"""Module to handle incoming messages and statuses from WAHA."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import json
import logging
from typing import Any, Dict, List, Optional

import requests  # type: ignore[import-untyped]

from gardebot.config import API_CONFIG, GROUP_ID_GARDE_ET_PIQUET

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
                message_text=f"Echoing, you sent : '{body}' at {timestamp}",
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


def send_post_request(url: str, payload: Dict[str, Any]) -> requests.Response:
    """Send a generic API POST request to WAHA."""
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": API_CONFIG["api_key"],
        }
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
        return _sent_error_response(exc)


def send_get_request(
    url: str,
    params: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    """Send a generic API GET request to WAHA."""
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": API_CONFIG["api_key"],
        }
        LOGGER.debug("GET %s", url)
        response = requests.get(
            url,
            headers=headers,
            timeout=API_CONFIG["timeout"],
            params=params,
        )
        LOGGER.debug("Response %s: %s", response.status_code, response.text)
        return response
    except Exception as exc:
        LOGGER.error("Error sending API request: %s", exc)
        return _sent_error_response(exc)


def _is_success(status: int) -> bool:
    return 200 <= status < 300


def _sent_error_response(exc: Exception) -> requests.Response:
    response = requests.Response()
    response.status_code = 500
    response._content = json.dumps({"error": str(exc)}).encode("utf-8")
    return response


def send_poll(
    chat_id: str,
    poll_title: str,
    poll_options: List[str],
    multiple_answers: bool = False,
    base_url: str = API_CONFIG["base_url"],
) -> None:
    """Send a poll using WAHA."""
    try:
        url = f"{base_url}/api/sendPoll"
        payload = {
            "chatId": chat_id,
            "poll": {
                "name": poll_title,
                "options": poll_options,
                "multipleAnswers": multiple_answers,
            },
            "session": API_CONFIG["session"],
        }
        response = send_post_request(url, payload)
        if _is_success(response.status_code):
            LOGGER.info("Poll sent successfully to %s", chat_id)
        else:
            LOGGER.error(
                "Failed to send poll (%s): %s", response.status_code, response.text
            )
    except Exception as exc:
        LOGGER.exception("Error sending poll: %s", exc)


def send_text(
    chat_id: str, message_text: str, base_url: str = API_CONFIG["base_url"]
) -> None:
    """Send a reply using WAHA."""
    try:
        url = f"{base_url}/api/sendText"
        payload = {
            "session": API_CONFIG["session"],
            "chatId": chat_id,
            "text": message_text,
        }
        response = send_post_request(url, payload)
        if _is_success(response.status_code):
            LOGGER.info("Message sent successfully to %s", chat_id)
        else:
            LOGGER.error(
                "Failed to send message (%s): %s", response.status_code, response.text
            )
    except Exception as exc:
        LOGGER.exception("Error sending message: %s", exc)


def get_group_participants(
    base_url: str = API_CONFIG["base_url"],
    session: str = API_CONFIG["session"],
    group_id: str = GROUP_ID_GARDE_ET_PIQUET,
) -> Optional[List[Dict[str, Any]]]:
    """Fetch participants of a specific group from the WAHA API.

    Args:
        base_url: Base URL of the WAHA API
        session: Session identifier
        group_id: Unique identifier of the group

    Returns:
        Dictionary of participant information
    """
    url = f"{base_url}/api/{session}/groups/{group_id}/participants"
    try:
        response = send_get_request(url=url)
        if _is_success(response.status_code):
            LOGGER.info("Participants fetched successfully for group %s", group_id)
            participants: List[Dict[str, Any]] = response.json()
            return participants
        LOGGER.error(
            "Failed to fetch participants for groupId %s (%s): %s",
            group_id,
            response.status_code,
            response.text,
        )
        return None
    except Exception as exc:
        LOGGER.exception("Error fetching participants: %s", exc)
        return None


def get_groups(
    base_url: str = API_CONFIG["base_url"],
    session: str = API_CONFIG["session"],
    limit: int = 10,
    offset: int = 0,
    sort_by: str = "subject",
    sort_order: str = "desc",
) -> Optional[Dict[str, Any]]:
    """Get groups from the WAHA API with pagination and sorting.

    Args:
        base_url: Base URL of the WAHA API
        session: Session identifier
        limit: Maximum number of groups to return
        offset: Number of groups to skip
        sort_by: Field to sort by (e.g., "subject", "creation")
        sort_order: Sort order ("asc" or "desc")

    Returns:
        Dictionary of group information
    """
    url = f"{base_url}/api/{session}/groups"
    params = {
        "limit": limit,
        "offset": offset,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    try:
        response = send_get_request(url=url, params=params)
        if _is_success(response.status_code):
            LOGGER.info("Groups fetched successfully")
            groups: Dict[str, Any] = response.json()
            return groups
        LOGGER.error(
            "Failed to fetch groups (%s): %s", response.status_code, response.text
        )
        return None
    except Exception as exc:
        LOGGER.exception("Error fetching groups: %s", exc)
        return None


def get_contact_info(
    contact_id: str,
    base_url: str = API_CONFIG["base_url"],
    session: str = API_CONFIG["session"],
) -> Optional[Dict[str, Any]]:
    """Fetch contact information from the WAHA API.

    Args:
        contact_id: Unique identifier of the contact (e.g., phone number with country code)
        base_url: Base URL of the WAHA API
        session: Session identifier
    Returns:
        Dictionary of contact information
    """
    url = f"{base_url}/api/contacts?contactId={contact_id}&session={session}"
    try:
        response = send_get_request(url=url)
        if _is_success(response.status_code):
            LOGGER.info("Contact info fetched successfully for contact %s", contact_id)
            contact_info: Dict[str, Any] = response.json()
            return contact_info
        LOGGER.error(
            "Failed to fetch contact info for contactId %s (%s): %s",
            contact_id,
            response.status_code,
            response.text,
        )
        return None
    except Exception as exc:
        LOGGER.exception("Error fetching contact info: %s", exc)
        return None
