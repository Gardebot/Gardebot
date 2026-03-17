"""On-duty assignment handling service."""

from __future__ import annotations

import random
from typing import List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.config import EM_NAME
from gardebot.errors import AlreadyAssignedError
from gardebot.models.domain import Event, OnDutyAssignment, Sapeur
from gardebot.repositories import OnDutyRepository
from gardebot.services.votes import VoteService

LOGGER = get_logger(__name__)


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
        """Build an on-duty assignment (does NOT persist to storage)."""
        return OnDutyAssignment(
            event=event,
            sapeur_list=sapeurs,
            assigned=True,
        )

    def save_assignment(self, assignment: OnDutyAssignment) -> None:
        """Persist an assignment to storage."""
        self.on_duty_repos.write_assignment(assignment)

    def _vote_score_pro_sapeur(self, event: Event, sapeur_list: Optional[List[Sapeur]] = None) -> pd.Series:
        """Score a sapeur for on-duty assignment based on its participation."""
        vote_df = self.vote_service.get_vote_df(sapeur_list=sapeur_list)
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
        """Processes the assignment for a single event (no cross-event fairness)."""
        return self.process_assignments([event])[0]

    def process_assignments(self, events: List[Event]) -> List[OnDutyAssignment]:
        """Process assignments for a list of events with cross-event fairness.

        Events that have reached headcount are assigned together via
        ``_assign_within_volunteers`` so the same person is not over-selected.
        Events that have *not* reached headcount fall back to ``_assign_among_all``.
        """
        for event in events:
            if self.is_assigned(event):
                raise AlreadyAssignedError(detail={"event.poll_string": event.poll_string})

        within_events: List[Event] = []
        among_all_events: List[Event] = []
        for ev in events:
            if self.vote_service.repo.count_present(ev) >= ev.headcount:
                within_events.append(ev)
            else:
                among_all_events.append(ev)

        # Batch-assign within volunteers with fairness
        within_assignments = self._assign_within_volunteers(within_events)

        # Assign among all sapeurs for remaining events with fairness
        among_all_assignments = self._assign_among_all(among_all_events)

        assignments = within_assignments + among_all_assignments
        for assignment in assignments:
            LOGGER.info(
                "Poll %s assigned to sapeurs: %s",
                assignment.event.poll_string,
                [s.name for s in assignment.sapeur_list],
            )
        return assignments

    def _assign_within_volunteers(self, events: List[Event]) -> List[OnDutyAssignment]:
        """Assign on-duty among volunteers for a batch of events with fairness.

        Tracks how many times each sapeur is selected across the batch so
        the workload is spread evenly.
        """
        # Historical assignment score (lower = less assigned in the past)
        all_volunteers: List[Sapeur] = []
        for ev in events:
            all_volunteers.extend(self.vote_service.list_present(ev))
        # Deduplicate by name for the historical score query
        unique_volunteers = list({s.name: s for s in all_volunteers}.values())
        historical_scores = (
            self._assignment_score_pro_sapeur(sapeur_list=unique_volunteers) if unique_volunteers else pd.Series(dtype=float)
        )

        batch_counts: dict[str, int] = {s.name: 0 for s in unique_volunteers}
        assignments: List[OnDutyAssignment] = []

        for event in events:
            present_sapeurs = self.vote_service.list_present(event)

            if len(present_sapeurs) == 0:
                LOGGER.debug("No present sapeur for event %s", event.poll_string)
                assignments.append(OnDutyAssignment(event=event, sapeur_list=[], assigned=False))
                continue

            n = event.headcount
            if len(present_sapeurs) <= n:
                if len(present_sapeurs) < n:
                    LOGGER.warning(
                        "Event '%s': only %d volunteers but %d required. Assigning all available.",
                        event.title,
                        len(present_sapeurs),
                        n,
                    )
                assignment = self._assign(event=event, sapeurs=present_sapeurs)
                for s in present_sapeurs:
                    batch_counts[s.name] = batch_counts.get(s.name, 0) + 1
                assignments.append(assignment)
                continue

            # Rank by historical score + batch count (lower = preferred), random tiebreak
            present_names = [s.name for s in present_sapeurs]
            combined_score = pd.Series(
                {name: historical_scores.get(name, 0.0) + batch_counts.get(name, 0) + random.random() * 1e-6
                 for name in present_names}
            )
            selected_names = combined_score.sort_values().iloc[:n].index.tolist()
            selected_sapeurs = [s for s in present_sapeurs if s.name in selected_names]

            assignment = self._assign(event=event, sapeurs=selected_sapeurs)
            for s in selected_sapeurs:
                batch_counts[s.name] = batch_counts.get(s.name, 0) + 1
            assignments.append(assignment)

        return assignments

    def _assign_among_all(self, events: List[Event]) -> List[OnDutyAssignment]:
        """Assign on-duty among all sapeurs for a batch of events with fairness.

        Volunteers are included first, then remaining slots are filled from
        all other sapeurs. A batch counter ensures fair distribution across events.
        Sapeurs who joined after the event was published are excluded.
        """
        all_sapeurs = self.on_duty_repos.list_sapeurs()
        # Compute historical scores once for all non-EM sapeurs
        eligible_sapeurs = [s for s in all_sapeurs if s.name not in EM_NAME]
        historical_scores = self._assignment_score_pro_sapeur(sapeur_list=eligible_sapeurs) if eligible_sapeurs else pd.Series(dtype=float)

        batch_counts: dict[str, int] = {s.name: 0 for s in eligible_sapeurs}
        assignments: List[OnDutyAssignment] = []

        for event in events:
            present_sapeurs = self.vote_service.list_present(event)
            present_names = {sap.name for sap in present_sapeurs}
            nb_to_nominate = event.headcount - len(present_sapeurs)

            if nb_to_nominate <= 0:
                assignment = self._assign(event=event, sapeurs=present_sapeurs[: event.headcount])
                for s in present_sapeurs[: event.headcount]:
                    batch_counts[s.name] = batch_counts.get(s.name, 0) + 1
                assignments.append(assignment)
                continue

            # Exclude sapeurs who joined after the event was published
            pending_sapeurs = [
                s
                for s in eligible_sapeurs
                if s.name not in present_names and (event.published_date is None or s.joined_date <= event.published_date)
            ]
            # Combine: vote score (non-voters=0, voters=1) + assignment history + batch count
            vote_score = self._vote_score_pro_sapeur(event=event, sapeur_list=pending_sapeurs)
            combined_score = pd.Series(
                {
                    s.name: (vote_score.get(s.name, 0.0) + historical_scores.get(s.name, 0.0)) / 2
                    + batch_counts.get(s.name, 0) + random.random() * 1e-6
                    for s in pending_sapeurs
                }
            )
            selected_names = combined_score.sort_values().iloc[:nb_to_nominate].index.tolist()
            selected_sapeurs = [s for s in pending_sapeurs if s.name in selected_names]

            all_assigned = present_sapeurs + selected_sapeurs
            assignment = self._assign(event=event, sapeurs=all_assigned)
            for s in all_assigned:
                batch_counts[s.name] = batch_counts.get(s.name, 0) + 1
            assignments.append(assignment)

        return assignments

    def create(self, overwrite: bool = False) -> None:
        """Wrapper around create from repository."""
        self.on_duty_repos.create(overwrite=overwrite)
