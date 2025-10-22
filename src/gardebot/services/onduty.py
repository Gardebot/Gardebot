"""On-duty assignment handling service."""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.config import EM_NAME
from gardebot.errors import AlreadyAssignedError
from gardebot.models.domain import Event, OnDutyAssignment, Sapeur
from gardebot.repositories import OnDutyRepository
from gardebot.services.votes import VoteService

LOGGER = logging.getLogger(__name__)


class OnDutyService:
    """Handle on-duty assignment logic."""

    def __init__(self, on_duty_repos: Optional[OnDutyRepository] = None, vote_service: Optional[VoteService] = None) -> None:
        """Initialize with optional custom repository."""
        self.on_duty_repos = on_duty_repos or OnDutyRepository()
        self.vote_service = vote_service or VoteService()

    def is_assigned(self, event: Event) -> bool:
        """Return True if any assignment exists for poll."""
        return bool(self.on_duty_repos.is_assigned(event))

    def list_assigned_events(self) -> List[OnDutyAssignment]:
        """List events with assignments."""
        assignment_list = self.on_duty_repos.list_assignments()
        return [assignment for assignment in assignment_list if assignment.assigned]

    def _assign(self, event: Event, sapeurs: List[Sapeur]) -> OnDutyAssignment:
        """Assign sapeurs to on-duty for event."""
        assignment = OnDutyAssignment(
            event=event,
            sapeur_list=sapeurs,
            assigned=True,
        )
        self.on_duty_repos.write_assignment(assignment)
        return assignment

    def _vote_score_pro_sapeur(self, event: Event, sapeur_list: Optional[List[Sapeur]] = None) -> pd.Series:
        """Score a sapeur for on-duty assignment based on its participation."""
        vote_df = self.vote_service.repo.get_vote_df(sapeur_list=sapeur_list)
        return vote_df[event.poll_string].map({True: 1, False: 1, None: 0})

    def _assignment_score_pro_sapeur(self, sapeur_list: Optional[List[Sapeur]] = None) -> pd.Series:
        """Score a sapeur for on-duty assignment based on its previous assignments."""
        assigned_event = [ass.event for ass in self.list_assigned_events()]
        on_duty_df = self.on_duty_repos.get_onduty_df(event_list=assigned_event, sapeur_list=sapeur_list)
        if len(assigned_event) == 0:
            data = {sap: 0 for sap in on_duty_df.index}
            return pd.Series(data)
        return on_duty_df.mean(axis=1)

    def _score_pro_sapeur(self, event: Event, sapeur_list: Optional[List[Sapeur]] = None) -> pd.Series:
        """Score for on-duty assignment based on its overall participation."""
        vote_score = self._vote_score_pro_sapeur(event=event, sapeur_list=sapeur_list)
        on_duty_score = self._assignment_score_pro_sapeur(sapeur_list=sapeur_list)
        return (vote_score + on_duty_score) / 2

    def process_assignment(self, event: Event) -> OnDutyAssignment:
        """Processes the assignment for a given event."""
        if self.is_assigned(event):
            raise AlreadyAssignedError(detail={"event.poll_string": event.poll_string})
        if self.vote_service.test_headcount_reached(event):
            assignment = self._assign_within_volunteers(event)
        else:
            assignment = self._assign_among_all(event)

        LOGGER.info("Poll %s assigned to sapeurs: %s", event.poll_string, [s.name for s in assignment.sapeur_list])

        return assignment

    def _assign_within_volunteers(self, event: Event) -> OnDutyAssignment:
        """Assign on-duty among volunteers (present voters)."""
        present_sapeurs = self.vote_service.list_present(event)
        if len(present_sapeurs) == 0:
            LOGGER.debug("No present sapeur for event %s", event.poll_string)
            return OnDutyAssignment(
                event=event,
                sapeur_list=[],
                assigned=False,
            )
        if len(present_sapeurs) == event.headcount:
            assignment = self._assign(event=event, sapeurs=present_sapeurs)
            return assignment
        score_series = self._assignment_score_pro_sapeur(sapeur_list=present_sapeurs)
        selected_sapeurs = score_series.sort_values().iloc[: event.headcount].index.tolist()
        assignment = self._assign(event=event, sapeurs=[sap for sap in present_sapeurs if sap.name in selected_sapeurs])
        return assignment

    def _assign_among_all(self, event: Event) -> OnDutyAssignment:
        """Assign on-duty among all sapeurs."""
        present_sapeurs = self.vote_service.list_present(event)
        present_sapeurs_names = [sap.name for sap in present_sapeurs]
        nb_to_nominate = event.headcount - len(present_sapeurs)
        all_sapeurs = self.on_duty_repos.sapeur_repository.list_sapeurs()
        pending_sapeur = [sap for sap in all_sapeurs if sap.name not in present_sapeurs_names + EM_NAME]
        score_pending_sapeur = self._score_pro_sapeur(event=event, sapeur_list=pending_sapeur)
        selected_sapeurs_name = score_pending_sapeur.sort_values().iloc[:nb_to_nominate].index.tolist()
        selected_sapeurs = [sap for sap in pending_sapeur if sap.name in selected_sapeurs_name]
        assignment = self._assign(event=event, sapeurs=present_sapeurs + selected_sapeurs)
        return assignment
