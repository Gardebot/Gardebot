"""Vote handling service."""

from __future__ import annotations

import logging
from typing import List

from gardebot.config import EM_NAME, VOTE_OPTIONS
from gardebot.models.domain import Event, VoteRecord
from gardebot.repositories import VoteRepository

LOGGER = logging.getLogger(__name__)


class VoteService:
    """Handle voting logic (record, aggregate, completion checks)."""

    def __init__(self, repository: VoteRepository | None = None) -> None:
        """Initialize with optional custom repository."""
        self.repo = repository or VoteRepository()

    def record_vote(self, poll_string: str, voter_name: str, value: str | None) -> VoteRecord:
        """Record a vote (Présent / Absent / None)."""
        LOGGER.info("Recording vote for %s: %s voted %s", poll_string, voter_name, value)
        if value not in [None] + VOTE_OPTIONS:
            raise ValueError(f"Invalid vote value {value}")
        rec = VoteRecord(poll_string=poll_string, voter_name=voter_name, vote=value)
        self.repo.upsert(rec)
        return rec

    def list_present(self, poll_string: str) -> List[str]:
        """List names who voted Present."""
        return [v.voter_name for v in self.repo.list_by_poll(poll_string) if v.vote == "Présent"]

    def list_absent(self, poll_string: str) -> List[str]:
        """List names who voted Absent."""
        return [v.voter_name for v in self.repo.list_by_poll(poll_string) if v.vote == "Absent"]

    def list_non_responding(self, poll_string: str, include_em: bool = False) -> List[str]:
        """List users who have not responded."""
        have_voted = [v.voter_name for v in self.repo.list_by_poll(poll_string) if v.vote is not None]
        all_voters = [v.voter_name for v in self.repo.list_by_poll(poll_string)]
        non_responding = [n for n in all_voters if n not in have_voted]
        if not include_em:
            non_responding = [n for n in non_responding if n not in EM_NAME]
        return non_responding

    def completion_reached(self, event: Event) -> bool:
        """Return True if number of present votes >= required headcount."""
        return len(self.list_present(event.poll_string)) >= event.headcount

    def everyone_voted(self, poll_string: str) -> bool:
        """Return True if all provided population (excluding EM_NAME) have responded."""
        non_responding = self.list_non_responding(poll_string, include_em=False)
        return len(non_responding) == 0
