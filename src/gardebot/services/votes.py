"""Vote handling service."""

from __future__ import annotations

from typing import List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.config import EM_NAME, MAX_NB_REMINDER
from gardebot.models.domain import Event, Sapeur, VoteRecord
from gardebot.repositories import SapeurRepository, VoteRepository

LOGGER = get_logger(__name__)


class VoteService:
    """Handle voting logic (record, aggregate, completion checks)."""

    def __init__(self, repository: VoteRepository | None = None) -> None:
        """Initialize with optional custom repository."""
        self.repo = repository or VoteRepository()

    def record_vote(self, rec: VoteRecord) -> VoteRecord:
        """Record a vote (Présent / Absent / None)."""
        LOGGER.info("Recording vote for %s: %s voted %s", rec.event.poll_string, rec.sapeur.name, rec.value)
        self.repo.upsert(rec)
        return rec

    def list_present(self, event: Event) -> List[Sapeur]:
        """List sapeur who voted Present."""
        return [v.sapeur for v in self.repo.list_by_poll(event) if v.value is True]

    def list_absent(self, event: Event) -> List[Sapeur]:
        """List sapeur who voted Absent."""
        return [v.sapeur for v in self.repo.list_by_poll(event) if v.value is False]

    def list_non_responding(self, event: Event, include_em: bool = False) -> List[Sapeur]:
        """List users who have not responded."""
        have_voted = [v.sapeur.name for v in self.repo.list_by_poll(event) if v.value is not None]
        sap_repo = SapeurRepository()
        tmp_all_voters = sap_repo.list_sapeurs()
        all_voters = [sap for sap in tmp_all_voters if sap.joined_date <= event.published_date]
        non_responding = [n for n in all_voters if n.name not in have_voted]
        if not include_em:
            non_responding = [n for n in non_responding if n.name not in EM_NAME]
        return non_responding

    def test_headcount_reached(self, event: Event) -> bool:
        """Test if headcount is reached for an event."""
        if self.repo.count_present(event) >= event.headcount:
            LOGGER.info("Headcount reached for %s", event.poll_string)
            return True
        return False

    def test_all_responded(self, event: Event) -> bool:
        """Test if all sapeurs have responded for an event."""
        if len(self.list_non_responding(event, include_em=False)) == 0:
            LOGGER.info("All sapeurs have voted to %s", event.poll_string)
            return True
        return False

    def test_max_reminders(self, event: Event) -> bool:
        """Test if maximum number of reminders is reached for an event."""
        if event.nb_reminder >= MAX_NB_REMINDER:
            LOGGER.info("Maximum number of reminders reached for %s", event.poll_string)
            return True
        return False

    def test_event_completion(self, event: Event) -> bool:
        """Test if an event can be processed for assignment."""
        return self.test_headcount_reached(event) or self.test_all_responded(event) or self.test_max_reminders(event)

    def get_vote_df(self, event_list: Optional[List[Event]] = None, sapeur_list: Optional[List[Sapeur]] = None) -> pd.DataFrame:
        """Wrapper around get vote from repository."""
        vote_df = self.repo.get_vote_df(event_list=event_list, sapeur_list=sapeur_list)
        return vote_df

    def create(self, overwrite: bool = False) -> None:
        """Wrapper around create from repository."""
        self.repo.create(overwrite=overwrite)
