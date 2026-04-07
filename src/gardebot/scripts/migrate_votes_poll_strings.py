"""Migration script: merge fragmented vote columns in votes.parquet.

After calendar sync renamed events (removing numeric suffixes like "Piquet de Pâques 5"
→ "Piquet de Pâques"), publish_polls published new polls under new names, creating
**duplicate columns** in votes.parquet across multiple generations:

  - 1st gen:  "Piquet de Pâques 7 : dimanche 5 avril..."  (old suffixed, has real votes)
  - 2nd gen:  "Piquet de Pâques 5 : dimanche 5 avril..."  (old suffixed, has real votes)
  - 3rd gen:  "Piquet de Pâques : dimanche 5 avril..."    (current name, nearly empty)

This script:
  1. Reads votes.parquet from KDrive
  2. Reads events.parquet to get current event poll_strings
  3. For each current event, finds ALL columns in votes.parquet matching on the
     date+location suffix (everything after " : ")
  4. Merges those columns with priority: True > False > NaN
  5. Renames the merged result to the current event poll_string
  6. Removes old duplicate columns
  7. Writes back to KDrive

Run with:
    python -m gardebot.scripts.migrate_votes_poll_strings
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.common.storage import FileStorage
from gardebot.config import EVENTS_FILE, VOTES_FILE
from gardebot.models.domain import Event

LOGGER = get_logger(__name__)


def _date_location_suffix(poll_string: str) -> Optional[str]:
    """Return the date+location part (everything after ' : ') of a poll_string, or None."""
    if " : " not in poll_string:
        return None
    return poll_string.split(" : ", 1)[1]


def _merge_bool_series(series_list: List[pd.Series]) -> pd.Series:
    """OR-merge a list of boolean Series: True > False > NaN.

    A row is True if ANY series has True; False if any has False (and none True);
    NaN if all are NaN.
    """
    if not series_list:
        raise ValueError("series_list must not be empty")

    def _or_merge(a: object, b: object) -> object:
        if pd.notna(a) and bool(a):
            return True
        if pd.notna(b) and bool(b):
            return True
        return a if pd.notna(a) else b

    result = series_list[0].copy()
    for ser in series_list[1:]:
        result = result.combine(ser, _or_merge)
    return result


def migrate_votes_dataframe(df: pd.DataFrame, events: List[Event]) -> pd.DataFrame:
    """Merge all historical column generations for each event into the current poll_string.

    For each event, finds ALL df columns that share the same date+location suffix,
    OR-merges them (True > False > NaN), and renames the result to event.poll_string.
    Columns that don't match any current event are left untouched.

    Returns a new DataFrame if any changes were made, or the original df object if nothing
    changed.
    """
    if df.empty:
        return df

    result = df.copy()
    changed = False

    for evt in events:
        current_col = evt.poll_string
        suffix = _date_location_suffix(current_col)
        if suffix is None:
            continue

        # Find ALL columns in the current result that share this suffix
        matching = [col for col in result.columns if " : " in col and col.split(" : ", 1)[1] == suffix]

        if not matching:
            LOGGER.info("migrate_votes_no_match", poll_string=current_col)
            continue

        if matching == [current_col]:
            # Already exactly right — nothing to do
            continue

        # Separate the current-name column (if it exists) from old-name columns
        old_cols = [c for c in matching if c != current_col]
        has_current = current_col in matching

        if not old_cols:
            # Only the current column exists — already clean
            continue

        LOGGER.info("migrate_votes_merging", current_col=current_col, old_cols=old_cols, has_current=has_current)

        # Build the merged series from all matching columns
        all_cols = ([current_col] if has_current else []) + old_cols
        series_list = [result[c] for c in all_cols]
        merged = _merge_bool_series(series_list)

        # Drop all matched columns, then add the merged one under the current name
        result = result.drop(columns=matching)
        result[current_col] = merged
        changed = True

    return result if changed else df


def main() -> None:
    """Entry point: migrate fragmented vote columns in votes.parquet."""
    storage = FileStorage()

    events_df = storage.read_parquet(EVENTS_FILE)
    if events_df.empty:
        LOGGER.info("migrate_votes_no_events")
        return
    events = [Event(**{str(k): v for k, v in row.items()}) for row in events_df.to_dict(orient="records")]

    votes_df = storage.read_parquet(VOTES_FILE)
    if votes_df.empty:
        LOGGER.info("migrate_votes_file_empty")
        return

    LOGGER.info("migrate_votes_start", cols_before=len(votes_df.columns))
    migrated = migrate_votes_dataframe(votes_df, events)

    if migrated is not votes_df:
        storage.atomic_write(migrated, VOTES_FILE)
        LOGGER.info("migrate_votes_written", cols_before=len(votes_df.columns), cols_after=len(migrated.columns))
    else:
        LOGGER.info("migrate_votes_unchanged")


if __name__ == "__main__":
    main()
