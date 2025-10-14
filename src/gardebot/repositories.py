"""CRUD repositories for domain models, backed by Parquet files."""

from __future__ import annotations

from typing import Iterable, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.models.domain import Event, OnDutyAssignment, Sapeur, VoteRecord
from gardebot.storage import FileStorage, ensure_columns

# Filenames
EVENTS_FILE = "events"
SAPEURS_FILE = "sapeurs"
VOTES_FILE = "votes"
ONDUTY_FILE = "on_duty"


class EventRepository:
    """CRUD operations for Event objects."""

    def __init__(self, storage: Optional[FileStorage] = None) -> None:
        """Initialize with optional custom storage backend."""
        self.storage = storage or FileStorage()

    def list_events(self) -> List[Event]:
        """Return all stored events."""
        df = self.storage.read_parquet(EVENTS_FILE)
        if df.empty:
            return []
        return [Event(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]

    def upsert_event(self, event: Event) -> None:
        """Insert or update an event based on its uid."""
        events = self.list_events()
        existing = {e.uid: e for e in events}
        existing[event.uid] = event
        new_df = pd.DataFrame([e.dict() for e in existing.values()])
        self.storage.atomic_write(new_df, EVENTS_FILE)

    def bulk_upsert(self, events: Iterable[Event]) -> None:
        """Upsert multiple events."""
        current = {e.uid: e for e in self.list_events()}
        for ev in events:
            current[ev.uid] = ev
        df = pd.DataFrame([e.dict() for e in current.values()])
        self.storage.atomic_write(df, EVENTS_FILE)

    def find_by_uid(self, uid: str) -> Optional[Event]:
        """Find an event by its UID."""
        return next((e for e in self.list_events() if e.uid == uid), None)

    def find_by_poll_string(self, poll_string: str) -> Optional[Event]:
        """Find an event by poll string."""
        return next((e for e in self.list_events() if e.poll_string == poll_string), None)


class SapeurRepository:
    """CRUD for Sapeur objects."""

    def __init__(self, storage: Optional[FileStorage] = None) -> None:
        """Initialize with optional custom storage backend."""
        self.storage = storage or FileStorage()

    def list_sapeurs(self) -> List[Sapeur]:
        """Return all sapeurs."""
        df = self.storage.read_parquet(SAPEURS_FILE)
        if df.empty:
            return []
        return [Sapeur(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]

    def upsert(self, sapeur: Sapeur) -> None:
        """Insert or update a sapeur by uid."""
        saps = {s.uid: s for s in self.list_sapeurs()}
        saps[sapeur.uid] = sapeur
        df = pd.DataFrame([s.dict() for s in saps.values()])
        self.storage.atomic_write(df, SAPEURS_FILE)

    def find_by_name(self, name: str) -> Optional[Sapeur]:
        """Find a sapeur by name."""
        return next((s for s in self.list_sapeurs() if s.name == name), None)

    def find_by_uid(self, uid: str) -> Optional[Sapeur]:
        """Find by uid."""
        return next((s for s in self.list_sapeurs() if s.uid == uid), None)


class VoteRepository:
    """Persistence for normalized vote records."""

    def __init__(self, storage: Optional[FileStorage] = None) -> None:
        """Initialize with optional custom storage backend."""
        self.storage = storage or FileStorage()

    def list_votes(self) -> List[VoteRecord]:
        """Return all vote rows."""
        df = self.storage.read_parquet(VOTES_FILE)
        if df.empty:
            return []
        ensure_columns(df, ["poll_string", "voter_name", "vote"])
        return [VoteRecord(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]

    def upsert(self, vote: VoteRecord) -> None:
        """Insert or replace existing vote (unique by poll_string & voter_name)."""
        votes = {(v.poll_string, v.voter_name): v for v in self.list_votes()}
        votes[(vote.poll_string, vote.voter_name)] = vote
        df = pd.DataFrame([v.dict() for v in votes.values()])
        self.storage.atomic_write(df, VOTES_FILE)

    def list_by_poll(self, poll_string: str) -> List[VoteRecord]:
        """List votes for a single poll."""
        return [v for v in self.list_votes() if v.poll_string == poll_string]


class OnDutyRepository:
    """Persistence for on-duty assignments."""

    def __init__(self, storage: Optional[FileStorage] = None) -> None:
        """Initialize with optional custom storage backend."""
        self.storage = storage or FileStorage()

    def list_assignments(self) -> List[OnDutyAssignment]:
        """Return all on-duty rows."""
        df = self.storage.read_parquet(ONDUTY_FILE)
        if df.empty:
            return []
        ensure_columns(df, ["poll_string", "sapeur_name", "assigned"])
        return [OnDutyAssignment(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]

    def add_assignment(self, assignment: OnDutyAssignment) -> None:
        """Add an assignment (idempotent)."""
        existing = {(a.poll_string, a.sapeur_name): a for a in self.list_assignments()}
        existing[(assignment.poll_string, assignment.sapeur_name)] = assignment
        df = pd.DataFrame([a.dict() for a in existing.values()])
        self.storage.atomic_write(df, ONDUTY_FILE)

    def list_for_poll(self, poll_string: str) -> List[OnDutyAssignment]:
        """List all assignments for a poll."""
        return [a for a in self.list_assignments() if a.poll_string == poll_string]

    def is_assigned(self, poll_string: str) -> bool:
        """Return True if at least one person is assigned to the poll."""
        return any(a.poll_string == poll_string for a in self.list_assignments())


# Optional backwards compatibility (remove after refactor complete)
class DEPRECATED:  # noqa: N801
    """Namespace for deprecated shim helpers mapping old paradigm to new repository layer."""

    @staticmethod
    def get_garde_by_pollstring(poll_string: str, repo: Optional[EventRepository] = None) -> Event:
        """Shim for EventManager.get_garde_by_pollstring."""
        er = repo or EventRepository()
        evt = er.find_by_poll_string(poll_string)
        if not evt:
            raise ValueError(f"Event with poll_string {poll_string} not found.")
        return evt
