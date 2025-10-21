"""MessagingAdapter: outbound messaging operations using WahaClient with injectable services."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pytz  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.config import EM_NAME, GROUP_ID_GARDE_ET_PIQUET
from gardebot.errors import ExternalServiceError
from gardebot.integrations.waha_client import WahaClient
from gardebot.models.domain import Event, Sapeur
from gardebot.repositories import SapeurRepository
from gardebot.services.events import EventService
from gardebot.services.votes import VoteService
from gardebot.settings import settings

LOGGER = get_logger(__name__)
GENEVA_TZ = pytz.timezone("Europe/Zurich")


class MessagingAdapter:
    """MessagingAdapter: outbound messaging operations using WahaClient with injectable services."""

    def __init__(
        self,
        waha_client: Optional[WahaClient] = None,
        event_service: Optional[EventService] = None,
        vote_service: Optional[VoteService] = None,
        sapeur_repository: Optional[SapeurRepository] = None,
    ) -> None:
        """Initialize with optional shared services and WahaClient."""
        self._client = waha_client or WahaClient(
            api_key=settings.api.api_key,
            base_url=settings.api.base_url,
            session=settings.api.session,
            timeout=settings.api.timeout_seconds,
            retries=settings.api.retry_attempts,
        )
        self._event_service = event_service or EventService()
        self._vote_service = vote_service or VoteService()
        self._sapeur_repo = sapeur_repository or SapeurRepository()
        self.endpoint = "/api/sendText"

    def send_text(self, to_number: str, text: str) -> Dict[str, Any]:
        """Send a text message to a WhatsApp number."""
        LOGGER.info("messaging.send_text", to=to_number, text_excerpt=text[:60])
        payload = {"session": self._client.session, "chatId": to_number, "text": text}
        return self._post_json(self.endpoint, payload)

    def send_event(
        self,
        to_number: str,
        name: str,
        description: str,
        start_time: int,
        end_time: int,
        location: str,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a calendar event to a chat."""
        LOGGER.debug("messaging.send_event", to=to_number, name=name, start_time=start_time, end_time=end_time)
        payload = {
            "chatId": to_number,
            "event": {
                "name": name,
                "description": description,
                "startTime": start_time,
                "endTime": end_time,
                "location": {"name": location},
            },
        }
        if reply_to:
            payload["reply_to"] = reply_to
        endpoint = f"/api/{self._client.session}/events"
        return self._post_json(endpoint, payload)

    def get_message(self, chat_id: str, message_id: str) -> Dict[str, Any]:
        """Fetch a message by ID."""
        endpoint = f"/api/{self._client.session}/chats/{chat_id}/messages/{message_id}"
        resp = self._client._http.request("GET", endpoint, raise_for_status=True)
        return self._client._extract_json_dict(resp)

    def _build_mentions_payload(
        self,
        to_number: str,
        sapeur_list: List[Sapeur],
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build payload with mentions for given sapeur names."""
        mentions = [sap.uid for sap in sapeur_list]
        text_mention = ", ".join(["@" + sap.phone[1:] for sap in sapeur_list])
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
        LOGGER.debug("http_post_json", endpoint=endpoint, payload=payload)
        resp = self._client._http.request("POST", endpoint, json_body=payload, raise_for_status=True)  # noqa: SLF001
        return self._client._extract_json_dict(resp)  # noqa: SLF001

    def _build_vote_reminder_payload(self, event: Event) -> Optional[Dict[str, Any]]:
        """Build payload for vote reminder message."""
        sapeur_list = [sap for sap in self._vote_service.list_non_responding(event=event) if sap.name not in EM_NAME]
        if len(sapeur_list) == 0:
            return None
        payload = self._build_mentions_payload(
            to_number=os.environ.get("ADMIN_NUMBER", ""),
            sapeur_list=sapeur_list,
            reply_to=event.poll_uid,
        )
        payload["text"] = f"Bonjour, merci à {payload['text']} de répondre au sondage - {event.poll_string} - associé :)"
        return payload

    def send_vote_reminder(self, event: Event) -> Dict[str, Any]:
        """Send reminder message; raises if no recipients or send fails."""
        payload = self._build_vote_reminder_payload(event=event)
        if payload is None:
            raise ExternalServiceError(
                "No recipients for reminder",
                detail={"poll_string": event.poll_string},
            )
        LOGGER.info("sending_vote_reminder", poll_string=event.poll_string, to=payload.get("chatId"))
        return self._post_json(self.endpoint, payload)

    def _send_group_convocation(
        self,
        to_number: str,
        event: Event,
        sapeur_list: List[Sapeur],
    ) -> Dict[str, Any]:
        """Send group convocation message with mentions."""
        payload = self._build_mentions_payload(to_number=to_number, sapeur_list=sapeur_list, reply_to=event.poll_uid)
        payload["text"] = f"Merci à {payload['text']} pour la garde: {event.poll_string}. Vous êtes convoqué.e.s."
        LOGGER.info("sending_group_convocation", poll_string=event.poll_string, to=to_number)
        return self._post_json(self.endpoint, payload)

    def _send_private_convocation(self, to_number: str, event: Event) -> Dict[str, Any]:
        """Send private convocation message for an on-duty sapeur."""
        event_description = f"Bonjour, vous êtes convoqué.e.s pour la garde : {event.poll_string}. Merci pour votre engagement."
        return self.send_event(
            to_number=to_number,
            name=event.title,
            description=event_description,
            location=event.location,
            start_time=int(event.start_date.timestamp()),
            end_time=int(event.end_date.timestamp()),
            reply_to=event.poll_uid,
        )

    def send_convocation(self, event: Event, sapeur_list: List[Sapeur]) -> Dict[str, Any]:
        """Send convocation messages (group and private) to on-duty sapeurs."""
        if not event.poll_uid:
            raise ExternalServiceError("Missing poll ID for convocation", detail={"poll_string": event.poll_string})
        results: Dict[str, Any] = {"group": None, "private": []}
        results["group"] = self._send_group_convocation(
            to_number=GROUP_ID_GARDE_ET_PIQUET,
            sapeur_list=sapeur_list,
            event=event,
        )
        for sap in sapeur_list:
            try:
                res = self._send_private_convocation(to_number=sap.phone, event=event)
                results["private"].append({"to": sap.phone, "result": res})
            except ExternalServiceError as exc:
                LOGGER.error(
                    "private_convocation_failed",
                    to=sap.phone,
                    poll_string=event.poll_string,
                    error=str(exc),
                )
                results["private"].append({"to": sap.phone, "error": str(exc)})
        LOGGER.info("convocation_complete", poll_string=event.poll_string, on_duty=[s.name for s in sapeur_list])
        return results
