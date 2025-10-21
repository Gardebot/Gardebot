"""Vote handling service."""

from __future__ import annotations

import logging
from typing import List

from gardebot.config import EM_NAME
from gardebot.models.domain import Event, Sapeur, VoteRecord
from gardebot.repositories import VoteRepository

LOGGER = logging.getLogger(__name__)


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
        return [v.sapeur for v in self.repo.list_by_poll(event) if v.value]

    def list_absent(self, event: Event) -> List[Sapeur]:
        """List sapeur who voted Absent."""
        return [v.sapeur for v in self.repo.list_by_poll(event) if not v.value]

    def list_non_responding(self, event: Event, include_em: bool = False) -> List[Sapeur]:
        """List users who have not responded."""
        have_voted = [v.sapeur.name for v in self.repo.list_by_poll(event) if v.value is not None]
        all_voters = [v.sapeur for v in self.repo.list_by_poll(event)]
        non_responding = [n for n in all_voters if n.name not in have_voted]
        if not include_em:
            non_responding = [n for n in non_responding if n.name not in EM_NAME]
        return non_responding
