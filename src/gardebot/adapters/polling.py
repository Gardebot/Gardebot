"""PollingAdapter: high-level poll operations via WahaClient (composition over inheritance)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz  # type: ignore[import-untyped]

from gardebot.config import GROUP_ID_GARDE_ET_PIQUET
from gardebot.errors import ExternalServiceError
from gardebot.integrations.waha_client import WahaClient
from gardebot.repositories import SapeurRepository
from gardebot.services.events import EventService
from gardebot.services.onduty import OnDutyService
from gardebot.services.votes import VoteService
from gardebot.settings import settings

LOGGER = logging.getLogger(__name__)


class PollingAdapter:
    """Encapsulates poll-related logic and WAHA interactions."""

    def __init__(self, waha_client: Optional[WahaClient] = None) -> None:
        """Initialize with optional custom WahaClient."""
        self._client = waha_client or WahaClient(
            api_key=settings.api.api_key,
            base_url=settings.api.base_url,
            session=settings.api.session,
            timeout=settings.api.timeout_seconds,
            retries=settings.api.retry_attempts,
        )

    # ------------------------------------------------------------------ #
    # Outbound operations
    # ------------------------------------------------------------------ #
    def send_poll(
        self,
        to_conv: str,
        poll_title: str,
        poll_options: List[str],
        multiple_answers: bool = False,
    ) -> Dict[str, Any]:
        """Send a poll. Returns parsed JSON or raises ExternalServiceError."""
        payload = {
            "chatId": to_conv,
            "poll": {
                "name": poll_title,
                "options": poll_options,
                "multipleAnswers": multiple_answers,
            },
            "session": self._client.session,
        }
        LOGGER.debug(
            "sending_poll",
            extra={"to": to_conv, "title": poll_title, "options": poll_options, "multiple": multiple_answers},
        )
        resp = self._client._http.request("POST", "/api/sendPoll", json_body=payload, raise_for_status=True)  # noqa: SLF001
        data = self._client._extract_json_dict(resp)  # noqa: SLF001
        LOGGER.info("poll_sent", extra={"to": to_conv, "poll_id": data.get("id")})
        return data

    def publish_polls(self) -> None:
        """Iterate over gardes and publish due polls. Returns list of published poll_strings."""
        event_service = EventService()
        event_list = event_service.repo.list_events()
        for evt in event_list:
            LOGGER.debug("event_check", extra={"poll_string": evt.poll_string})
            if evt.is_published():
                LOGGER.debug("poll_already_published", extra={"poll_string": evt.poll_string})
                continue
            if evt.scheduled_publication_date.date() > datetime.now(pytz.timezone("Europe/Zurich")).date():
                LOGGER.debug("poll_not_due_yet", extra={"poll_string": evt.poll_string})
                continue
            if evt.is_assigned():
                LOGGER.debug("poll_already_assigned", extra={"poll_string": evt.poll_string})
                continue
            try:
                poll_data = self.send_poll(
                    to_conv=GROUP_ID_GARDE_ET_PIQUET,
                    poll_title=evt.poll_string,
                    poll_options=["Absent", "Présent"],
                    multiple_answers=False,
                )
            except ExternalServiceError as exc:
                LOGGER.error("poll_publish_failed", extra={"poll_string": evt.poll_string, "error": str(exc)})
                continue
            evt.mark_published()
            if not poll_data.get("id"):
                LOGGER.error("poll_publish_no_id", extra={"poll_string": evt.poll_string})
                continue
            poll_uid: str = poll_data.get("id", "")
            event_service.assign_poll_uid(evt=evt, poll_uid=poll_uid)
            LOGGER.info("poll_published", extra={"poll_string": evt.poll_string, "poll_id": poll_data.get("id")})

    # ------------------------------------------------------------------ #
    # Inbound processing
    # ------------------------------------------------------------------ #
    def process_vote_from_group(self, data: Dict[str, Any]) -> Optional[str]:
        """Process inbound vote event, update Vote table, return poll_string or None."""
        event_service = EventService()
        vote_service = VoteService()
        on_duty_service = OnDutyService()
        sapeur_repository = SapeurRepository()

        try:
            payload = data.get("payload")
            if payload is None:
                LOGGER.info("vote_no_payload")
                return None

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
            garde = event_service.repo.find_by_poll_uid(poll_id)
            if not garde:
                raise ValueError(f"Event with poll_id {poll_id} not found")
            poll_string: str = garde.poll_string

            if on_duty_service.is_assigned(poll_string=poll_string):
                LOGGER.debug("vote_poll_already_assigned", extra={"poll_string": poll_string})
                return None

            voter = sapeur_repository.find_by_uid(voter_id).name
            vote_payload = payload.get("vote") or {}
            selected_options = vote_payload.get("selectedOptions", [])
            vote_value = selected_options[0] if selected_options else None

            vote_service.record_vote(poll_string=poll_string, voter_name=voter, value=vote_value)

            LOGGER.info(
                "vote_processed",
                extra={"voter": voter, "poll_string": poll_string, "vote": vote_value},
            )
            return poll_string
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("vote_processing_error", extra={"error": str(exc)})
            LOGGER.debug("vote_raw_event", extra={"data": data})
            return None
