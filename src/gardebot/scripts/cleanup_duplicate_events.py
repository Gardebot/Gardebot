"""Script to deduplicate events in the events parquet storage."""

from __future__ import annotations

import re
from typing import List

import pandas as pd  # type: ignore[import-untyped]

from gardebot.models.domain import Event


def _base_name(title: str) -> str:
    """Strip trailing numeric suffix: 'Piquet de Pâques 5' → 'Piquet de Pâques'."""
    return re.sub(r"\s+\d+$", "", title).strip()


def _score(e: Event) -> tuple:
    """Score an event by richness of metadata (higher is better)."""
    return (
        e.ical_uid is not None,
        e.poll_uid is not None,
        e.published_date is not None and not pd.isna(e.published_date),
        e.nb_reminder or 0,
    )


def deduplicate(events: List[Event]) -> List[Event]:
    """Deduplicate a list of events by natural key, keeping the best-scored row.

    Natural key: (start_date, end_date, location, base_name(title)).
    Metadata from dropped duplicates is merged into the surviving row.

    Args:
        events: List of Event objects to deduplicate.

    Returns:
        Deduplicated list of Event objects.
    """
    from collections import defaultdict

    groups: defaultdict[tuple, list[Event]] = defaultdict(list)
    for e in events:
        nk = (str(e.start_date), str(e.end_date), e.location, _base_name(e.title))
        groups[nk].append(e)

    result: List[Event] = []
    for group in groups.values():
        if len(group) == 1:
            result.append(group[0])
            continue

        best = max(group, key=_score)
        for other in group:
            if other.uid == best.uid:
                continue
            updates = {}
            if not best.poll_uid and other.poll_uid:
                updates["poll_uid"] = other.poll_uid
            if (best.published_date is None or pd.isna(best.published_date)) and (
                other.published_date is not None and not pd.isna(other.published_date)
            ):
                updates["published_date"] = other.published_date
            if (best.nb_reminder or 0) < (other.nb_reminder or 0):
                updates["nb_reminder"] = other.nb_reminder
            if updates:
                best = best.model_copy(update=updates)
        result.append(best)

    return result
