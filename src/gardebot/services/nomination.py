"""Nomination logic service."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd  # type: ignore[import-untyped]

from gardebot.config import MARGIN_NOMINATION
from gardebot.repositories import OnDutyRepository, VoteRepository


class NominationService:
    """Implements nomination logic based on participation ratios & responses."""

    def __init__(
        self,
        votes: VoteRepository | None = None,
        onduty: OnDutyRepository | None = None,
    ) -> None:
        """Initialize with optional custom repositories."""
        self.votes_repo = votes or VoteRepository()
        self.onduty_repo = onduty or OnDutyRepository()

    def _build_metrics(self, poll_string: str) -> pd.DataFrame:  # noqa: ARG002 TODO remove unused arg
        """Construct aggregated metrics DataFrame for scoring."""
        votes = self.votes_repo.list_votes()
        on_duty = self.onduty_repo.list_assignments()
        if not votes:
            return pd.DataFrame(columns=["name", "answered", "total_polls", "on_duty_count"])
        vote_df = pd.DataFrame([v.model_dump() for v in votes])
        answered_df = (
            vote_df.assign(answered=vote_df["vote"].notnull())
            .groupby("voter_name")["answered"]
            .sum()
            .reset_index()
            .rename(columns={"voter_name": "name", "answered": "answered"})
        )
        total_df = (
            vote_df.groupby("voter_name")["poll_string"]
            .nunique()
            .reset_index()
            .rename(columns={"voter_name": "name", "poll_string": "total_polls"})
        )
        merged = pd.merge(total_df, answered_df, on="name", how="left")
        merged["participation_rate"] = merged["answered"] / merged["total_polls"]

        if on_duty:
            od_df = pd.DataFrame([o.model_dump() for o in on_duty])
            od_agg = (
                od_df[od_df["assigned"]]
                .groupby("sapeur_name")["poll_string"]
                .nunique()
                .reset_index()
                .rename(columns={"sapeur_name": "name", "poll_string": "on_duty_count"})
            )
            merged = pd.merge(merged, od_agg, on="name", how="left")
        else:
            merged["on_duty_count"] = 0

        merged.fillna({"on_duty_count": 0}, inplace=True)
        merged["on_duty_rate"] = merged["on_duty_count"] / merged["total_polls"]
        # availability (answered any poll) per poll normalized: treat each answered poll as 1
        merged["availability"] = merged["participation_rate"]
        merged["score"] = (merged["availability"] + merged["participation_rate"] + merged["on_duty_rate"]) / 3
        return merged

    def nominate_within_non_responding(
        self,
        poll_string: str,
        candidates: List[str],
        number: int,
    ) -> Dict[str, float]:
        """Nominate among non-responders with margin."""
        metrics = self._build_metrics(poll_string=poll_string).set_index("name")
        subset = metrics.loc[[c for c in candidates if c in metrics.index]].copy()
        if subset.empty:
            return {}
        subset.sort_values("score", ascending=False, inplace=True)
        pick_count = min(len(subset), number + MARGIN_NOMINATION)
        picked = subset.head(pick_count)
        # penalty -1 replicates original behavior
        nominate: Dict[str, float] = {str(name): float(row["score"]) - 1 for name, row in picked.iterrows()}
        return nominate

    def nominate_within_absent(
        self,
        poll_string: str,
        candidates: List[str],
        number: int,
    ) -> Dict[str, float]:
        """Nominate among absent with margin (no penalty)."""
        metrics = self._build_metrics(poll_string=poll_string).set_index("name")
        subset = metrics.loc[[c for c in candidates if c in metrics.index]].copy()
        if subset.empty:
            return {}
        subset.sort_values("score", ascending=False, inplace=True)
        pick_count = min(len(subset), number + MARGIN_NOMINATION)
        picked = subset.head(pick_count)
        nominate: Dict[str, float] = {str(name): float(row["score"]) for name, row in picked.iterrows()}
        return nominate

    def force_nomination(
        self,
        poll_string: str,
        need: int,
        non_responding: List[str],
        absent: List[str],
    ) -> Dict[str, float]:
        """Nominate with fallback from non-responding to absent."""
        first = self.nominate_within_non_responding(poll_string, non_responding, need)
        if len(first) >= need:
            return dict(sorted(first.items(), key=lambda kv: kv[1]))
        remaining = need - len(first)
        second = self.nominate_within_absent(poll_string, [a for a in absent if a not in first], remaining)
        merged = first | second
        return dict(sorted(merged.items(), key=lambda kv: kv[1]))
