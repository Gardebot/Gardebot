"""High-level sapeur logic (fetch, enrich, etc.)."""

from __future__ import annotations

from typing import List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.models.domain import Sapeur
from gardebot.repositories import SapeurRepository
from gardebot.services.group_service import GroupService

LOGGER = get_logger(__name__)


class SapeurService:
    """High-level sapeur logic (fetch, enrich, etc.)."""

    def __init__(self, repository: Optional[SapeurRepository] = None) -> None:
        """Initialize with optional custom repository."""
        self.repo = repository or SapeurRepository()
        self.group_service = GroupService()

    def synchronize_sapeurs(self) -> None:
        """Single fetch used for both insert and delete to avoid duplicate remote calls."""
        group_member_df = self.group_service.fetch_group_participants_table()
        self._insert_active_sapeurs(group_member_df)
        self._delete_sapeur_who_quit(group_member_df)

    def _insert_active_sapeurs(self, group_member_df: pd.DataFrame) -> List[Sapeur]:
        """Insert or update active sapeurs from group member DataFrame."""
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

    def _delete_sapeur_who_quit(self, group_member_df: pd.DataFrame) -> None:
        """Delete sapeurs who have left the group."""
        current_sapeur_uid = group_member_df["uid"].to_list()
        sapeurs_who_quit = [sap for sap in self.repo.list_sapeurs() if sap.uid not in current_sapeur_uid]
        for sapeur in sapeurs_who_quit:
            LOGGER.info("deleting_sapeur", name=sapeur.name)
            self.repo.delete(sapeur)
