"""One-time cleanup script: deduplicate events.parquet on Kdrive.

Groups rows by (start_date, end_date, location) and keeps the row with the most
metadata (ical_uid set > poll_uid set > published_date set > nb_reminder).

Run with:
    python -m gardebot.scripts.cleanup_duplicate_events
"""

from __future__ import annotations

from typing import List

import pandas as pd  # type: ignore[import-untyped]

from gardebot.common.logging_configuration import get_logger
from gardebot.common.storage import FileStorage
from gardebot.config import EVENTS_FILE
from gardebot.models.domain import Event

LOGGER = get_logger(__name__)


def deduplicate(events: List[Event]) -> List[Event]:
    """Return the deduplicated list of events, keeping one canonical row per slot.

    Groups by (start_date, end_date, location).  Within each group the best row
    is selected based on descending priority:
      1. ical_uid is set
      2. poll_uid is set
      3. published_date is set (and not NaT)
      4. nb_reminder (highest wins)
    """
    from collections import defaultdict

    groups: defaultdict[tuple, list] = defaultdict(list)
    for e in events:
        key = (str(e.start_date), str(e.end_date), e.location)
        groups[key].append(e)

    result: List[Event] = []
    for key, group in groups.items():
        if len(group) == 1:
            result.append(group[0])
            continue
        best = max(
            group,
            key=lambda e: (
                e.ical_uid is not None,
                e.poll_uid is not None,
                e.published_date is not None and not pd.isna(e.published_date),
                e.nb_reminder or 0,
            ),
        )
        dropped = [e for e in group if e.uid != best.uid]
        for d in dropped:
            LOGGER.info("cleanup_drop_duplicate", dropped_title=d.title, dropped_uid=d.uid, kept_title=best.title, kept_uid=best.uid)
        result.append(best)
    return result


def main() -> None:
    """Entry point: read, deduplicate, and write back events.parquet."""
    storage = FileStorage()
    df = storage.read_parquet(EVENTS_FILE)
    if df.empty:
        LOGGER.info("cleanup_no_events")
        return
    events = [Event(**{str(k): v for k, v in row.items()}) for row in df.to_dict(orient="records")]
    before = len(events)
    clean = deduplicate(events)
    after = len(clean)
    LOGGER.info("cleanup_summary", before=before, after=after, removed=before - after)
    if before != after:
        out_df = pd.DataFrame([e.model_dump() for e in clean])
        storage.atomic_write(out_df, EVENTS_FILE)
        LOGGER.info("cleanup_written", rows=after)
    else:
        LOGGER.info("cleanup_no_duplicates_found")


if __name__ == "__main__":
    main()
