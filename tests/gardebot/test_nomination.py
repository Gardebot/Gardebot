"""Tests for the NominationService in gardebot."""

from typing import List

from gardebot.models.domain import OnDutyAssignment, VoteRecord  # type: ignore[import-untyped]
from gardebot.services.nomination import NominationService  # type: ignore[import-untyped]


class InMemoryVotes:
    """In-memory test double for VoteRepository."""

    def __init__(self) -> None:
        """Initialize the in-memory storage."""
        self._votes: List[VoteRecord] = []

    def list_votes(self) -> List[VoteRecord]:
        """List all votes."""
        return self._votes

    def upsert(self, vote: VoteRecord) -> None:
        """Insert or update a vote."""
        self._votes = [v for v in self._votes if not (v.poll_string == vote.poll_string and v.voter_name == vote.voter_name)]
        self._votes.append(vote)


class InMemoryOnDuty:
    """In-memory test double for OnDutyRepository."""

    def __init__(self) -> None:
        """Initialize the in-memory storage."""
        self._assignments: List[OnDutyAssignment] = []

    def list_assignments(self) -> List[OnDutyAssignment]:
        """List all assignments."""
        return self._assignments

    def add_assignment(self, assignment: OnDutyAssignment) -> None:
        """Add or update an assignment."""
        self._assignments = [
            a for a in self._assignments if not (a.poll_string == assignment.poll_string and a.sapeur_name == assignment.sapeur_name)
        ]
        self._assignments.append(assignment)


def test_nomination_flows() -> None:
    """Test nomination flows."""
    votes_repo = InMemoryVotes()
    onduty_repo = InMemoryOnDuty()
    # Simulate three polls, three people
    for poll in ["P1", "P2", "P3"]:
        votes_repo.upsert(VoteRecord(poll_string=poll, voter_name="Alice", vote="Présent"))
        votes_repo.upsert(VoteRecord(poll_string=poll, voter_name="Bob", vote=None))
        votes_repo.upsert(VoteRecord(poll_string=poll, voter_name="Charlie", vote="Absent"))

    onduty_repo.add_assignment(OnDutyAssignment(poll_string="P1", sapeur_name="Alice"))
    service = NominationService(votes_repo, onduty_repo)
    non_responding = ["Bob"]
    absent = ["Charlie"]
    result = service.force_nomination("P3", 2, non_responding, absent)
    assert "Bob" in result or "Charlie" in result
