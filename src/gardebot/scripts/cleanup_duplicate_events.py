"""One-time cleanup script to deduplicate events in the events.parquet table.

Groups rows by (start_date, end_date, location) — the natural key for an event occurrence —
and for each group with duplicates, keeps the row with the most metadata
(non-null poll_uid preferred, then highest nb_reminder).

Run with:
    python -m gardebot.scripts.cleanup_duplicate_events
"""

from __future__ import annotations

import sys
from typing import Optional

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.common.storage import FileStorage
from gardebot.config import EVENTS_FILE

LOGGER = get_logger(__name__)


def cleanup_duplicate_events(storage: Optional[FileStorage] = None) -> int:
    """Deduplicate events.parquet by (start_date, end_date, location).

    Args:
        storage: Optional FileStorage instance. Defaults to a new FileStorage.

    Returns:
        Number of duplicate rows removed.
    """
    store = storage or FileStorage()
    df = store.read_parquet(EVENTS_FILE)

    if df.empty:
        LOGGER.info("cleanup_duplicate_events_empty_table")
        return 0

    LOGGER.info("cleanup_duplicate_events_start", total_rows=len(df))

    natural_key = ["start_date", "end_date", "location"]
    # Check that required columns are present
    for col in natural_key:
        if col not in df.columns:
            LOGGER.error("cleanup_duplicate_events_missing_column", column=col)
            return 0

    # Score each row: (has_poll_uid, nb_reminder)
    df = df.copy()
    df["_score_poll"] = df["poll_uid"].notna().astype(int) if "poll_uid" in df.columns else 0
    df["_score_reminder"] = df.get("nb_reminder", pd.Series(0, index=df.index)).fillna(0).astype(int)

    # Sort so the best row comes last (we keep last within each group)
    df_sorted = df.sort_values(by=["_score_poll", "_score_reminder"], ascending=[True, True])

    # Keep last (highest score) per natural key
    df_dedup = df_sorted.drop_duplicates(subset=natural_key, keep="last")

    # Drop helper columns
    df_dedup = df_dedup.drop(columns=["_score_poll", "_score_reminder"])

    removed = len(df) - len(df_dedup)

    if removed == 0:
        LOGGER.info("cleanup_duplicate_events_no_duplicates_found")
        return 0

    LOGGER.info("cleanup_duplicate_events_duplicates_found", removed=removed, kept=len(df_dedup))

    # Log which rows were dropped
    kept_index = df_dedup.index
    dropped_df = df.loc[~df.index.isin(kept_index), natural_key + ["uid"] if "uid" in df.columns else natural_key]
    for _, row in dropped_df.iterrows():
        LOGGER.info("cleanup_duplicate_events_row_dropped", start_date=str(row.get("start_date")), end_date=str(row.get("end_date")), location=str(row.get("location")), uid=str(row.get("uid", "N/A")))

    store.atomic_write(df_dedup, EVENTS_FILE)
    LOGGER.info("cleanup_duplicate_events_done", removed=removed, remaining=len(df_dedup))
    return removed


if __name__ == "__main__":
    removed = cleanup_duplicate_events()
    sys.exit(0 if removed >= 0 else 1)
