"""CRUD repositories for domain models, backed by Parquet files."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.common.storage import FileStorage
from gardebot.config import EVENTS_FILE, ONDUTY_FILE, SAPEURS_FILE, VOTES_FILE
from gardebot.errors import NotFoundError
from gardebot.models.domain import Event, OnDutyAssignment, Sapeur, VoteRecord

LOGGER = get_logger(__name__)


def _base_name(title: str) -> str:
    """Strip trailing numeric suffix: 'Piquet de Pâques 5' → 'Piquet de Pâques'."""
    return re.sub(r"\s+\d+$", "", title).strip()


def _clean_record(row: dict) -> dict:
    """Convert float NaN values (from mixed-type DataFrame columns) to None."""
    return {k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in row.items()}


def _find_matching_column(df: pd.DataFrame, event: Event) -> Optional[str]:
    """Find a column whose date+location suffix matches the event's poll_string suffix.

    Matches on everything after ' : ' in the poll_string (the date and location part),
    so 'Piquet de Pâques 5 : samedi 4 avril...' and 'Piquet de Pâques : samedi 4 avril...'
    are considered matching.
    """
    if " : " not in event.poll_string:
        return None
    event_suffix = event.poll_string.split(" : ", 1)[1]
    for col in df.columns:
        if " : " in col and col.split(" : ", 1)[1] == event_suffix:
            return col
    return None


class EventRepository:
    """CRUD operations for Event objects."""

    def __init__(self, storage: Optional[FileStorage] = None) -> None:
        """Initialize with optional custom storage backend."""
        self.storage = storage or FileStorage()

    def create(self, overwrite: bool = False) -> None:
        """Create empty event storage (optionally overwriting existing)."""
        df = self.storage.read_parquet(EVENTS_FILE)
        if df.empty or overwrite:
            columns = list(Event.model_fields.keys())
            empty_df = pd.DataFrame(columns=columns)
            self.storage.atomic_write(empty_df, EVENTS_FILE)

    def list_events(self) -> List[Event]:
        """Return all stored events."""
        df = self.storage.read_parquet(EVENTS_FILE)
        if df.empty:
            LOGGER.debug("events_empty")
            return []
        return [
            Event(**_clean_record(row)) for row in df.to_dict(orient="records")
        ]  # TODO: deal with possibility new fields in Event which are not in df

    def upsert_event(self, event: Event) -> None:
        """Insert or update an event based on its uid."""

        def modify(df: pd.DataFrame) -> pd.DataFrame:
            events = []
            if not df.empty:
                events = [Event(**_clean_record(row)) for row in df.to_dict(orient="records")]
            existing = {e.uid: e for e in events}
            existing[event.uid] = event
            return pd.DataFrame([e.model_dump() for e in existing.values()])

        self.storage.force_atomic_read_modify_write(EVENTS_FILE, modify)

    def bulk_upsert(self, events: Iterable[Event]) -> None:
        """Upsert multiple events."""
        from collections import defaultdict

        def modify(df: pd.DataFrame) -> pd.DataFrame:
            current_events = []
            if not df.empty:
                current_events = [Event(**_clean_record(row)) for row in df.to_dict(orient="records")]
            current = {e.uid: e for e in current_events}

            # Phase 0: Deduplicate existing rows by natural key (base name + start/end/location)
            # Group existing events by (base_title, start, end, location) and keep the best one
            phase0_groups: defaultdict[tuple, list] = defaultdict(list)
            for e in current_events:
                nk = (str(e.start_date), str(e.end_date), e.location, _base_name(e.title))
                phase0_groups[nk].append(e)
            phase0_changed = False
            for nk, group in phase0_groups.items():
                if len(group) > 1:
                    best = max(
                        group,
                        key=lambda e: (
                            e.ical_uid is not None,
                            e.poll_uid is not None,
                            e.published_date is not None and not pd.isna(e.published_date),
                            e.nb_reminder or 0,
                        ),
                    )
                    for e in group:
                        if e.uid != best.uid:
                            LOGGER.info("phase0_dedup_remove", uid=e.uid, title=e.title, kept_uid=best.uid)
                            current.pop(e.uid, None)
                            phase0_changed = True

            # Build secondary index: natural key -> list of uids (handles pre-existing duplicates)
            legacy_index: defaultdict[tuple, list] = defaultdict(list)
            for e in current.values():
                natural_key = (str(e.start_date), str(e.end_date), e.location)
                legacy_index[natural_key].append(e.uid)

            new_event_added = False
            for ev in events:
                natural_key = (str(ev.start_date), str(ev.end_date), ev.location)
                existing_uids = legacy_index.get(natural_key, [])

                if ev.uid in current:
                    # Already exists with same UID, skip
                    continue

                if existing_uids:
                    # Find the best old entry (most metadata) among all duplicates for this slot
                    old_events = [current[uid] for uid in existing_uids if uid in current]
                    if old_events:
                        best_old = max(
                            old_events,
                            key=lambda e: (
                                e.poll_uid is not None,
                                e.published_date is not None and not pd.isna(e.published_date),
                                e.nb_reminder or 0,
                            ),
                        )
                        # Remove ALL old entries for this natural key (they are all duplicates)
                        for uid in existing_uids:
                            current.pop(uid, None)
                        # Add new event with migrated metadata
                        current[ev.uid] = ev.model_copy(update={
                            "poll_uid": best_old.poll_uid,
                            "published_date": best_old.published_date,
                            "nb_reminder": best_old.nb_reminder,
                            "scheduled_publication_date": best_old.scheduled_publication_date,
                        })
                        new_event_added = True
                        continue

                # Completely new event
                current[ev.uid] = ev
                new_event_added = True

            if new_event_added or phase0_changed:
                return pd.DataFrame([e.model_dump() for e in current.values()])
            else:
                LOGGER.info("no_new_events")
                return df  # Return unchanged

        self.storage.force_atomic_read_modify_write(EVENTS_FILE, modify)

    def find_by_uid(self, uid: str) -> Event:
        """Find an event by its UID."""
        event = next((e for e in self.list_events() if e.uid == uid), None)
        if not event:
            raise NotFoundError(detail={"resource": "event", "uid": uid})
        return event

    def find_by_poll_string(self, poll_string: str) -> Event:
        """Find an event by poll string."""
        event = next((e for e in self.list_events() if e.poll_string == poll_string), None)
        if not event:
            raise NotFoundError(detail={"resource": "event", "poll_string": poll_string})
        return event

    def find_by_poll_uid(self, poll_uid: str) -> Event:
        """Find an event by poll string."""
        event = next((e for e in self.list_events() if e.poll_uid == poll_uid), None)
        if not event:
            raise NotFoundError(detail={"resource": "event", "poll_uid": poll_uid})
        return event


class SapeurRepository:
    """CRUD for Sapeur objects."""

    def __init__(self, storage: Optional[FileStorage] = None) -> None:
        """Initialize with optional custom storage backend."""
        self.storage = storage or FileStorage()

    def list_sapeurs(self) -> List[Sapeur]:
        """Return all sapeurs."""
        df = self.storage.read_parquet(SAPEURS_FILE)
        if df.empty:
            LOGGER.debug("sapeurs_empty")
            return []
        return [Sapeur(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]

    def upsert(self, sapeur: Sapeur) -> None:
        """Insert or update a sapeur by uid."""

        def modify(df: pd.DataFrame) -> pd.DataFrame:
            sapeurs = []
            if not df.empty:
                sapeurs = [Sapeur(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]
            saps = {s.uid: s for s in sapeurs}
            if sapeur.uid in saps:
                LOGGER.debug("sapeur_exists", uid=sapeur.uid)
                return df  # Return unchanged
            saps[sapeur.uid] = sapeur
            return pd.DataFrame([s.model_dump() for s in saps.values()])

        self.storage.atomic_read_modify_write(SAPEURS_FILE, modify)

    def bulk_upsert(self, sapeurs: Iterable[Sapeur]) -> None:
        """Upsert multiple sapeurs."""

        def modify(df: pd.DataFrame) -> pd.DataFrame:
            current_sapeurs = []
            if not df.empty:
                current_sapeurs = [Sapeur(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]
            current = {s.uid: s for s in current_sapeurs}
            new_sap = False
            for sap in sapeurs:
                if sap.uid not in current:
                    current[sap.uid] = sap
                    new_sap = True
            if new_sap:
                return pd.DataFrame([s.model_dump() for s in current.values()])
            else:
                LOGGER.info("no_new_sapeurs")
                return df  # Return unchanged

        self.storage.atomic_read_modify_write(SAPEURS_FILE, modify)

    def delete(self, sapeur: Sapeur) -> None:
        """Delete a sapeur."""

        def modify(df: pd.DataFrame) -> pd.DataFrame:
            sapeurs = []
            if not df.empty:
                sapeurs = [Sapeur(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]
            saps = [s for s in sapeurs if s.uid != sapeur.uid]
            return pd.DataFrame([s.model_dump() for s in saps])

        self.storage.atomic_read_modify_write(SAPEURS_FILE, modify)

    def bulk_delete(self, sapeurs: Iterable[Sapeur]) -> None:
        """Delete multiple sapeurs."""
        for sap in self.list_sapeurs():
            if sap.uid in [s.uid for s in sapeurs]:
                self.delete(sap)

    def find_by_name(self, name: str) -> Sapeur:
        """Find a sapeur by name."""
        sapeur = next((s for s in self.list_sapeurs() if s.name == name), None)
        if not sapeur:
            raise NotFoundError(detail={"resource": "sapeur", "name": name})
        return sapeur

    def find_by_uid(self, uid: str) -> Sapeur:
        """Find by uid."""
        sapeur = next((s for s in self.list_sapeurs() if s.uid == uid), None)
        if not sapeur:
            raise NotFoundError(detail={"resource": "sapeur", "uid": uid})
        return sapeur


class VoteRepository:
    """Persistence for normalized vote records."""

    def __init__(self, storage: Optional[FileStorage] = None) -> None:
        """Initialize with optional custom storage backend."""
        self.storage = storage or FileStorage()
        self.sapeur_repository = SapeurRepository()
        self.events_repository = EventRepository()

    def create(self, overwrite: bool = False) -> None:
        """Create empty vote storage (optionally overwriting existing)."""
        df = self.storage.read_parquet(VOTES_FILE)
        if df.empty or overwrite:
            LOGGER.debug("vote_storage_create")
            columns = [evt.poll_string for evt in self.events_repository.list_events()]
            index = [sap.name for sap in self.sapeur_repository.list_sapeurs()]
            df = pd.DataFrame(columns=columns, index=index)
            self.storage.atomic_write(df, VOTES_FILE)

    def list_votes(self) -> List[VoteRecord]:
        """Return all vote rows."""
        df = self.storage.read_parquet(VOTES_FILE)
        list_vote = []
        if df.empty:
            LOGGER.debug("votes_empty")
            return []
        for poll_string in df.columns:
            event = self.events_repository.find_by_poll_string(poll_string)
            for index in df.index:
                all_sapeurs_name = [s.name for s in self.sapeur_repository.list_sapeurs()]
                if index in all_sapeurs_name:
                    sapeur = self.sapeur_repository.find_by_name(index)
                    vote_value: Optional[bool] = df.at[index, poll_string]
                    list_vote.append(VoteRecord(event=event, sapeur=sapeur, value=vote_value))
        return list_vote

    def upsert(self, vote: VoteRecord) -> None:
        """Insert or replace existing vote (unique by poll_string & voter_name)."""

        def modify(df: pd.DataFrame) -> pd.DataFrame:
            df.at[vote.sapeur.name, vote.event.poll_string] = vote.value
            return df

        self.storage.atomic_read_modify_write(VOTES_FILE, modify)

    def list_by_poll(self, evt: Event) -> List[VoteRecord]:
        """List votes for a single poll."""
        df = self.storage.read_parquet(VOTES_FILE)
        col = evt.poll_string
        if col not in df.columns:
            matched = _find_matching_column(df, evt)
            if matched:
                col = matched
            else:
                return []
        ser = df[col]
        all_sapeurs = {s.name: s for s in self.sapeur_repository.list_sapeurs()}
        list_vote = []
        for index in ser.index:
            if index in all_sapeurs:
                vote_value: Optional[bool] = ser.at[index]
                list_vote.append(VoteRecord(event=evt, sapeur=all_sapeurs[index], value=vote_value))
        return list_vote

    def count_present(self, evt: Event) -> int:
        """Count how many sapeurs voted True for a poll (no model construction)."""
        df = self.storage.read_parquet(VOTES_FILE)
        col = evt.poll_string
        if col not in df.columns:
            col = _find_matching_column(df, evt)
        if col is None or col not in df.columns:
            return 0
        return int(df[col].eq(True).sum())

    def get_vote_df(self, event_list: Optional[List[Event]] = None, sapeur_list: Optional[List[Sapeur]] = None) -> pd.DataFrame:
        """Return the vote DataFrame, optionally filtered by events and/or sapeurs."""
        df = self.storage.read_parquet(VOTES_FILE)

        if event_list:
            valid_polls = [event.poll_string for event in event_list if event.poll_string in df.columns]
            df = df[valid_polls]
        if sapeur_list:
            sapeur_names = [sapeur.name for sapeur in sapeur_list if sapeur.name in df.index]
            df = df.loc[sapeur_names]

        return df


class OnDutyRepository:
    """Persistence for on-duty assignments."""

    def __init__(self, storage: Optional[FileStorage] = None) -> None:
        """Initialize with optional custom storage backend."""
        self.storage = storage or FileStorage()
        self.events_repository = EventRepository()
        self.sapeur_repository = SapeurRepository()

    def create(self, overwrite: bool = False) -> None:
        """Create empty on_duty storage (optionally overwriting existing)."""
        df = self.storage.read_parquet(ONDUTY_FILE)
        if df.empty or overwrite:
            LOGGER.debug("onduty_storage_create")
            columns = [evt.poll_string for evt in self.events_repository.list_events()]
            index = [sap.name for sap in self.sapeur_repository.list_sapeurs()]
            df = pd.DataFrame(columns=columns, index=index).fillna(False)
            self.storage.atomic_write(df, ONDUTY_FILE)

    def list_assignments(self) -> List[OnDutyAssignment]:
        """Return all assignments."""
        df = self.storage.read_parquet(ONDUTY_FILE)
        if df.empty:
            LOGGER.debug("onduty_empty")
            return []
        retour: List[OnDutyAssignment] = []
        for poll_string in df.columns:
            assigned_names = df.index[df[poll_string].eq(True)].tolist()
            sapeurs = [self.sapeur_repository.find_by_name(n) for n in assigned_names]
            event = self.events_repository.find_by_poll_string(poll_string)
            assigned_flag = len(sapeurs) >= event.headcount
            retour.append(OnDutyAssignment(event=event, sapeur_list=sapeurs, assigned=assigned_flag))
        return retour

    def write_assignment(self, assignment: OnDutyAssignment) -> None:
        """Add an assignment (idempotent)."""

        def modify(df: pd.DataFrame) -> pd.DataFrame:
            for sap in assignment.sapeur_list:
                df.at[sap.name, assignment.event.poll_string] = assignment.assigned
            return df

        self.storage.atomic_read_modify_write(ONDUTY_FILE, modify)

    def list_assigned_sapeur(self, assignment: OnDutyAssignment) -> List[Sapeur]:
        """List all assignments for an event."""
        df = self.storage.read_parquet(ONDUTY_FILE)
        if assignment.event.poll_string not in df.columns:
            return []
        return [self.sapeur_repository.find_by_name(n) for n in df.index[df[assignment.event.poll_string].eq(True)].tolist()]

    def is_assigned(self, event: Event) -> bool:
        """Return True if headcount requirement is satisfied for the poll."""
        df = self.storage.read_parquet(ONDUTY_FILE)
        if df.empty:
            return False
        col = event.poll_string
        if col not in df.columns:
            col = _find_matching_column(df, event)
        if col is None or col not in df.columns:
            return False
        assigned_names = df.index[df[col].eq(True)].tolist()
        return len(assigned_names) >= event.headcount

    def get_onduty_df(self, event_list: Optional[List[Event]] = None, sapeur_list: Optional[List[Sapeur]] = None) -> pd.DataFrame:
        """Return the OnDuty DataFrame, optionally filtered by events and/or sapeurs."""
        df = self.storage.read_parquet(ONDUTY_FILE)

        if event_list:
            valid_polls = [event.poll_string for event in event_list if event.poll_string in df.columns]
            df = df[valid_polls]
        if sapeur_list:
            sapeur_names = [sapeur.name for sapeur in sapeur_list if sapeur.name in df.index]
            df = df.loc[sapeur_names]

        return df

    def list_sapeurs(self) -> List[Sapeur]:
        """Wrapper around sapeur repository to list all sapeurs."""
        return self.sapeur_repository.list_sapeurs()
