"""Models for inbound WAHA message events."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class MessagePayload(BaseModel):
    """Typed representation of WAHA message payload structure we rely on."""

    from_me: bool = Field(..., alias="fromMe", description="True if message originated from the bot session.")
    from_: Optional[str] = Field(default=None, alias="from", description="Sender's chat/number identifier.")
    body: Optional[str] = Field(default=None, description="Text body of the message.")
    timestamp: Optional[int] = Field(default=None, description="Epoch timestamp (seconds) from WAHA.")


class MessageEventEnvelope(BaseModel):
    """Envelope for an inbound 'message' event."""

    event: str
    payload: MessagePayload

    def is_from_self(self) -> bool:
        """Check if the message was sent from the bot itself."""
        return self.payload.from_me

    def sender(self) -> Optional[str]:
        """Get the sender's chat/number identifier."""
        return self.payload.from_

    def text(self) -> Optional[str]:
        """Get the text body of the message."""
        return self.payload.body
