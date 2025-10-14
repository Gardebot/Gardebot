"""Unit tests for the VoteService in gardebot."""

from typing import Any, Dict, List

from gardebot.models.domain import VoteRecord  # type: ignore[import-untyped]
from gardebot.services.votes import VoteService  # type: ignore[import-untyped]


class InMemoryVoteRepo:
    """In-memory test double for VoteRepository."""

    def __init__(self) -> None:
        """Initialize the in-memory storage."""
        self._votes: Dict[str, Any] = {}

    def list_votes(self) -> List[VoteRecord]:
        """List all votes."""
        return list(self._votes.values())

    def upsert(self, vote: VoteRecord) -> None:
        """Insert or update a vote."""
        key = f"{vote.poll_string}:{vote.voter_name}"
        self._votes[key] = vote

    def list_by_poll(self, poll_string: str) -> List[VoteRecord]:
        """List votes for a specific poll."""
        return [v for v in self._votes.values() if v.poll_string == poll_string]


def test_record_and_retrieve_votes() -> None:
    """Test recording and retrieving votes."""
    repo = InMemoryVoteRepo()
    service = VoteService(repository=repo)
    service.record_vote("Poll1", "Alice", "Présent")
    service.record_vote("Poll1", "Bob", "Absent")
    assert set(service.list_present("Poll1")) == {"Alice"}
    assert set(service.list_absent("Poll1")) == {"Bob"}


def test_non_responding() -> None:
    """Test listing non-responding voters."""
    repo = InMemoryVoteRepo()
    service = VoteService(repository=repo)
    service.record_vote("Poll1", "Alice", "Présent")
    service.record_vote("Poll1", "Bob", None)
    non = service.list_non_responding("Poll1", include_em=True)
    assert "Bob" in non and "Alice" not in non
