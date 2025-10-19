"""CRUD repositories for domain models, backed by Parquet files."""

from __future__ import annotations

from typing import Iterable, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import configure_logging, get_logger
from gardebot.config import EVENTS_FILE, ONDUTY_FILE, SAPEURS_FILE, VOTES_FILE
from gardebot.models.domain import Event, OnDutyAssignment, Sapeur, VoteRecord
from gardebot.settings import settings
from gardebot.storage import FileStorage, ensure_columns

configure_logging(
    level=settings.logging.level,
    json_logs=bool(settings.logging.json_logs),
    color=settings.logging.color,
    timestamps=settings.logging.timestamps,
)
LOGGER = get_logger(__name__)


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
            LOGGER.debug("No events found in storage.")
            return []
        return [
            Event(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")
        ]  # TODO: deal with possibility new fields in Event which are not in df

    def upsert_event(self, event: Event) -> None:
        """Insert or update an event based on its uid."""
        events = self.list_events()
        existing = {e.uid: e for e in events}
        existing[event.uid] = event
        new_df = pd.DataFrame([e.model_dump() for e in existing.values()])
        self.storage.atomic_write(new_df, EVENTS_FILE)

    def bulk_upsert(self, events: Iterable[Event]) -> None:
        """Upsert multiple events."""
        current = {e.uid: e for e in self.list_events()}
        new_event = False
        for ev in events:
            if ev.uid not in current.keys():
                current[ev.uid] = ev
                new_event = True
        if new_event:
            df = pd.DataFrame([e.model_dump() for e in current.values()])
            self.storage.atomic_write(df, EVENTS_FILE)
        else:
            LOGGER.info("No new events to upsert.")

    def find_by_uid(self, uid: str) -> Event:
        """Find an event by its UID."""
        event = next((e for e in self.list_events() if e.uid == uid), None)
        if not event:
            raise ValueError(f"Event with uid {uid} not found")
        return event

    def find_by_poll_string(self, poll_string: str) -> Event:
        """Find an event by poll string."""
        event = next((e for e in self.list_events() if e.poll_string == poll_string), None)
        if not event:
            raise ValueError(f"Event with poll string {poll_string} not found")
        return event

    def find_by_poll_uid(self, poll_uid: str) -> Optional[Event]:
        """Find an event by poll string."""
        event = next((e for e in self.list_events() if e.poll_uid == poll_uid), None)
        if not event:
            raise ValueError(f"Event with poll uid {poll_uid} not found")
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
            LOGGER.debug("No sapeurs found in storage.")
            return []
        return [Sapeur(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]

    def upsert(self, sapeur: Sapeur) -> None:
        """Insert or update a sapeur by uid."""
        saps = {s.uid: s for s in self.list_sapeurs()}
        if sapeur.uid in saps:
            LOGGER.debug("Sapeur with uid %s already exists, skipping upsert.", sapeur.uid)
            return None
        saps[sapeur.uid] = sapeur
        df = pd.DataFrame([s.model_dump() for s in saps.values()])
        self.storage.atomic_write(df, SAPEURS_FILE)
        return None

    def bulk_upsert(self, sapeurs: Iterable[Sapeur]) -> None:
        """Upsert multiple sapeurs."""
        current = {s.uid: s for s in self.list_sapeurs()}
        new_sapeur = False
        for sap in sapeurs:
            if sap.uid not in current.keys():
                current[sap.uid] = sap
                new_sapeur = True
        if new_sapeur:
            df = pd.DataFrame([s.model_dump() for s in current.values()])
            self.storage.atomic_write(df, SAPEURS_FILE)
        else:
            LOGGER.info("No new sapeurs to upsert.")

    def delete(self, sapeur: Sapeur) -> None:
        """Delete a sapeur."""
        saps = [s for s in self.list_sapeurs() if s.uid != sapeur.uid]
        df = pd.DataFrame([s.model_dump() for s in saps])
        self.storage.atomic_write(df, SAPEURS_FILE)

    def bulk_delete(self, sapeurs: Iterable[Sapeur]) -> None:
        """Delete multiple sapeurs."""
        for sap in self.list_sapeurs():
            if sap.uid in [s.uid for s in sapeurs]:
                self.delete(sap)

    def find_by_name(self, name: str) -> Sapeur:
        """Find a sapeur by name."""
        sapeur = next((s for s in self.list_sapeurs() if s.name == name), None)
        if not sapeur:
            raise ValueError(f"Sapeur with name {name} not found")
        return sapeur

    def find_by_uid(self, uid: str) -> Sapeur:
        """Find by uid."""
        sapeur = next((s for s in self.list_sapeurs() if s.uid == uid), None)
        if not sapeur:
            raise ValueError(f"Sapeur with uid {uid} not found")
        return sapeur


class VoteRepository:
    """Persistence for normalized vote records."""

    def __init__(self, storage: Optional[FileStorage] = None) -> None:
        """Initialize with optional custom storage backend."""
        self.storage = storage or FileStorage()

    def create(self, overwrite: bool = False) -> None:
        """Create empty vote storage (optionally overwriting existing)."""
        df = self.storage.read_parquet(VOTES_FILE)
        if df.empty or overwrite:
            LOGGER.debug("Creating new vote storage at %s", VOTES_FILE)
            sapeur_repository = SapeurRepository()
            events_repository = EventRepository()
            columns = [evt.poll_string for evt in events_repository.list_events()]
            index = [sap.name for sap in sapeur_repository.list_sapeurs()]
            df = pd.DataFrame(columns=columns, index=index)
            self.storage.atomic_write(df, VOTES_FILE)

    def list_votes(self) -> List[VoteRecord]:
        """Return all vote rows."""
        df = self.storage.read_parquet(VOTES_FILE)
        if df.empty:
            LOGGER.debug("No votes found in storage.")
            return []
        ensure_columns(df, ["poll_string", "voter_name", "vote"])
        return [VoteRecord(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]

    def upsert(self, vote: VoteRecord) -> None:
        """Insert or replace existing vote (unique by poll_string & voter_name)."""
        df = self.storage.read_parquet(VOTES_FILE)
        if vote.vote is None:
            value = None
        elif vote.vote == "Présent":
            value = True
        elif vote.vote == "Absent":
            value = False
        else:
            raise ValueError(f"Invalid vote value {vote.vote}")
        df.at[vote.voter_name, vote.poll_string] = value
        self.storage.atomic_write(df, VOTES_FILE)

    def list_by_poll(self, poll_string: str) -> List[VoteRecord]:
        """List votes for a single poll."""
        return [v for v in self.list_votes() if v.poll_string == poll_string]


class OnDutyRepository:
    """Persistence for on-duty assignments."""

    def __init__(self, storage: Optional[FileStorage] = None) -> None:
        """Initialize with optional custom storage backend."""
        self.storage = storage or FileStorage()
        self.events_repository = EventRepository()
        self.sapeur_repository = SapeurRepository()

    def create(self, overwrite: bool = False) -> None:
        """Create empty vote storage (optionally overwriting existing)."""
        df = self.storage.read_parquet(ONDUTY_FILE)
        if df.empty or overwrite:
            LOGGER.debug("Creating new on-duty storage at %s", ONDUTY_FILE)
            columns = [evt.poll_string for evt in self.events_repository.list_events()]
            index = [sap.name for sap in self.sapeur_repository.list_sapeurs()]
            df = pd.DataFrame(columns=columns, index=index)
            self.storage.atomic_write(df, ONDUTY_FILE)

    def list_assignments(self) -> List[OnDutyAssignment]:
        """Return all on-duty rows."""
        df = self.storage.read_parquet(ONDUTY_FILE)
        if df.empty:
            LOGGER.debug("No on-duty assignments found in storage.")
            return []
        retour: List[OnDutyAssignment] = []
        for poll_string in df.columns:
            sapeurs = [self.sapeur_repository.find_by_name(sap_name) for sap_name in df.index[df[poll_string].eq(True)].tolist()]
            event = self.events_repository.find_by_poll_string(poll_string)
            assigned = len(sapeurs) >= event.headcount
            retour.append(OnDutyAssignment(event=event, sapeur_list=sapeurs, assigned=assigned))
        return retour

    def write_assignment(self, assignment: OnDutyAssignment) -> None:
        """Add an assignment (idempotent)."""
        df = self.storage.read_parquet(ONDUTY_FILE)
        for sap in assignment.sapeur_list:
            df.at[sap.name, assignment.event.poll_string] = True
        self.storage.atomic_write(df, ONDUTY_FILE)

    def list_for_poll(self, poll_string: str) -> List[Sapeur]:
        """List all assignments for a poll."""
        df = self.storage.read_parquet(ONDUTY_FILE)
        return [self.sapeur_repository.find_by_name(sap_name) for sap_name in df.index[df[poll_string].eq(True)].tolist()]

    def is_assigned(self, poll_string: str) -> bool:
        """Return True if the right number of person is assigned to the poll."""
        df = self.storage.read_parquet(ONDUTY_FILE)
        sapeurs = df.index[df[poll_string].eq(True)].tolist()
        return len(sapeurs) != 0
