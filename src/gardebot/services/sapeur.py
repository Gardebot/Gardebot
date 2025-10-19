"""High-level sapeur logic (fetch, enrich, etc.)."""

from __future__ import annotations

import logging
from typing import List, Optional

from gardebot.adapters.groups import GroupAdapter
from gardebot.models.domain import Sapeur
from gardebot.repositories import SapeurRepository

LOGGER = logging.getLogger(__name__)


class SapeurService:
    """High-level sapeur logic (fetch, enrich, etc.)."""

    def __init__(self, repository: Optional[SapeurRepository] = None) -> None:
        """Initialize with optional custom repository."""
        self.repo = repository or SapeurRepository()
        self.group_adapter = GroupAdapter()

    def synchronize_sapeurs(self) -> None:
        """Insert active sapeurs and remove those who quit."""
        self.insert_active_sapeurs()
        self.delete_sapeur_who_quit()

    def insert_active_sapeurs(self) -> List[Sapeur]:
        """Sync active sapeurs from group and upsert into repository (idempotent)."""
        group_member_df = self.group_adapter.fetch_group_participants_table()
        sapeurs: List[Sapeur] = []
        for _, row in group_member_df.iterrows():
            sapeur = Sapeur(
                name=row["name"],
                phone=row["phone"],
                uid=row["uid"],
                joined_date=row["joined_date"],
                pushname=row["pushname"],
                group_id=row["group_id"],
            )
            sapeurs.append(sapeur)
        self.repo.bulk_upsert(sapeurs)
        return sapeurs

    def delete_sapeur_who_quit(self) -> None:
        """Delete sapeur who has left the group."""
        group_member_df = self.group_adapter.fetch_group_participants_table()
        current_sapeur_uid = group_member_df["uid"].to_list()
        sapeurs_who_quit = [sap for sap in self.repo.list_sapeurs() if sap.uid not in current_sapeur_uid]
        for sapeur in sapeurs_who_quit:
            LOGGER.info("Deleting sapeur who quit: %s", sapeur.name)
            self.repo.delete(sapeur)
