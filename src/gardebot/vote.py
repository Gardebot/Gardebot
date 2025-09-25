"""Class to handle poll vote in database."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging
from typing import List, Optional, Union

import pandas as pd  # type: ignore[import-untyped]

from gardebot.config import EM_NAME
from gardebot.datamanager import DataManager

LOGGER = logging.getLogger(__name__)


class VoteManager(DataManager):
    """Handles votes from the WAHA API."""

    def _create_sapeur_poll_table(self) -> pd.DataFrame:
        """Create the initial votes table structure."""
        poll_df = self.load_dataframe("polls")
        sapeur_df = self.load_dataframe("sapeurs")
        if poll_df is None or sapeur_df is None:
            LOGGER.error("Poll or sapeur dataframe could not be loaded.")

        result_df = pd.DataFrame(
            columns=poll_df["poll_string"].tolist(), index=sapeur_df["name"].tolist()
        )

        return result_df

    def update_votes(self, poll_string: str, name: str, vote: Optional[str]) -> None:
        """Update votes in the votes table with a given vote."""
        vote_df = self.load_dataframe("votes")
        if vote_df.empty:
            vote_df = self._create_sapeur_poll_table()
            self.save_dataframe(vote_df, "votes")

        if vote == "Absent":
            vote_df.at[name, poll_string] = False
        elif vote == "Présent":
            vote_df.at[name, poll_string] = True
        elif vote is None:
            vote_df.at[name, poll_string] = None
        else:
            LOGGER.error("Vote %s not recognized", vote)
        self.save_dataframe(vote_df, "votes")

    def update_on_duty(
        self, poll_string: str, on_duty_name: Union[str, List[str]]
    ) -> None:
        """Update the table on_duty wih the given name for the given poll_string."""
        on_duty_df = self.load_dataframe("on_duty")
        if on_duty_df.empty:
            on_duty_df = self._create_sapeur_poll_table()
            self.save_dataframe(on_duty_df, "on_duty")

        if isinstance(on_duty_name, List):
            for name in on_duty_name:
                on_duty_df.at[name, poll_string] = True
        else:
            on_duty_df.at[on_duty_name, poll_string] = True

        self.save_dataframe(on_duty_df, "on_duty")

    def test_poll_completion(self, poll_string: str, vote_df: pd.DataFrame) -> bool:
        """Test if the poll have enough people."""
        poll_df = self.load_dataframe("polls").set_index("poll_string")
        if vote_df[poll_string].sum() >= poll_df.loc[poll_string, "headcount"]:
            return True
        return False

    def force_nomination(
        self, sapeur_list_name: List[str], nb_to_nominate: int, poll_string: str
    ) -> Optional[List[str]]:
        """Nominate nb_to_nominate people in the sapeur_list_name, based on their overall participations and answer."""
        for etat_major in EM_NAME:
            if etat_major in sapeur_list_name:
                LOGGER.debug(
                    "Removing %s from the nomination list as part of the Etat Major.",
                    etat_major,
                )
                sapeur_list_name.remove(etat_major)
        if len(sapeur_list_name) == nb_to_nominate:
            return sapeur_list_name
        if len(sapeur_list_name) < nb_to_nominate:
            LOGGER.error(
                "Not enough people to nominate %s in %s",
                nb_to_nominate,
                sapeur_list_name,
            )
            return None
        vote_df = self.load_dataframe("votes")
        on_duty_df = self.load_dataframe("on_duty")
        sapeur_participation_rate = on_duty_df.fillna(0).mean(axis=1)
        sapeur_availability_score = (
            vote_df[poll_string].map({True: 1, False: 1}).fillna(0)
        )
        score_pro_sapeur = (
            sapeur_availability_score + sapeur_participation_rate
        ) * 0.5  # normalized between 0 and 1
        score_pro_sapeur = score_pro_sapeur.loc[sapeur_list_name].sort_values(
            ascending=True
        )
        on_duty_by_force: List[str] = score_pro_sapeur.iloc[
            :nb_to_nominate
        ].index.tolist()

        return on_duty_by_force
