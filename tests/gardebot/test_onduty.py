"""Tests for the OnDutyService and OnDutyRepository implementations."""

from typing import Any, Dict, List

from gardebot.models.domain import OnDutyAssignment  # type: ignore[import-untyped]
from gardebot.services.onduty import OnDutyService  # type: ignore[import-untyped]


class InMemoryOnDutyRepo:
    """In-memory test double for OnDutyRepository."""

    def __init__(self) -> None:
        """Initialize the in-memory storage."""
        self._assignments: Dict[str, Any] = {}

    def list_assignments(self) -> List[OnDutyAssignment]:
        return list(self._assignments.values())

    def add_assignment(self, assignment: OnDutyAssignment) -> None:
        key = f"{assignment.poll_string}:{assignment.sapeur_name}"
        self._assignments[key] = assignment

    def list_for_poll(self, poll_string: str) -> List[OnDutyAssignment]:
        return [a for a in self._assignments.values() if a.poll_string == poll_string]

    def is_assigned(self, poll_string: str) -> bool:
        return any(a.poll_string == poll_string for a in self._assignments.values())


def test_assign_and_retrieve() -> None:
    """Test assigning and retrieving on-duty assignments."""
    repo = InMemoryOnDutyRepo()
    service = OnDutyService(repository=repo)
    service.assign("PollX", ["Alice", "Bob"])
    assert service.is_assigned("PollX")
    assigned = service.list_assigned("PollX")
    assert set(assigned) == {"Alice", "Bob"}
