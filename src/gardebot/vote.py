"""Class to handle poll vote in database."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging
from typing import Any, Dict, List, Optional, Union

import pandas as pd  # type: ignore[import-untyped]

from gardebot.config import EM_NAME
from gardebot.datamanager import DataManager
from gardebot.event import EventManager
from gardebot.sapeur import SapeurManager

LOGGER = logging.getLogger(__name__)


class Vote:
    """Handles a vote instance."""

    def __init__(
        self,
        poll_string: str,
        voter_name: str,
        vote: Optional[str] = None,
    ) -> None:
        """Initialize the Vote instance."""
        self.poll_string = poll_string
        self.voter_name = voter_name
        self.vote = vote

    def get_attr(self, attr: str) -> Any:
        """Get an attribute of the vote by name."""
        if not hasattr(self, attr):
            raise ValueError(f"Vote has no attribute {attr}.")
        return getattr(self, attr)

    def get_poll_string(self) -> str:
        """Get the poll string of the vote."""
        return self.poll_string

    def get_voter_name(self) -> str:
        """Get the voter name of the vote."""
        return self.voter_name

    def get_vote(self) -> Optional[str]:
        """Get the vote value."""
        return self.vote

    def set_attr(self, attr: str, value: Any) -> None:
        """Set an attribute of the vote by attribute name."""
        if not hasattr(self, attr):
            raise ValueError(f"Vote has no attribute {attr}.")
        setattr(self, attr, value)

    def to_dict(self) -> Dict[str, Union[str, None]]:
        """Convert the Vote instance to a dictionary."""
        return {
            "poll_string": self.poll_string,
            "voter_name": self.voter_name,
            "vote": self.vote,
        }


class VoteManager(DataManager):
    """Handles votes from the WAHA API."""

    def __init__(self) -> None:
        """Initialize the VoteManager instance."""
        super().__init__(filename="votes")

    def _initialize_vote_table(self) -> pd.DataFrame:
        """Create the initial votes table structure."""
        poll_string_list = EventManager().load_gardes()["poll_string"].tolist()
        sapeur_list = SapeurManager().load_sapeurs()["name"].tolist()

        return pd.DataFrame(columns=poll_string_list, index=sapeur_list)

    def load_votes(self) -> pd.DataFrame:
        """Load the votes table from the database."""
        vote_df = self.load_dataframe(self.filename)
        if vote_df.empty:
            vote_df = self._initialize_vote_table()
            self.save_votes(vote_df)
        return vote_df

    def save_votes(self, vote_df: pd.DataFrame) -> None:
        """Save the votes table to the database."""
        self.save_dataframe(vote_df, self.filename)

    def update_votes(self, vote: Vote) -> None:
        """Update votes in the votes table with a given vote."""
        vote_df = self.load_votes()

        if vote.get_vote() == "Absent":
            vote_df.at[vote.get_voter_name(), vote.get_poll_string()] = False
        elif vote.get_vote() == "Présent":
            vote_df.at[vote.get_voter_name(), vote.get_poll_string()] = True
        elif vote.get_vote() is None:
            vote_df.at[vote.get_voter_name(), vote.get_poll_string()] = None
        else:
            LOGGER.error("Vote %s not recognized", vote.get_vote())
        self.save_votes(vote_df)

    def test_garde_completion(self, poll_string: str) -> bool:
        """Test if the garde have enough people."""
        vote_df = self.load_votes()
        event_manager = EventManager()
        garde = event_manager.get_garde_by_pollstring(poll_string)

        if vote_df[poll_string].sum() >= garde.get_headcount():
            return True
        return False

    def test_all_voted(self, poll_string: str) -> bool:
        """Test if all sapeurs have voted."""
        vote_df = self.load_votes()
        tmp_sapeur_name_who_did_not_answered = vote_df[
            vote_df[poll_string].isnull()
        ].index.tolist()
        sapeur_name_who_did_not_answered = [
            name for name in tmp_sapeur_name_who_did_not_answered if name not in EM_NAME
        ]

        if len(sapeur_name_who_did_not_answered) == 0:
            LOGGER.info("All sapeurs have voted for poll %s", poll_string)
            return True
        return False

    def get_present_list(self, poll_string: str) -> List[str]:
        """Get the list of sapeurs who voted present for a given poll."""
        vote_df = self.load_votes()
        present_list: List[str] = vote_df[vote_df[poll_string] is True].index.tolist()
        return present_list

    def get_absent_list(self, poll_string: str) -> List[str]:
        """Get the list of sapeurs who voted absent for a given poll."""
        vote_df = self.load_votes()
        absent_list: List[str] = vote_df[vote_df[poll_string] is False].index.tolist()
        return absent_list

    def get_non_responding_list(self, poll_string: str) -> List[str]:
        """Get the list of sapeurs who did not respond for a given poll."""
        vote_df = self.load_votes()
        non_responding_list: List[str] = vote_df[
            vote_df[poll_string].isnull()
        ].index.tolist()
        return non_responding_list
