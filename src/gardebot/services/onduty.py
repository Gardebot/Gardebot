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

    def is_assigned(self, event: Event) -> bool:
        """Return True if any assignment exists for poll."""
        return bool(self.repo.is_assigned(event))

    def list_assigned(self, on_duty: OnDutyAssignment) -> List[Sapeur]:
        """List assigned sapeur names for poll."""
        return self.repo.list_for_poll(on_duty)

    def assign(self, event: Event, sapeurs: List[Sapeur]) -> None:
        """Assign sapeurs to on-duty for event."""
        assignment = OnDutyAssignment(
            event=event,
            sapeur_list=sapeurs,
            assigned=True,
        )
        self.repo.write_assignment(assignment)
