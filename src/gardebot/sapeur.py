"""Module for managing sapeur data."""

import logging
from typing import Any, Dict, Union

import pandas as pd  # type: ignore[import-untyped]

from gardebot.datamanager import DataManager
from gardebot.group import GroupRequest

LOGGER = logging.getLogger(__name__)


class Sapeur:
    """Handles sapeur data management."""

    def __init__(
        self,
        uid: str,
        name: str,
        pushname: str,
        phone: str,
        joined_date: pd.Timestamp,
        group_id: str,
    ) -> None:
        """Initialize the Sapeur instance."""
        self.uid = uid
        self.name = name
        self.pushname = pushname
        self.phone = phone
        self.joined_date = joined_date
        self.group_id = group_id

    def get_attr(self, attr: str) -> Any:
        """Get an attribute of the sapeur by name."""
        if not hasattr(self, attr):
            raise ValueError(f"Sapeur has no attribute {attr}.")
        return getattr(self, attr)

    def set_by_attr(self, attr: str, value: Any) -> None:
        """Set an attribute of the sapeur by name."""
        if not hasattr(self, attr):
            raise ValueError(f"Sapeur has no attribute {attr}.")
        setattr(self, attr, value)

    def to_dict(self) -> Dict[str, Union[str, pd.Timestamp]]:
        """Convert the Sapeur instance to a dictionary."""
        return {
            "uid": self.uid,
            "name": self.name,
            "pushname": self.pushname,
            "phone": self.phone,
            "joined_date": self.joined_date,
            "group_uid": self.group_id,
        }

    def get_uid(self) -> str:
        """Get the uid of the sapeur."""
        return self.uid

    def get_phone(self) -> str:
        """Get the phone of the sapeur."""
        return self.phone

    def get_name(self) -> str:
        """Get the name of the sapeur."""
        return self.name


class SapeurManager(DataManager):
    """Manages sapeur data."""

    def __init__(self) -> None:
        """Initialize the SapeurManager instance."""
        super().__init__(filename="sapeur")

    def _fetch_sapeurs(self) -> pd.DataFrame:
        """Fetch the sapeurs from the WhatsApp group."""
        group_request = GroupRequest()
        participants_df = group_request.fetch_group_participants_table()
        sapeur_list = []
        for _, row in participants_df.iterrows():
            sapeur = Sapeur(
                uid=str(row["uid"]),
                name=str(row["name"]),
                pushname=str(row["pushname"]),
                phone=str(row["phone"]),
                joined_date=row["joined_date"],
                group_id=str(row["group_id"]),
            )
            sapeur_list.append(sapeur.to_dict())

        return pd.DataFrame(sapeur_list)

    def load_sapeurs(self) -> pd.DataFrame:
        """Load the sapeurs from the data storage."""
        sapeur_df = self.load_dataframe(filename=self.filename)
        if sapeur_df.empty:
            LOGGER.warning("No existing sapeurs in database. Creating one")
            sapeur_df = self._fetch_sapeurs()
            self.save_sapeurs(sapeur_df)
        return sapeur_df

    def save_sapeurs(self, sapeur_df: pd.DataFrame) -> None:
        """Save the sapeurs to the data storage."""
        self.save_dataframe(sapeur_df, self.filename)

    def update_sapeurs(self) -> None:
        """Update the sapeurs in the data storage."""
        new_sapeur_df = self._fetch_sapeurs()
        existing_sapeur_df = self.load_sapeurs()
        self.synch_dataframe(existing_sapeur_df, new_sapeur_df, key="uid")

    def from_dict(self, sapeur_dict: Dict[str, Union[str, pd.Timestamp]]) -> Sapeur:
        """Create a Sapeur instance from a dictionary."""
        return Sapeur(
            uid=str(sapeur_dict["uid"]),
            name=str(sapeur_dict["name"]),
            pushname=str(sapeur_dict["pushname"]),
            phone=str(sapeur_dict["phone"]),
            joined_date=sapeur_dict["joined_date"],  # pyright: ignore[reportArgumentType]
            group_id=str(sapeur_dict["group_uid"]),
        )

    def _get_sapeur_by_attr(self, attr: str) -> pd.DataFrame:
        """Get a sapeur by attribute."""
        sapeur_df = self.load_sapeurs()
        return sapeur_df.set_index(attr)

    def get_sapeur_by_name(self, name: str) -> Sapeur:
        """Get a sapeur by name."""
        sapeur_ser: pd.Series = self._get_sapeur_by_attr("name").loc[name]
        if sapeur_ser.empty:
            raise ValueError(f"Sapeur with name {name} not found.")
        sapeur_dict = sapeur_ser.to_dict()
        sapeur_dict["name"] = name
        sapeur = self.from_dict(sapeur_dict)  # pyright: ignore[reportArgumentType]

        return sapeur

    def get_sapeur_by_uid(self, uid: str) -> Sapeur:
        """Get a sapeur by uid."""
        sapeur_ser: pd.Series = self._get_sapeur_by_attr("uid").loc[uid]
        if sapeur_ser.empty:
            raise ValueError(f"Sapeur with uid {uid} not found.")
        sapeur_dict = sapeur_ser.to_dict()
        sapeur_dict["uid"] = uid
        sapeur = self.from_dict(sapeur_dict)  # pyright: ignore[reportArgumentType]

        return sapeur

    def get_sapeur_by_phone(self, phone: str) -> Sapeur:
        """Get a sapeur by phone."""
        sapeur_ser: pd.Series = self._get_sapeur_by_attr("phone").loc[phone]
        if sapeur_ser.empty:
            raise ValueError(f"Sapeur with phone {phone} not found.")
        sapeur_dict = sapeur_ser.to_dict()
        sapeur_dict["phone"] = phone
        sapeur = self.from_dict(sapeur_dict)  # pyright: ignore[reportArgumentType]

        return sapeur

    def get_sapeur_by_pushname(self, pushname: str) -> Sapeur:
        """Get a sapeur by pushname."""
        sapeur_ser: pd.Series = self._get_sapeur_by_attr("pushname").loc[pushname]
        if sapeur_ser.empty:
            raise ValueError(f"Sapeur with pushname {pushname} not found.")
        sapeur_dict = sapeur_ser.to_dict()
        sapeur_dict["pushname"] = pushname
        sapeur = self.from_dict(sapeur_dict)  # pyright: ignore[reportArgumentType]

        return sapeur

    def filter_sapeurs_by_joined_date(self, threshold_date: pd.Timestamp) -> pd.DataFrame:
        """Filter sapeurs by joined date.

        Arguments:
            threshold_date: The date to filter by.

        Returns:
            A pandas DataFrame of sapeurs who joined before the threshold date.
        """
        sapeur_df = self.load_sapeurs()
        mask = sapeur_df["joined_date"] <= threshold_date
        return sapeur_df[mask]
