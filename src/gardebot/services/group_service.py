"""GroupService: group-related operations via WahaClient (composition over inheritance)."""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd  # type: ignore[import-untyped]

from gardebot.adapters.contacts import ContactAdapter
from gardebot.adapters.groups import GroupAdapter
from gardebot.common.logging_configuration import get_logger

LOGGER = get_logger(__name__)


class GroupService:
    """Encapsulates group-related WAHA interactions."""

    def __init__(self) -> None:
        """Sender: object providing send_text(to_number: str, message_text: str) and (optionally later) other message-related operations."""
        self.contact = ContactAdapter()
        self.group = GroupAdapter()

    def fetch_group_participants_table(self) -> pd.DataFrame:
        """Return DataFrame of participant contact info enriched with joined_date and group_id."""
        participants = self.group.get_group_participants()
        contact_ids = ["".join([char for char in p.get("PhoneNumber", "") if char.isnumeric()]) for p in participants]
        rows: List[Dict[str, Any]] = []
        for cid in contact_ids:
            info = self.contact.get_contact_info(contact_id=cid)
            if info:
                rows.append(info)
            else:
                LOGGER.warning("contact_info_missing", extra={"contact_id": cid})
        df = pd.DataFrame(rows)
        if not df.empty:
            df["joined_date"] = pd.Timestamp.now(tz="Europe/Zurich")
            df["group_id"] = self.group.group_id
            if "id" in df.columns:
                df.rename(columns={"id": "uid"}, inplace=True)
        return df
