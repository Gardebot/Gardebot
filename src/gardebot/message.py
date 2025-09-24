"""Module to handle incoming messages to/from WAHA."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import pytz  # type: ignore[import-untyped]

from gardebot.common.common import parse_iso_datetime
from gardebot.config import (
    API_CONFIG,
    EM_NAME,
    GROUP_ID_GARDE_ET_PIQUET,
    MAX_NB_REMINDER,
)
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

    def test_is_published(self, poll_string: str) -> bool:
        """Test if the poll is published."""
        data_manager = DataManager()
        poll_df = data_manager.load_dataframe("polls").set_index("poll_string")
        if poll_df.loc[poll_string, "is_published"]:
            return True
        return False

    def test_assigned(self, poll_string: str) -> bool:
        """Test if the poll is on duty."""
        data_manager = DataManager()
        on_duty_df = data_manager.load_dataframe("on_duty")
        on_duty_list = on_duty_df[~on_duty_df[poll_string].isna()].index.tolist()

        if len(on_duty_list) > 0:
            return True
        return False

    def test_nb_reminder(self, poll_string: str) -> bool:
        """Test if the poll have reached the maximum number of reminders."""
        data_manager = DataManager()
        poll_df = data_manager.load_dataframe("polls").set_index("poll_string")
        if poll_df.loc[poll_string, "nb_reminder"] >= MAX_NB_REMINDER:
            return True
        return False

    def test_elapsed_time(
        self, poll_id: str, poll_string: str, minimum_elapsed_hours: int = 23
    ) -> bool:
        """Test if the poll was sent more than minimum_elapsed_hours ago."""
        timestamp = (
            self.get_message_by_id(message_id=poll_id)
            .get("_data")
            .get("Info")
            .get("Timestamp")
        )
        if parse_iso_datetime(timestamp) - datetime.now(tz=geneva_tz) < timedelta(
            hours=minimum_elapsed_hours
        ):
            LOGGER.debug(
                "Skipping reminder for poll %s as it was sent less than 24 hours ago",
                poll_string,
            )
            return True
        return False

    def test_all_voted(self, poll_string: str) -> bool:
        """Test if all sapeurs have voted."""
        data_manager = DataManager()
        vote_df = data_manager.load_dataframe("votes")
        tmp_sapeur_name_who_answered = vote_df[
            vote_df[poll_string].isnull()
        ].index.tolist()
        sapeur_name_who_answered = [
            name for name in tmp_sapeur_name_who_answered if name not in EM_NAME
        ]

        if len(sapeur_name_who_answered) == 0:
            LOGGER.info("All sapeurs have voted for poll %s", poll_string)
            self.send_text(
                to_number=os.environ.get("ADMIN_NUMBER", ""),
                message_text=f"Salut, Tous les sapeurs ont répondu au sondage {poll_string}.",
            )
            return True
        return False

    def test_has_to_be_reminded(self, poll_string: str, poll_id: str) -> bool:
        """Test if the poll has to be reminded."""
        if not self.test_is_published(poll_string):
            LOGGER.info(
                "Skipping reminder for poll %s as it is not published yet", poll_string
            )
            return False
        if self.test_assigned(poll_string):
            LOGGER.info(
                "Skipping reminder for poll %s as it is already assigned", poll_string
            )
            return False
        if self.test_nb_reminder(poll_string):
            LOGGER.info(
                "Skipping reminder for poll %s as it reached max number of reminders",
                poll_string,
            )
            return False
        if self.test_elapsed_time(
            poll_id=poll_id,
            poll_string=poll_string,
        ):  # pyright: ignore[reportCallIssue]
            LOGGER.info(
                "Skipping reminder for poll %s as it was sent less than 24 hours ago",
                poll_string,
            )
            return False
        if self.test_all_voted(poll_string):
            LOGGER.info(
                "Skipping reminder for poll %s as all sapeurs have voted",
                poll_string,
            )
            return False
        return True

    def _get_vote_reminders(self) -> List[Dict[str, Any]]:
        """Prepare reminder data for polls and sapeurs who haven't voted."""
        data_manager = DataManager()
        vote_df = data_manager.load_dataframe("votes")
        poll_df = data_manager.load_dataframe("polls").set_index("poll_string")
        reminder_payload = []
        for poll_string in vote_df.columns:
            poll_id = str(poll_df.loc[poll_string, "poll_uid"])

            if not self.test_has_to_be_reminded(poll_string, poll_id):
                continue

            tmp_sapeur_name_to_send_reminder = vote_df[
                vote_df[poll_string].isnull()
            ].index.tolist()
            sapeur_name_to_send_reminder = [
                name for name in tmp_sapeur_name_to_send_reminder if name not in EM_NAME
            ]

            payload = self._get_payload_with_mention(
                to_number=os.environ.get(
                    "ADMIN_NUMBER", ""
                ),  # TODO: change to group chat
                name_list=sapeur_name_to_send_reminder,
                reply_to=poll_id,
            )
            message_text = f"Bonjour, Merci à {payload['mentions']} de bien vouloir répondre au sondage"
            message_text += f" - {poll_string} - attaché à ce mesage :)"
            payload["text"] = message_text
            reminder_payload.append(payload)
            poll_df.at[
                poll_string, "nb_reminder"
            ] += 1  # pyright: ignore[reportOperatorIssue]

        return reminder_payload

    def send_vote_reminder(self) -> None:
        """Send a reminder message to vote."""
        reminder_payload = self._get_vote_reminders()
        for payload in reminder_payload:

            try:
                response = self.send_post_request(
                    endpoint="/api/sendText", payload=payload
                )
                if self._is_success(response.status_code):
                    LOGGER.info(
                        "Reminder sent successfully to %s",
                        os.environ.get(
                            "ADMIN_NUMBER"
                        ),  # TODO: Chnage to number in payload
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

    def _get_payload_with_mention(
        self, to_number: str, name_list: List[str], reply_to: Optional[str]
    ) -> Dict[str, Sequence[str]]:
        """Prepare payload for sending message with mentions."""
        data_manager = DataManager()
        sapeur_df = data_manager.load_dataframe("sapeurs").set_index("name")

        mentions = [str(sapeur_df.loc[name, "id"]) for name in name_list]
        text_mention = ", ".join(
            ["@" + str(sapeur_df.loc[name, "phone"])[1:] for name in name_list]
        )
        payload = {
            "session": self.session,
            "chatId": to_number,
            "text": text_mention,
            "mentions": mentions,
        }
        if reply_to:
            payload["reply_to"] = reply_to
        return payload

    def _send_group_convocation(
        self, to_number: str, poll_string: str, on_duty_name: List[str], poll_id: str
    ) -> None:
        payload = self._get_payload_with_mention(
            to_number=to_number, name_list=on_duty_name, reply_to=poll_id
        )
        group_text = f"Merci à {payload['mentions']} pour la garde: {poll_string}. Vous êtes convoqué.e.s, merci pour votre engagement :)"
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

    def _send_private_convocation(
        self, to_number: str, poll_string: str, poll_id: str
    ) -> None:
        """Send a private convocation message using an event message."""
        data_manager = DataManager()
        calendar_df = data_manager.load_dataframe("calendar").set_index("uid")
        poll_df = data_manager.load_dataframe("polls").set_index("poll_string")
        uid = poll_df.loc[poll_string, "uid"]
        event_description = f"Bonjour, Vous êtes convoqué.e.s pour la garde : {poll_string} et merci pour votre engagement :)"
        try:
            self.send_event_message(
                to_number=to_number,
                event_description=event_description,
                event_name=calendar_df.loc[uid, "name"],
                event_start_time=int(calendar_df.loc[uid, "date_start"].timestamp()),
                event_end_time=int(calendar_df.loc[uid, "date_end"].timestamp()),
                location=calendar_df.loc[uid, "location"],
                reply_to=poll_id,
            )
        except Exception as exc:
            LOGGER.exception("Error sending private convocation: %s", exc)

    def send_convocation(
        self, poll_string: str, on_duty_name: List[str], poll_id: str
    ) -> None:
        """Send a convocation message in private and in group using WAHA."""
        data_manager = DataManager()
        sapeur_df = data_manager.load_dataframe("sapeurs").set_index("name")
        self._send_group_convocation(
            to_number=os.environ.get("ADMIN_NUMBER", ""),  # TODO: change to group chat
            poll_string=poll_string,
            on_duty_name=on_duty_name,
            poll_id=poll_id,
        )
        for name in on_duty_name:
            to_number = str(sapeur_df.loc[name, "phone"])
            self._send_private_convocation(
                to_number=to_number, poll_string=poll_string, poll_id=poll_id
            )
