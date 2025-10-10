"""Class to handle convocations in database."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Union

import pandas as pd  # type: ignore[import-untyped]

from gardebot.config import EM_NAME, MARGIN_NOMINATION
from gardebot.datamanager import DataManager
from gardebot.vote import VoteManager

LOGGER = logging.getLogger(__name__)


class OndutyManager(DataManager):
    """Handles on duty data."""

    def __init__(self) -> None:
        """Initialize the VoteManager instance."""
        super().__init__(filename="on_duty")

    def _initialize_onduty_table(self) -> pd.DataFrame:
        """Create the initial on_duty table structure."""
        vote_manager = VoteManager()
        return vote_manager._initialize_vote_table()

    def load_onduty(self) -> pd.DataFrame:
        """Load the votes table from the database."""
        onduty_df = self.load_dataframe(self.filename)
        if onduty_df.empty:
            onduty_df = self._initialize_onduty_table()
            self.save_onduty(onduty_df)
        return onduty_df

    def save_onduty(self, onduty_df: pd.DataFrame) -> None:
        """Save the votes table to the database."""
        self.save_dataframe(onduty_df, self.filename)

    def test_assigned(self, poll_string: str) -> bool:
        """Test if the poll is on duty."""
        on_duty_df = self.load_onduty()
        on_duty_list = on_duty_df[~on_duty_df[poll_string].isna()].index.tolist()

        if len(on_duty_list) > 0:
            return True
        return False

    def update_on_duty(self, poll_string: str, on_duty_name: Union[str, List[str]]) -> None:
        """Update the table on_duty wih the given name for the given poll_string."""
        on_duty_df = self.load_onduty()
        if isinstance(on_duty_name, List):
            for name in on_duty_name:
                on_duty_df.at[name, poll_string] = True
        else:
            on_duty_df.at[on_duty_name, poll_string] = True

        self.save_onduty(on_duty_df)

    def _filter_etat_major(self, sapeur_list_name: List[str]) -> List[str]:
        """Filter the sapeur_list_name to keep only the available ones."""
        retour = sapeur_list_name.copy()
        for etat_major in EM_NAME:
            if etat_major in sapeur_list_name:
                LOGGER.debug(
                    "Removing %s from the nomination list as part of the Etat Major.",
                    etat_major,
                )
                retour.remove(etat_major)
        return retour

    def force_nomination(self, nb_to_nominate: int, poll_string: str) -> Dict[str, float]:
        """Nominate nb_to_nominate people  based on their overall participations and answer."""
        nominated = self.nominate_within_non_responding(nb_to_nominate, poll_string)
        if len(nominated) < nb_to_nominate:
            LOGGER.info(
                "Not enough non-responding people to nominate %s. Completing with absent people.",
                nb_to_nominate,
            )
            remaining_to_nominate = nb_to_nominate - len(nominated)
            nominated_within_absent = self.nominate_within_absent(remaining_to_nominate, poll_string)
            nominated_within_absent = {k: v for k, v in nominated_within_absent.items() if k not in nominated}
            nominated.update(nominated_within_absent)

        sorted_nominated = dict(sorted(nominated.items(), key=lambda item: item[1], reverse=False))
        return sorted_nominated

    def nominate_within_non_responding(self, nb_to_nominate: int, poll_string: str) -> Dict[str, float]:
        """Nominate people within the unanswered list."""
        vote_manager = VoteManager()
        non_responding = vote_manager.get_non_responding_list(poll_string)
        non_responding = self._filter_etat_major(non_responding)

        if len(non_responding) <= nb_to_nominate:
            if len(non_responding) < nb_to_nominate:
                LOGGER.warning(
                    "Not enough non-responding people to nominate %s in %s",
                    nb_to_nominate,
                    non_responding,
                )
            return dict.fromkeys(non_responding, -1.0)
        score_pro_sapeur = self._calculate_participation_score(poll_string, non_responding)
        if score_pro_sapeur.size < nb_to_nominate + MARGIN_NOMINATION:
            sapeur_nominated: Dict[str, float] = score_pro_sapeur.to_dict()
        else:
            sapeur_nominated = score_pro_sapeur.iloc[: nb_to_nominate + MARGIN_NOMINATION].to_dict()
        return {k: v - 1 for k, v in sapeur_nominated.items()}

    def nominate_within_absent(self, nb_to_nominate: int, poll_string: str) -> Dict[str, float]:
        """Nominate people within the absent list."""
        vote_manager = VoteManager()
        absent = vote_manager.get_absent_list(poll_string)
        absent = self._filter_etat_major(absent)
        score_pro_sapeur = self._calculate_participation_score(poll_string, absent)
        if score_pro_sapeur.size < nb_to_nominate + MARGIN_NOMINATION:
            sapeur_nominated: Dict[str, float] = score_pro_sapeur.iloc[:nb_to_nominate].to_dict()
        else:
            sapeur_nominated = score_pro_sapeur.iloc[: nb_to_nominate + MARGIN_NOMINATION].to_dict()
        return sapeur_nominated

    def _calculate_participation_score(self, poll_string: str, potential_sapeur: Optional[List[str]] = None) -> pd.Series:
        """Calculate the participation score for each sapeur in potential_sapeur."""
        vote_manager = VoteManager()
        vote_df = vote_manager.load_votes()
        onduty_df = self.load_onduty()

        on_duty_rate = onduty_df.infer_objects(copy=False).fillna(0).mean(axis=1)
        vote_participation_rate = vote_df.infer_objects(copy=False).fillna(0).mean(axis=1)
        sapeur_availability_score = vote_df[poll_string].map({True: 1, False: 1}).infer_objects(copy=False).fillna(0)
        score_pro_sapeur = (sapeur_availability_score + vote_participation_rate + on_duty_rate) / 3  # normalized between 0 and 1
        score_pro_sapeur.sort_values(ascending=False, inplace=True)
        if potential_sapeur is not None:
            score_pro_sapeur = score_pro_sapeur.loc[potential_sapeur]
        return score_pro_sapeur

    def get_on_duty_list(self, poll_string: str) -> List[str]:
        """Get the list of people who were on duty for the given poll_string."""
        on_duty_df = self.load_onduty()
        on_duty_list: List[str] = on_duty_df[~on_duty_df[poll_string].isna()].index.tolist()
        return on_duty_list
