"""On-duty assignment handling service."""

from __future__ import annotations

from typing import List

from gardebot.models.domain import OnDutyAssignment
from gardebot.repositories import OnDutyRepository


class OnDutyService:
    """Handle on-duty assignment logic."""

    def __init__(self, repository: OnDutyRepository | None = None) -> None:
        """Initialize with optional custom repository."""
        self.repo = repository or OnDutyRepository()

    def assign(self, poll_string: str, names: List[str]) -> List[OnDutyAssignment]:
        """Assign one or multiple sapeurs to a poll (idempotent)."""
        assignments = []
        for name in names:
            a = OnDutyAssignment(poll_string=poll_string, sapeur_name=name, assigned=True)
            self.repo.add_assignment(a)
            assignments.append(a)
        return assignments

    def is_assigned(self, poll_string: str) -> bool:
        """Return True if any assignment exists for poll."""
        return self.repo.is_assigned(poll_string)

    def list_assigned(self, poll_string: str) -> List[str]:
        """List assigned sapeur names for poll."""
        return [a.sapeur_name for a in self.repo.list_for_poll(poll_string)]
