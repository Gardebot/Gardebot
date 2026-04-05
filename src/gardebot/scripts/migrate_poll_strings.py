"""Migration script: rename old suffixed poll_string columns in votes.parquet and on_duty.parquet.

After the ical_uid fix, events no longer have numeric title suffixes (e.g. "Piquet de Pâques 5"
→ "Piquet de Pâques"), so the poll_string columns in votes/on_duty no longer match the current
event poll_strings.  This script renames those columns using a suffix-based match and merges
data when multiple old columns map to the same current poll_string.

Run with:
    python -m gardebot.scripts.migrate_poll_strings
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.common.storage import FileStorage
from gardebot.config import EVENTS_FILE, ONDUTY_FILE, VOTES_FILE
from gardebot.models.domain import Event

LOGGER = get_logger(__name__)


def _or_merge_bool(a: object, b: object) -> object:
    """OR-merge two nullable boolean values: True > False > NaN."""
    if pd.notna(a) and bool(a):
        return True
    if pd.notna(b) and bool(b):
        return True
    return a if pd.notna(a) else b


def _date_location_suffix(poll_string: str) -> Optional[str]:
    """Return the date+location part (everything after ' : ') of a poll_string, or None."""
    if " : " not in poll_string:
        return None
    return poll_string.split(" : ", 1)[1]


def _build_old_variants(event: Event, max_suffix: int = 20) -> List[str]:
    """Return all historical poll_string variants for an event (unsuffixed + suffixed titles)."""
    base_title = event.title
    variants = [event.poll_string]  # current (no suffix)
    for n in range(2, max_suffix + 1):
        suffixed = event.model_copy(update={"title": f"{base_title} {n}"})
        variants.append(suffixed.poll_string)
    return variants


def _build_rename_mapping(events: List[Event]) -> Dict[str, str]:
    """Build {old_poll_string: current_poll_string} mapping for all events."""
    mapping: Dict[str, str] = {}
    for evt in events:
        current = evt.poll_string
        for old in _build_old_variants(evt):
            if old != current and old not in mapping:
                mapping[old] = current
    return mapping


def migrate_dataframe(df: pd.DataFrame, rename_map: Dict[str, str], current_poll_strings: List[str]) -> pd.DataFrame:
    """Rename/merge old columns in df according to rename_map.

    When multiple old columns map to the same new column, their boolean data is merged
    with OR logic (True wins over False, non-null wins over null).
    """
    if df.empty:
        return df

    # Identify columns needing rename
    to_rename = {col: rename_map[col] for col in df.columns if col in rename_map}
    if not to_rename:
        return df

    # Group old columns that map to the same new column name
    merge_groups: Dict[str, List[str]] = {}
    for old_col, new_col in to_rename.items():
        merge_groups.setdefault(new_col, []).append(old_col)

    result = df.copy()
    for new_col, old_cols in merge_groups.items():
        if new_col in result.columns:
            # New column already exists; merge old columns into it
            for old_col in old_cols:
                existing = result[new_col]
                incoming = result[old_col]
                # OR merge: True wins over False/None; non-null wins over null
                merged = existing.combine(incoming, _or_merge_bool)
                result[new_col] = merged
                LOGGER.info("migrate_merge_column", old_col=old_col, new_col=new_col)
                result = result.drop(columns=[old_col])
        elif len(old_cols) == 1:
            # Simple rename
            LOGGER.info("migrate_rename_column", old_col=old_cols[0], new_col=new_col)
            result = result.rename(columns={old_cols[0]: new_col})
        else:
            # Multiple old cols, no existing new col — merge into first then rename
            base_col = old_cols[0]
            for old_col in old_cols[1:]:
                existing = result[base_col]
                incoming = result[old_col]
                merged = existing.combine(incoming, _or_merge_bool)
                result[base_col] = merged
                LOGGER.info("migrate_merge_column", old_col=old_col, new_col=new_col)
                result = result.drop(columns=[old_col])
            LOGGER.info("migrate_rename_column", old_col=base_col, new_col=new_col)
            result = result.rename(columns={base_col: new_col})

    return result


def main() -> None:
    """Entry point: migrate poll_string columns in votes and on_duty parquet files."""
    storage = FileStorage()
    events_df = storage.read_parquet(EVENTS_FILE)
    if events_df.empty:
        LOGGER.info("migrate_no_events")
        return
    events = [Event(**{str(k): v for k, v in row.items()}) for row in events_df.to_dict(orient="records")]
    current_poll_strings = [e.poll_string for e in events]
    rename_map = _build_rename_mapping(events)
    LOGGER.info("migrate_rename_map_size", size=len(rename_map))

    for filename in (VOTES_FILE, ONDUTY_FILE):
        df = storage.read_parquet(filename)
        if df.empty:
            LOGGER.info("migrate_file_empty", filename=filename)
            continue
        migrated = migrate_dataframe(df, rename_map, current_poll_strings)
        if migrated is not df:
            storage.atomic_write(migrated, filename)
            LOGGER.info("migrate_file_written", filename=filename, cols_before=len(df.columns), cols_after=len(migrated.columns))
        else:
            LOGGER.info("migrate_file_unchanged", filename=filename)


if __name__ == "__main__":
    main()
