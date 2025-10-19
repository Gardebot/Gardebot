"""On-duty assignment handling service."""

from __future__ import annotations

from typing import List

from gardebot.models.domain import Event, OnDutyAssignment, Sapeur
from gardebot.repositories import OnDutyRepository


class OnDutyService:
    """Handle on-duty assignment logic."""

    def __init__(self, repository: OnDutyRepository | None = None) -> None:
        """Initialize with optional custom repository."""
        self.repo = repository or OnDutyRepository()

    def is_assigned(self, poll_string: str) -> bool:
        """Return True if any assignment exists for poll."""  # TODO: This should test a boolean
        return self.repo.is_assigned(poll_string)

    def list_assigned(self, poll_string: str) -> List[str]:
        """List assigned sapeur names for poll."""
        return [sap.name for sap in self.repo.list_for_poll(poll_string)]

    def assign(self, event: Event, sapeurs: List[Sapeur]) -> None:
        """Assign sapeurs to on-duty for event."""
        assignment = OnDutyAssignment(
            event=event,
            sapeur_list=sapeurs,
            assigned=True,
        )
        self.repo.write_assignment(assignment)
