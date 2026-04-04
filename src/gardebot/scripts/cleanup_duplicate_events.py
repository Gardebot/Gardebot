"""One-off script to deduplicate events.parquet on Kdrive.

Groups events by natural key (start_date, end_date, location).
For each group with more than one row, keeps the row with the most
metadata (ical_uid set > poll_uid set > published_date set > nb_reminder),
then writes the result back to Kdrive.

Run with:
    python -m gardebot.scripts.cleanup_duplicate_events
"""

from __future__ import annotations

from typing import List

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import configure_logging, get_logger
from gardebot.common.storage import FileStorage
from gardebot.config import EVENTS_FILE
from gardebot.models.domain import Event

LOGGER = get_logger(__name__)


def _score(event: Event) -> tuple:
    """Return a sortable score tuple — higher is better."""
    return (
        event.ical_uid is not None,
        event.poll_uid is not None,
        event.published_date is not None and not pd.isna(event.published_date),
        event.nb_reminder or 0,
    )


def deduplicate(events: List[Event]) -> List[Event]:
    """Return a deduplicated list, keeping the best row per natural key."""
    from collections import defaultdict

    groups: defaultdict[tuple, List[Event]] = defaultdict(list)
    for e in events:
        natural_key = (str(e.start_date), str(e.end_date), e.location)
        groups[natural_key].append(e)

    kept: List[Event] = []
    for natural_key, group in groups.items():
        if len(group) == 1:
            kept.append(group[0])
            continue

        best = max(group, key=_score)
        dropped_uids = [e.uid for e in group if e.uid != best.uid]
        LOGGER.info(
            "deduplicating_events",
            natural_key=natural_key,
            kept_uid=best.uid,
            kept_title=best.title,
            dropped_uids=dropped_uids,
        )
        kept.append(best)

    return kept


def main() -> None:
    """Read events from Kdrive, deduplicate, and write back."""
    configure_logging()
    storage = FileStorage()

    LOGGER.info("cleanup_start", file=EVENTS_FILE)
    df = storage.read_parquet(EVENTS_FILE)
    if df.empty:
        LOGGER.info("cleanup_no_events")
        return

    events = [Event(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]
    LOGGER.info("cleanup_read", total=len(events))

    clean_events = deduplicate(events)
    removed = len(events) - len(clean_events)
    LOGGER.info("cleanup_deduplicated", kept=len(clean_events), removed=removed)

    if removed == 0:
        LOGGER.info("cleanup_nothing_to_do")
        return

    clean_df = pd.DataFrame([e.model_dump() for e in clean_events])
    storage.atomic_write(clean_df, EVENTS_FILE)
    LOGGER.info("cleanup_done", rows_written=len(clean_df))


if __name__ == "__main__":
    main()
