"""Module to handle incoming messages to/from WAHA."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Sequence

import pytz  # type: ignore[import-untyped]

from gardebot.config import EM_NAME, GROUP_ID_GARDE_ET_PIQUET
from gardebot.event import EventManager
from gardebot.request import WahaRequest
from gardebot.sapeur import SapeurManager
from gardebot.settings import settings
from gardebot.vote import VoteManager

geneva_tz = pytz.timezone("Europe/Zurich")

LOGGER = logging.getLogger(__name__)


class MessageRequest(WahaRequest):
    """Handles message interactions with the WAHA API."""

    def __init__(self, base_url: str = settings.api.base_url) -> None:
        """Initialize the MessageRequest instance."""
        super().__init__(base_url=base_url)

    def process_messages(self, data: Dict[str, Any]) -> None:
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

                self.send_text(
                    to_number=from_number,
                    message_text=f"Echoing, you sent : '{body}' at {timestamp}",
                )
                LOGGER.info("Processed message from %s at %s: %s", from_number, timestamp, body)
            else:
                LOGGER.debug("Ignoring message sent from myself with data %s.", data)
        except Exception as exc:
            LOGGER.exception("Error in process_messages: %s", exc)

    def send_text(self, to_number: str, message_text: str) -> None:
        """Send a reply using WAHA."""
        try:
            payload = {
                "session": self.session,
                "chatId": to_number,
                "text": message_text,
            }
            response = self.send_post_request(endpoint="/api/sendText", payload=payload)
            if self._is_success(response.status_code):
                LOGGER.info("Message sent successfully to %s", to_number)
            else:
                LOGGER.error(
                    "Failed to send message (%s): %s",
                    response.status_code,
                    response.text,
                )
        except Exception as exc:
            LOGGER.exception("Error sending message: %s", exc)

    def send_event_message(
        self,
        to_number: str,
        event_description: str,
        event_name: str,
        event_start_time: int,
        event_end_time: int,
        location: str,
        reply_to: Optional[str] = None,
    ) -> None:
        """Send an event message using WAHA."""
        try:
            endpoint = f"/api/{self.session}/events"
            payload = {
                "chatId": to_number,
                "reply_to": reply_to,
                "event": {
                    "name": event_name,
                    "description": event_description,
                    "startTime": event_start_time,
                    "endTime": event_end_time,
                    "location": {"name": location},
                },
            }
            response = self.send_post_request(endpoint=endpoint, payload=payload)
            if self._is_success(response.status_code):
                LOGGER.info("Event sent successfully to %s", to_number)
            else:
                LOGGER.error(
                    "Failed to send event (%s): %s",
                    response.status_code,
                    response.text,
                )
        except Exception as exc:
            LOGGER.exception("Error sending event: %s", exc)

    def _get_reminders_payload(self, poll_string: str) -> Dict[str, Any]:
        """Prepare reminder data for polls and sapeurs who haven't voted."""
        vote_manager = VoteManager()
        event_manager = EventManager()
        poll_id = event_manager.get_garde_by_pollstring(poll_string).get_poll_uid()

        sapeur_name_to_send_reminder = [
            name for name in vote_manager.get_non_responding_list(poll_string=poll_string) if name not in EM_NAME
        ]

        payload = self._get_payload_with_mention(
            to_number=os.environ.get("ADMIN_NUMBER", ""),  # TODO: change to group chat
            name_list=sapeur_name_to_send_reminder,
            reply_to=poll_id,
        )
        message_text = f"Bonjour, Merci à {payload['text']} de bien vouloir répondre au sondage"
        message_text += f" - {poll_string} - attaché à ce mesage :)"
        payload["text"] = message_text

        return payload

    def send_vote_reminder(self, poll_string: str) -> None:
        """Send a reminder message to vote."""
        payload = self._get_reminders_payload(poll_string=poll_string)

        if len(payload["mentions"]) == 0:
            LOGGER.info("No reminder to send for poll %s", poll_string)
            return
        try:
            response = self.send_post_request(endpoint="/api/sendText", payload=payload)
            if self._is_success(response.status_code):
                LOGGER.info(
                    "Reminder sent successfully to %s",
                    os.environ.get("ADMIN_NUMBER"),  # TODO: Chnage to number in payload
                )
            else:
                LOGGER.error(
                    "Failed to send reminder (%s): %s",
                    response.status_code,
                    response.text,
                )
        except Exception as exc:
            LOGGER.exception("Error sending reminder: %s", exc)

    def get_message_by_id(self, message_id: str) -> Any:
        """Get a message by its ID using WAHA."""
        try:
            chat_id = GROUP_ID_GARDE_ET_PIQUET
            endpoint = f"/api/{self.session}/chats/{chat_id}/messages/{message_id}?downloadMedia=true"
            response = self.send_get_request(endpoint=endpoint)
            if self._is_success(response.status_code):
                LOGGER.info("Message retrieved successfully for ID %s", message_id)
                return response.json()
            LOGGER.error(
                "Failed to retrieve message (%s): %s",
                response.status_code,
                response.text,
            )
            return {}
        except Exception as exc:
            LOGGER.exception("Error retrieving message: %s", exc)
            return {}

    def _get_payload_with_mention(self, to_number: str, name_list: List[str], reply_to: Optional[str]) -> Dict[str, Sequence[str]]:
        """Prepare payload for sending message with mentions."""
        sapeur_manager = SapeurManager()
        sapeur_list = [sapeur_manager.get_sapeur_by_name(name) for name in name_list]

        mentions = [sap.get_uid() for sap in sapeur_list]
        text_mention = ", ".join(["@" + sap.get_phone()[1:] for sap in sapeur_list])
        payload = {
            "session": self.session,
            "chatId": to_number,
            "text": text_mention,
            "mentions": mentions,
        }
        if reply_to:
            payload["reply_to"] = reply_to
        return payload

    def _send_group_convocation(self, to_number: str, poll_string: str, on_duty_name: List[str], poll_id: str) -> None:
        """Send a group convocation message using WAHA."""
        payload = self._get_payload_with_mention(to_number=to_number, name_list=on_duty_name, reply_to=poll_id)
        group_text = f"Merci à {payload['text']} pour la garde: {poll_string}. Vous êtes convoqué.e.s, merci pour votre engagement :)"
        payload["text"] = group_text
        try:
            response = self.send_post_request(endpoint="/api/sendText", payload=payload)
            if self._is_success(response.status_code):
                LOGGER.info("Convocation sent successfully to %s", to_number)
            else:
                LOGGER.error(
                    "Failed to send convocation (%s): %s",
                    response.status_code,
                    response.text,
                )
        except Exception as exc:
            LOGGER.exception("Error sending convocation: %s", exc)

    def _send_private_convocation(self, to_number: str, poll_string: str) -> None:
        """Send a private convocation message using an event message."""
        event_manager = EventManager()
        garde = event_manager.get_garde_by_pollstring(poll_string)
        event_description = f"Bonjour, Vous êtes convoqué.e.s pour la garde : {poll_string} et merci pour votre engagement :)"
        try:
            self.send_event_message(
                to_number=to_number,
                event_description=event_description,
                event_name=garde.get_title(),
                event_start_time=int(geneva_tz.localize(garde.get_start_date()).timestamp()),
                event_end_time=int(geneva_tz.localize(garde.get_end_date()).timestamp()),
                location=garde.get_location(),
                reply_to=garde.get_poll_uid(),
            )
        except Exception as exc:
            LOGGER.exception("Error sending private convocation: %s", exc)

    def send_convocation(self, poll_string: str, on_duty_name: List[str]) -> None:
        """Send a convocation message in private and in group using WAHA."""
        sapeur_manager = SapeurManager()
        event_manager = EventManager()
        poll_id = event_manager.get_garde_by_pollstring(poll_string).get_poll_uid()
        if not poll_id:
            LOGGER.error("No poll ID found for poll string %s", poll_string)
            return None
        sapeur_list = [sapeur_manager.get_sapeur_by_name(name) for name in on_duty_name]

        self._send_group_convocation(
            to_number=os.environ.get("ADMIN_NUMBER", ""),  # TODO: change to group chat
            poll_string=poll_string,
            on_duty_name=on_duty_name,
            poll_id=poll_id,
        )
        for sapeur in sapeur_list:
            self._send_private_convocation(to_number=sapeur.get_phone(), poll_string=poll_string)

        LOGGER.info("Convocation send for pollstring %s to %s", poll_string, on_duty_name)
        return None
