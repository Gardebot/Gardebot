"""Module to handle incoming messages to/from WAHA."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytz  # type: ignore[import-untyped]

from gardebot.common.common import parse_iso_datetime
from gardebot.config import API_CONFIG, EM_NAME
from gardebot.datamanager import DataManager
from gardebot.request import WahaRequest

geneva_tz = pytz.timezone("Europe/Zurich")

LOGGER = logging.getLogger(__name__)


class MessageRequest(WahaRequest):
    """Handles message interactions with the WAHA API."""

    def __init__(self, base_url: str = API_CONFIG["base_url"]) -> None:
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
                LOGGER.info(
                    "Processed message from %s at %s: %s", from_number, timestamp, body
                )
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

    def send_vote_reminder(self) -> None:
        """Send a reminder message to vote."""
        reminders = self._get_vote_reminders()
        for reminder in reminders:
            poll_string = reminder["poll_string"]

            if reminder["all_voted"]:
                LOGGER.info("All sapeurs have voted for poll %s", poll_string)
                self.send_text(
                    to_number="41782611429",  # TODO: change to an admin number
                    message_text=f"Salut, Tous les sapeurs ont répondu au sondage {poll_string}.",
                )
                continue
            message_text = f"Bonjour, Merci à {reminder['mention_text']} de bien vouloir répondre au sondage"
            message_text += f" - {poll_string} - attaché à ce mesage :)"
            payload = {
                "session": self.session,
                "chatId": "41782611429",  # TODO: change to group chat
                "reply_to": reminder["poll_id"],
                "mentions": reminder["sapeur_ids"],
                "text": message_text,
            }
            try:
                response = self.send_post_request(
                    endpoint="/api/sendText", payload=payload
                )
                if self._is_success(response.status_code):
                    LOGGER.info(
                        "Reminder sent successfully to %s", "41782611429"
                    )  # TODO: change to group chat
                else:
                    LOGGER.error(
                        "Failed to send reminder (%s): %s",
                        response.status_code,
                        response.text,
                    )
            except Exception as exc:
                LOGGER.exception("Error sending reminder: %s", exc)

    def _get_vote_reminders(self) -> List[Dict[str, Any]]:
        """Prepare reminder data for polls and sapeurs who haven't voted."""
        data_manager = DataManager()
        vote_df = data_manager.load_dataframe("votes")
        poll_df = data_manager.load_dataframe("polls").set_index("poll_string")
        sapeur_df = data_manager.load_dataframe("sapeurs").set_index("name")

        reminders = []
        for poll_string in vote_df.columns:
            if not (
                poll_df.loc[poll_string, "on_duty"] is None
                and poll_df.loc[poll_string, "is_published"]
            ):
                LOGGER.info(
                    "Skipping reminder for poll %s as it is not active i.e. on_duty: %s and is_published: %s",
                    poll_string,
                    poll_df.loc[poll_string, "on_duty"],
                    poll_df.loc[poll_string, "is_published"],
                )
                continue

            poll_id = poll_df.loc[poll_string, "poll_uid"]
            timestamp = (
                self.get_message_by_id(message_id=poll_id)
                .get("_data")
                .get("Info")
                .get("Timestamp")
            )
            if parse_iso_datetime(timestamp) - datetime.now(tz=geneva_tz) < timedelta(
                hours=23
            ):
                LOGGER.debug(
                    "Skipping reminder for poll %s as it was sent less than 24 hours ago",
                    poll_string,
                )
                continue
            tmp_sapeur_name_to_send_reminder = vote_df[
                vote_df[poll_string].isnull()
            ].index.tolist()
            sapeur_name_to_send_reminder = [
                name for name in tmp_sapeur_name_to_send_reminder if name not in EM_NAME
            ]
            sapeur_id_to_send_reminder = [
                sapeur_df.loc[name, "id"] for name in sapeur_name_to_send_reminder
            ]
            sapeur_phone_to_send_reminder = [
                "@" + str(sapeur_df.loc[name, "phone"])[1:]
                for name in sapeur_name_to_send_reminder
            ]
            mention_text = ", ".join(sapeur_phone_to_send_reminder)

            reminders.append(
                {
                    "poll_string": poll_string,
                    "poll_id": poll_id,
                    "sapeur_ids": sapeur_id_to_send_reminder,
                    "mention_text": mention_text,
                    "all_voted": len(sapeur_name_to_send_reminder) == 0,
                }
            )
        return reminders

    def get_message_by_id(self, message_id: str) -> Any:
        """Get a message by its ID using WAHA."""
        try:
            chat_id = "41782611429"  # TODO: change to group chat
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
