"""CRUD repositories for domain models, backed by Parquet files."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.common.storage import FileStorage
from gardebot.config import EVENTS_FILE, ONDUTY_FILE, SAPEURS_FILE, VOTES_FILE
from gardebot.errors import NotFoundError
from gardebot.models.domain import Event, OnDutyAssignment, Sapeur, VoteRecord

LOGGER = get_logger(__name__)


def _clean_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Replace float NaN values with None so Pydantic validators receive None for optional fields.

    In pandas 3.x, a column containing a mix of None and string values uses the
    ``str`` dtype, where None is stored as ``float('nan')``.  When that value is
    passed to a Pydantic ``Optional[str]`` field it triggers a validation error.
    This helper converts those float NaN values back to ``None`` before the dict
    is unpacked into a model constructor.
    """
    return {str(k): (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}


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
            Event(**_clean_row(row)) for row in df.to_dict(orient="records")
        ]  # TODO: deal with possibility new fields in Event which are not in df

    def upsert_event(self, event: Event) -> None:
        """Insert or update an event based on its uid."""

        def modify(df: pd.DataFrame) -> pd.DataFrame:
            events = []
            if not df.empty:
                events = [Event(**_clean_row(row)) for row in df.to_dict(orient="records")]
            existing = {e.uid: e for e in events}
            existing[event.uid] = event
            return pd.DataFrame([e.model_dump() for e in existing.values()])

        self.storage.force_atomic_read_modify_write(EVENTS_FILE, modify)

    def bulk_upsert(self, events: Iterable[Event]) -> None:
        """Upsert multiple events."""
        import re
        from collections import defaultdict

        def _base_name(title: str) -> str:
            return re.sub(r"\s+\d+$", "", title).strip()

        def _score(e: Event) -> tuple:
            return (
                e.ical_uid is not None,
                e.poll_uid is not None,
                e.published_date is not None and not pd.isna(e.published_date),
                e.nb_reminder or 0,
            )

        def modify(df: pd.DataFrame) -> pd.DataFrame:
            current_events = []
            if not df.empty:
                current_events = [Event(**_clean_row(row)) for row in df.to_dict(orient="records")]
            current = {e.uid: e for e in current_events}
            changed = False

            # ══════════ PHASE 0: Deduplicate existing rows ══════════
            nk_groups: defaultdict[tuple, list[str]] = defaultdict(list)
            for e in current_events:
                nk = (str(e.start_date), str(e.end_date), e.location, _base_name(e.title))
                nk_groups[nk].append(e.uid)

            for nk, uids in nk_groups.items():
                if len(uids) <= 1:
                    continue
                group = [current[u] for u in uids if u in current]
                if len(group) <= 1:
                    continue
                best = max(group, key=_score)
                for other in group:
                    if other.uid == best.uid:
                        continue
                    updates = {}
                    if not best.poll_uid and other.poll_uid:
                        updates["poll_uid"] = other.poll_uid
                    if (best.published_date is None or pd.isna(best.published_date)) and (
                        other.published_date is not None and not pd.isna(other.published_date)
                    ):
                        updates["published_date"] = other.published_date
                    if (best.nb_reminder or 0) < (other.nb_reminder or 0):
                        updates["nb_reminder"] = other.nb_reminder
                    if updates:
                        best = best.model_copy(update=updates)
                    current.pop(other.uid, None)
                    changed = True
                current[best.uid] = best

            # Rebuild index after Phase 0 dedup
            legacy_index: defaultdict[tuple, list[str]] = defaultdict(list)
            for e in current.values():
                nk = (str(e.start_date), str(e.end_date), e.location, _base_name(e.title))
                legacy_index[nk].append(e.uid)

            # ══════════ PHASE 1: Process incoming events ══════════
            for ev in events:
                nk = (str(ev.start_date), str(ev.end_date), ev.location, _base_name(ev.title))
                existing_uids = legacy_index.get(nk, [])

                stale_uids = [uid for uid in existing_uids if uid != ev.uid and uid in current]
                if stale_uids:
                    stale_events = [current[uid] for uid in stale_uids]
                    best_stale = max(stale_events, key=_score)
                    for uid in stale_uids:
                        current.pop(uid, None)
                    changed = True

                    if ev.uid in current:
                        canonical = current[ev.uid]
                        updates = {}
                        if not canonical.poll_uid and best_stale.poll_uid:
                            updates["poll_uid"] = best_stale.poll_uid
                        if (canonical.published_date is None or pd.isna(canonical.published_date)) and (
                            best_stale.published_date is not None and not pd.isna(best_stale.published_date)
                        ):
                            updates["published_date"] = best_stale.published_date
                        if (canonical.nb_reminder or 0) < (best_stale.nb_reminder or 0):
                            updates["nb_reminder"] = best_stale.nb_reminder
                        if updates:
                            current[ev.uid] = canonical.model_copy(update=updates)
                        continue
                    else:
                        current[ev.uid] = ev.model_copy(update={
                            "poll_uid": best_stale.poll_uid,
                            "published_date": best_stale.published_date,
                            "nb_reminder": best_stale.nb_reminder,
                            "scheduled_publication_date": best_stale.scheduled_publication_date,
                        })
                        continue

                if ev.uid in current:
                    continue

                current[ev.uid] = ev
                changed = True

            if changed:
                return pd.DataFrame([e.model_dump() for e in current.values()])
            LOGGER.info("no_new_events")
            return df

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
        ser = df[evt.poll_string]
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
        if evt.poll_string not in df.columns:
            return 0
        return int(df[evt.poll_string].eq(True).sum())

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
        if df.empty or event.poll_string not in df.columns:
            return False
        assigned_names = df.index[df[event.poll_string].eq(True)].tolist()
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
