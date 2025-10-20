"""PollingAdapter: poll operations via WahaClient with shared services injection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytz  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.config import GROUP_ID_GARDE_ET_PIQUET
from gardebot.errors import ExternalServiceError, NotFoundError
from gardebot.integrations.waha_client import WahaClient
from gardebot.metrics import record_poll_publish, record_vote_processed
from gardebot.repositories import SapeurRepository
from gardebot.services.events import EventService
from gardebot.services.onduty import OnDutyService
from gardebot.services.votes import VoteService
from gardebot.settings import settings

LOGGER = get_logger(__name__)
TZ = pytz.timezone("Europe/Zurich")


class PollingAdapter:
    """PollingAdapter: poll operations via WahaClient with shared services injection."""

    def __init__(
        self,
        waha_client: Optional[WahaClient] = None,
        event_service: Optional[EventService] = None,
        vote_service: Optional[VoteService] = None,
        onduty_service: Optional[OnDutyService] = None,
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
        self._onduty_service = onduty_service or OnDutyService()
        self._sapeur_repo = sapeur_repository or SapeurRepository()

    def _extract_from_number(self, data: Dict[str, Any]) -> str:
        """Extract the sender's number from the webhook payload."""
        payload = data.get("payload")
        if not payload:
            raise NotFoundError(detail={"resource": "payload", "data": data})
        _data = payload.get("_data")
        if not _data:
            raise NotFoundError(detail={"resource": "_data", "payload": payload})
        info = _data.get("Info")
        if not info:
            raise NotFoundError(detail={"resource": "Info", "_data": _data})
        from_number: str = info.get("Chat")
        if not from_number:
            raise NotFoundError(detail={"resource": "Chat", "Info": info})
        return from_number

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
            "session": self._client.session,
        }
        LOGGER.debug("sending_poll", to=to_conv, title=poll_title)
        resp = self._client._http.request("POST", "/api/sendPoll", json_body=payload, raise_for_status=True)  # noqa: SLF001
        data = self._client._extract_json_dict(resp)  # noqa: SLF001
        LOGGER.info("poll_sent", to=to_conv, poll_id=data.get("id"))
        return data

    def publish_polls(self) -> None:
        """Publish polls for upcoming events."""
        event_list = self._event_service.repo.list_events()
        for evt in event_list:
            LOGGER.debug("event_check", poll_string=evt.poll_string)
            if not evt.should_be_published():
                LOGGER.debug("poll_not_due_for_publication", poll_string=evt.poll_string)
                continue
            if self._onduty_service.is_assigned(poll_string=evt.poll_string):  # TODO: change to is_published() when separation is done
                LOGGER.debug("poll_already_assigned", poll_string=evt.poll_string)
                continue
            try:
                poll_data = self.send_poll(
                    to_conv=GROUP_ID_GARDE_ET_PIQUET,
                    poll_title=evt.poll_string,
                    poll_options=["Absent", "Présent"],
                    multiple_answers=False,
                )
            except ExternalServiceError as exc:
                record_poll_publish("failure")
                LOGGER.error("poll_publish_failed", poll_string=evt.poll_string, error=str(exc))
                continue
            _ = evt.mark_published()
            if not poll_data.get("id"):
                record_poll_publish("failure")
                LOGGER.error("poll_publish_no_id", poll_string=evt.poll_string)
                continue
            poll_uid: str = poll_data.get("id", "")
            self._event_service.assign_poll_uid(evt=evt, poll_uid=poll_uid)
            record_poll_publish("success")
            LOGGER.info("poll_published", poll_string=evt.poll_string, poll_id=poll_uid)

    def process_vote_from_group(self, data: Dict[str, Any]) -> Optional[str]:
        """Process a vote event from the group; return poll_string if processed."""
        try:
            payload = data.get("payload") or {}
            _data = payload.get("_data") or {}
            info = _data.get("Info") or {}
            tmp_voter_id = info.get("SenderAlt")
            if not tmp_voter_id:
                LOGGER.warning("vote_missing_sender_alt")
                return None
            voter_id = tmp_voter_id.split("@")[0] + "@c.us"
            poll_obj = payload.get("poll") or {}
            poll_id = poll_obj.get("id")
            if not poll_id:
                LOGGER.warning("vote_missing_poll_id")
                return None
            event = self._event_service.repo.find_by_poll_uid(poll_id)
            poll_string = event.poll_string
            if self._onduty_service.is_assigned(poll_string=poll_string):
                LOGGER.debug("vote_poll_already_assigned", poll_string=poll_string)
                return None
            voter = self._sapeur_repo.find_by_uid(voter_id).name
            vote_payload = payload.get("vote") or {}
            selected_options = vote_payload.get("selectedOptions", [])
            vote_value = selected_options[0] if selected_options else None
            self._vote_service.record_vote(poll_string=poll_string, voter_name=voter, value=vote_value)
            record_vote_processed("success")
            LOGGER.info("vote_processed", voter=voter, poll_string=poll_string, vote=vote_value)
            return poll_string
        except NotFoundError as nf:
            record_vote_processed("error")
            LOGGER.error("vote_not_found_error", detail=nf.detail)
            return None
        except Exception as exc:  # noqa: BLE001
            record_vote_processed("error")
            LOGGER.error("vote_processing_error", error=str(exc))
            LOGGER.debug("vote_raw_event", raw=data)
            return None

    def process_vote_from_admin(self, data: Dict[str, Any]) -> None:
        """Process a vote event from the admin chat."""
        # TODO: Implement admin vote logic
        pass
