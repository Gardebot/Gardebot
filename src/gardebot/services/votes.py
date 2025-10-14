"""Vote handling service."""

from __future__ import annotations

from typing import List

from gardebot.config import EM_NAME
from gardebot.models.domain import VoteRecord
from gardebot.repositories import VoteRepository


class VoteService:
    """Handle voting logic (record, aggregate, completion checks)."""

    def __init__(self, repository: VoteRepository | None = None) -> None:
        """Initialize with optional custom repository."""
        self.repo = repository or VoteRepository()

    def record_vote(self, poll_string: str, voter_name: str, value: str | None) -> VoteRecord:
        """Record a vote (Présent / Absent / None)."""
        if value not in ("Présent", "Absent", None):
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
        present = {v.voter_name for v in self.repo.list_by_poll(poll_string) if v.vote is not None}
        all_voters = {v.voter_name for v in self.repo.list_by_poll(poll_string)}
        non = [n for n in all_voters if n not in present]
        if not include_em:
            non = [n for n in non if n not in EM_NAME]
        return non

    def completion_reached(self, poll_string: str, required_headcount: int) -> bool:
        """Return True if number of present votes >= required headcount."""
        return len(self.list_present(poll_string)) >= required_headcount

    def everyone_voted(self, poll_string: str, population: List[str]) -> bool:
        """Return True if all provided population (excluding EM_NAME) have responded."""
        must = [p for p in population if p not in EM_NAME]
        responded = {v.voter_name for v in self.repo.list_by_poll(poll_string) if v.vote is not None and v.voter_name not in EM_NAME}
        return set(must) == responded
