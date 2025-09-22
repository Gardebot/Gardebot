"""Class to handle poll vote in database."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging

import pandas as pd  # type: ignore[import-untyped]

from gardebot.datamanager import DataManager

LOGGER = logging.getLogger(__name__)


class VoteManager(DataManager):
    """Handles votes from the WAHA API."""

    def _create_result_table(self) -> pd.DataFrame:
        """Create the initial votes table structure."""
        poll_df = self.load_dataframe("polls")
        sapeur_df = self.load_dataframe("sapeurs")
        if poll_df is None or sapeur_df is None:
            LOGGER.error("Poll or sapeur dataframe could not be loaded.")

        result_df = pd.DataFrame(
            columns=poll_df["poll_string"].tolist(), index=sapeur_df["name"].tolist()
        )

        self.save_dataframe(result_df, "votes")

        return result_df

    def update_votes(self, poll_string: str, name: str, vote: str) -> None:
        """Update votes in the votes table with a given vote."""
        vote_df = self.load_dataframe("votes")
        if vote_df.empty:
            vote_df = self._create_result_table()

        if vote == "Absent":
            vote_df.at[name, poll_string] = False
        elif vote == "Présent":
            vote_df.at[name, poll_string] = True
        else:
            LOGGER.error("Vote %s not recognized", vote)

        self.save_dataframe(vote_df, "votes")
