"""PollingAdapter: poll operations via WahaClient with shared services injection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.config import GENEVA_TZ, VOTE_OPTIONS
from gardebot.errors import NotFoundError
from gardebot.integrations.waha_client import WahaClient
from gardebot.models.domain import Event, Sapeur, VoteRecord
from gardebot.repositories import SapeurRepository
from gardebot.services.events import EventService
from gardebot.services.onduty import OnDutyService
from gardebot.services.votes import VoteService

LOGGER = get_logger(__name__)


class PollingAdapter(WahaClient):
    """PollingAdapter: poll operations via WahaClient with shared services injection."""

    def __init__(
        self,
        event_service: Optional[EventService] = None,
        vote_service: Optional[VoteService] = None,
        onduty_service: Optional[OnDutyService] = None,
        sapeur_repository: Optional[SapeurRepository] = None,
    ) -> None:
        """Initialize with optional shared services and WahaClient."""
        super().__init__()
        self._event_service = event_service or EventService()
        self._vote_service = vote_service or VoteService()
        self._onduty_service = onduty_service or OnDutyService()
        self._sapeur_repo = sapeur_repository or SapeurRepository()

    def _extract_payload_from_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the payload dictionary from the webhook data."""
        tmp_payload = data.get("payload")
        if not tmp_payload:
            raise NotFoundError(detail={"resource": "payload", "data": data})
        payload: Dict[str, Any] = tmp_payload
        return payload

    def _extract_info_from_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the Info dictionary from the webhook payload."""
        payload = self._extract_payload_from_data(data)
        _data = payload.get("_data")
        if not _data:
            raise NotFoundError(detail={"resource": "_data", "payload": payload})
        info: Dict[str, Any] = _data.get("Info")
        if not info:
            raise NotFoundError(detail={"resource": "Info", "_data": _data})
        return info

    def _extract_chat_id_from_data(self, data: Dict[str, Any]) -> str:
        """Extract the ChatId where the vote happened from the webhook payload."""
        info = self._extract_info_from_data(data)
        from_number: Optional[str] = info.get("Chat")
        if not from_number:
            raise NotFoundError(detail={"resource": "Chat", "Info": info})
        return from_number

    def _extract_sapeur_from_payload(self, data: Dict[str, Any]) -> Sapeur:
        """Extract the sapeur object from the webhook payload."""
        info = self._extract_info_from_data(data)
        tmp_voter_id = info.get("SenderAlt")
        if not tmp_voter_id:
            raise NotFoundError(detail={"resource": "SenderAlt", "Info": info})
        voter_id = tmp_voter_id.split("@")[0] + "@c.us"
        sapeur = self._sapeur_repo.find_by_uid(voter_id)
        return sapeur

    def _extract_vote_value_from_data(self, data: Dict[str, Any]) -> Optional[str]:
        """Extract the vote value from the webhook payload."""
        payload = self._extract_payload_from_data(data)
        vote_obj = payload.get("vote")
        if not vote_obj:
            raise NotFoundError(detail={"resource": "vote", "payload": payload})
        selected_options = vote_obj.get("selectedOptions")
        if selected_options is None:
            raise NotFoundError(detail={"resource": "vote.selectedOptions", "vote": vote_obj})
        vote_value: Optional[str] = selected_options[0] if selected_options else None
        return vote_value

    def _extract_event_from_data(self, data: Dict[str, Any]) -> Event:
        """Extract the event object associated with the vote from the webhook payload."""
        payload = self._extract_payload_from_data(data)
        poll_obj = payload.get("poll")
        if not poll_obj:
            raise NotFoundError(detail={"resource": "poll", "payload": payload})
        poll_id = poll_obj.get("id")
        if not poll_id:
            raise NotFoundError(detail={"resource": "poll.id", "poll": poll_obj})
        event = self._event_service.find_by_poll_uid(poll_id)
        return event

    def process_vote_from_group(self, data: Dict[str, Any]) -> None:
        """Process a vote event from the group; return event if processed."""
        try:
            event = self._extract_event_from_data(data)
            if self._onduty_service.is_assigned(event=event):
                LOGGER.info("vote_ignored_event_already_assigned", poll_string=event.poll_string)
                return
            sapeur = self._extract_sapeur_from_payload(data)
            tmp_vote_value = self._extract_vote_value_from_data(data)
            if tmp_vote_value not in VOTE_OPTIONS and tmp_vote_value is not None:
                raise ValueError(f"Invalid vote value {tmp_vote_value}")
            vote_value = VOTE_OPTIONS.get(tmp_vote_value) if tmp_vote_value else None
            vote = VoteRecord(event=event, sapeur=sapeur, value=vote_value)
            self._vote_service.record_vote(vote)
            if self._vote_service.test_event_completion(event):
                LOGGER.info("event_ready_for_assignment", poll_string=event.poll_string)
        except NotFoundError as nf:
            LOGGER.error("vote_not_found_error", detail=nf.detail)
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("vote_processing_error", error=str(exc), data=data)

    def process_vote_from_admin(self, data: Dict[str, Any]) -> None:
        """Process a vote event from the admin chat."""
        # TODO: Implement admin vote logic
        pass

    def should_be_published(self, event: Event) -> bool:
        """Determine if the event is due for publication."""
        if event.is_published():
            LOGGER.debug("event_already_published", poll_string=event.poll_string)
            return False
        today = pd.Timestamp.now(tz=GENEVA_TZ).date()
        if event.scheduled_publication_date.date() > today:
            LOGGER.debug("event_not_due_yet", poll_string=event.poll_string)
            return False
        if self._onduty_service.is_assigned(event=event):  # TODO: change to is_published() when separation is done
            LOGGER.debug("poll_already_assigned", poll_string=event.poll_string)
            return False

        return True

    def send_poll(
        self,
        to_conv: str,
        poll_title: str,
        poll_options: List[str],
        multiple_answers: bool = False,
    ) -> Dict[str, Any]:
        """Send a poll to a conversation."""
        payload = {
            "chatId": to_conv,
            "poll": {
                "name": poll_title,
                "options": poll_options,
                "multipleAnswers": multiple_answers,
            },
            "session": self.session,
        }
        LOGGER.debug("sending_poll", to=to_conv, title=poll_title)
        resp = self.post("/api/sendPoll", json_body=payload, raise_for_status=True)
        data = self.extract_json_dict(resp)  # noqa: SLF001
        LOGGER.info("poll_sent", to=to_conv, poll_id=data.get("id"))
        return data

    def list_events(self) -> List[Event]:
        """Wrapper around event service to list events."""
        return self._event_service.list_events()

    def assign_poll_uid(self, event: Event, poll_uid: str) -> Event:
        """Wrapper around event service to assign poll uid."""
        return self._event_service.assign_poll_uid(event=event, poll_uid=poll_uid)

    def mark_published(self, event: Event) -> Event:
        """Wrapper around event service to mark event as published."""
        return self._event_service.mark_published(event=event)
