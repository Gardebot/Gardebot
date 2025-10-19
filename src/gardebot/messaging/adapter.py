"""MessagingAdapter: high-level outbound messaging operations using WahaClient (composition over inheritance).

Responsibilities:
- Build WAHA payloads (text, events, mentions, convocations, reminders)
- Invoke WahaClient / underlying HttpClient
- Raise ExternalServiceError for any non-successful network interaction
- Remain stateless beyond holding references (pure transformation + delegation)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import pytz  # type: ignore[import-untyped]

from gardebot.config import EM_NAME, GROUP_ID_GARDE_ET_PIQUET
from gardebot.errors import ExternalServiceError
from gardebot.event import EventManager
from gardebot.integrations.waha_client import WahaClient
from gardebot.sapeur import SapeurManager
from gardebot.settings import settings
from gardebot.vote import VoteManager

LOGGER = logging.getLogger(__name__)
GENEVA_TZ = pytz.timezone("Europe/Zurich")


class MessagingAdapter:
    """Adapter encapsulating outbound messaging logic via WahaClient."""

    def __init__(self, waha_client: Optional[WahaClient] = None) -> None:
        """Initialize the MessagingAdapter with a WahaClient instance."""
        self._client = waha_client or WahaClient(
            api_key=settings.api.api_key,
            base_url=settings.api.base_url,
            session=settings.api.session,
            timeout=settings.api.timeout_seconds,
            retries=settings.api.retry_attempts,
        )

    # ------------------------------------------------------------------ #
    # Basic Sends
    # ------------------------------------------------------------------ #
    def send_text(self, to_number: str, message_text: str) -> Dict[str, Any]:
        """Send a simple text message. Raises ExternalServiceError on failure."""
        LOGGER.debug("messaging.send_text", extra={"to": to_number, "text_excerpt": message_text[:60]})
        return self._client.send_text(to_number, message_text)

    def send_event_message(
        self,
        to_number: str,
        event_description: str,
        event_name: str,
        event_start_time: int,
        event_end_time: int,
        location: str,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an event message."""
        LOGGER.debug(
            "messaging.send_event",
            extra={
                "to": to_number,
                "event_name": event_name,
                "start": event_start_time,
                "end": event_end_time,
                "reply_to": reply_to,
            },
        )
        return self._client.send_event(
            to_number=to_number,
            name=event_name,
            description=event_description,
            start_time=event_start_time,
            end_time=event_end_time,
            location=location,
            reply_to=reply_to,
        )

    def get_message_by_id(self, message_id: str, download_media: bool = True) -> Dict[str, Any]:
        """Retrieve a message by ID from the default group chat."""
        chat_id = GROUP_ID_GARDE_ET_PIQUET
        query = "?downloadMedia=true" if download_media else ""
        endpoint = f"/api/{self._client.session}/chats/{chat_id}/messages/{message_id}{query}"
        resp = self._client._http.request("GET", endpoint, raise_for_status=True)  # noqa: SLF001
        return self._client._extract_json(resp)  # noqa: SLF001

    # ------------------------------------------------------------------ #
    # Mention Payload Helpers
    # ------------------------------------------------------------------ #
    def _build_mentions_payload(
        self,
        to_number: str,
        name_list: List[str],
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create WAHA payload with mentions from sapeur names."""
        sapeur_manager = SapeurManager()
        sapeur_list = [sapeur_manager.get_sapeur_by_name(name) for name in name_list]
        mentions = [sap.get_uid() for sap in sapeur_list]
        text_mention = ", ".join(["@" + sap.get_phone()[1:] for sap in sapeur_list])
        payload: Dict[str, Any] = {
            "session": self._client.session,
            "chatId": to_number,
            "text": text_mention,
            "mentions": mentions,
        }
        if reply_to:
            payload["reply_to"] = reply_to
        return payload

    def _post_json(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generic POST helper returning parsed JSON or raising ExternalServiceError."""
        resp = self._client._http.request("POST", endpoint, json_body=payload, raise_for_status=True)  # noqa: SLF001
        return self._client._extract_json(resp)  # noqa: SLF001

    # ------------------------------------------------------------------ #
    # Reminders
    # ------------------------------------------------------------------ #
    def build_vote_reminder_payload(self, poll_string: str) -> Optional[Dict[str, Any]]:
        """Build the reminder payload (returns None if no recipients)."""
        vote_manager = VoteManager()
        event_manager = EventManager()
        poll_id = event_manager.get_garde_by_pollstring(poll_string).get_poll_uid()

        sapeur_name_to_send_reminder = [
            name for name in vote_manager.get_non_responding_list(poll_string=poll_string) if name not in EM_NAME
        ]
        if not sapeur_name_to_send_reminder:
            return None

        payload = self._build_mentions_payload(
            to_number=os.environ.get("ADMIN_NUMBER", ""),
            name_list=sapeur_name_to_send_reminder,
            reply_to=poll_id,
        )
        message_text = f"Bonjour, Merci à {payload['text']} de bien vouloir répondre au sondage - {poll_string} - attaché à ce message :)"
        payload["text"] = message_text
        return payload

    def send_vote_reminder(self, poll_string: str) -> Dict[str, Any]:
        """Send reminder message; raises if no recipients or send fails."""
        payload = self.build_vote_reminder_payload(poll_string=poll_string)
        if payload is None:
            raise ExternalServiceError(
                "No recipients for reminder",
                detail={"poll_string": poll_string},
            )
        LOGGER.info("sending_vote_reminder", extra={"poll_string": poll_string, "to": payload.get("chatId")})
        return self._post_json("/api/sendText", payload)

    # ------------------------------------------------------------------ #
    # Convocations
    # ------------------------------------------------------------------ #
    def _send_group_convocation(
        self,
        to_number: str,
        poll_string: str,
        on_duty_name: List[str],
        poll_id: str,
    ) -> Dict[str, Any]:
        payload = self._build_mentions_payload(to_number=to_number, name_list=on_duty_name, reply_to=poll_id)
        payload["text"] = f"Merci à {payload['text']} pour la garde: {poll_string}. Vous êtes convoqué.e.s, merci pour votre engagement :)"
        LOGGER.info("sending_group_convocation", extra={"poll_string": poll_string, "to": to_number})
        return self._post_json("/api/sendText", payload)

    def _send_private_convocation(self, to_number: str, poll_string: str) -> Dict[str, Any]:
        event_manager = EventManager()
        garde = event_manager.get_garde_by_pollstring(poll_string)
        event_description = f"Bonjour, Vous êtes convoqué.e.s pour la garde : {poll_string} et merci pour votre engagement :)"
        LOGGER.debug("sending_private_convocation", extra={"poll_string": poll_string, "to": to_number})
        return self.send_event_message(
            to_number=to_number,
            event_description=event_description,
            event_name=garde.get_title(),
            event_start_time=int(GENEVA_TZ.localize(garde.get_start_date()).timestamp()),
            event_end_time=int(GENEVA_TZ.localize(garde.get_end_date()).timestamp()),
            location=garde.get_location(),
            reply_to=garde.get_poll_uid(),
        )

    def send_convocation(self, poll_string: str, on_duty_name: List[str]) -> Dict[str, Any]:
        """Send convocation (group + private). Returns summary of results."""
        event_manager = EventManager()
        garde = event_manager.get_garde_by_pollstring(poll_string)
        poll_id = garde.get_poll_uid()
        if not poll_id:
            raise ExternalServiceError("Missing poll ID for convocation", detail={"poll_string": poll_string})

        results: Dict[str, Any] = {"group": None, "private": []}
        group_chat = os.environ.get("ADMIN_NUMBER", "")  # TODO: Replace with group chat ID
        results["group"] = self._send_group_convocation(
            to_number=group_chat,
            poll_string=poll_string,
            on_duty_name=on_duty_name,
            poll_id=poll_id,
        )

        sapeur_manager = SapeurManager()
        sapeur_list = [sapeur_manager.get_sapeur_by_name(name) for name in on_duty_name]
        for sapeur in sapeur_list:
            try:
                res = self._send_private_convocation(to_number=sapeur.get_phone(), poll_string=poll_string)
                results["private"].append({"to": sapeur.get_phone(), "result": res})
            except ExternalServiceError as exc:
                LOGGER.error(
                    "private_convocation_failed",
                    extra={"to": sapeur.get_phone(), "poll_string": poll_string, "error": str(exc)},
                )
                results["private"].append({"to": sapeur.get_phone(), "error": str(exc)})

        LOGGER.info(
            "convocation_complete",
            extra={"poll_string": poll_string, "on_duty": on_duty_name},
        )
        return results
