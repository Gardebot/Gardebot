"""Module to create Bot and unify the various requests."""

from __future__ import annotations

# pylint: disable=broad-exception-caught, protected-access, dangerous-default-value
import logging

from gardebot.config import GROUP_ID_GARDE_ET_PIQUET
from gardebot.contact import ContactRequest
from gardebot.group import GroupRequest
from gardebot.message import MessageRequest
from gardebot.poll import PollRequest

LOGGER = logging.getLogger(__name__)


class Gardebot(GroupRequest, MessageRequest, PollRequest, ContactRequest):
    """Main Gardebot class combining group, message, contact and poll functionalities."""

    def __init__(self, group_id: str = GROUP_ID_GARDE_ET_PIQUET) -> None:
        """Initialize the Gardebot instance."""
        GroupRequest.__init__(self, group_id=group_id)
        MessageRequest.__init__(self)
        PollRequest.__init__(self)
        ContactRequest.__init__(self, contact_id="")  # Placeholder contact_id
