"""Unit tests for message event models."""

import unittest

from gardebot.models.message_event import MessageEventEnvelope, MessagePayload


class TestMessagePayload(unittest.TestCase):
    """Test MessagePayload model."""

    def test_message_payload_creation(self) -> None:
        """Test MessagePayload creation with aliases."""
        payload = MessagePayload(fromMe=False, **{"from": "sender@test.com"}, body="Test message", timestamp=1672531200)
        self.assertFalse(payload.from_me)
        self.assertEqual(payload.from_, "sender@test.com")
        self.assertEqual(payload.body, "Test message")
        self.assertEqual(payload.timestamp, 1672531200)

    def test_message_payload_optional_fields(self) -> None:
        """Test MessagePayload with optional fields."""
        payload = MessagePayload(fromMe=True)
        self.assertTrue(payload.from_me)
        self.assertIsNone(payload.from_)
        self.assertIsNone(payload.body)
        self.assertIsNone(payload.timestamp)


class TestMessageEventEnvelope(unittest.TestCase):
    """Test MessageEventEnvelope model."""

    def setUp(self) -> None:
        """Set up test data."""
        self.payload = MessagePayload(fromMe=False, **{"from": "sender@test.com"}, body="Test message", timestamp=1672531200)
        self.envelope = MessageEventEnvelope(event="message", payload=self.payload)

    def test_envelope_creation(self) -> None:
        """Test MessageEventEnvelope creation."""
        self.assertEqual(self.envelope.event, "message")
        self.assertEqual(self.envelope.payload, self.payload)

    def test_is_from_self_false(self) -> None:
        """Test is_from_self returns False for external messages."""
        self.assertFalse(self.envelope.is_from_self())

    def test_is_from_self_true(self) -> None:
        """Test is_from_self returns True for self messages."""
        self_payload = MessagePayload(fromMe=True)
        self_envelope = MessageEventEnvelope(event="message", payload=self_payload)
        self.assertTrue(self_envelope.is_from_self())

    def test_sender(self) -> None:
        """Test sender method."""
        self.assertEqual(self.envelope.sender(), "sender@test.com")

    def test_sender_none(self) -> None:
        """Test sender method when from_ is None."""
        payload = MessagePayload(fromMe=True)
        envelope = MessageEventEnvelope(event="message", payload=payload)
        self.assertIsNone(envelope.sender())

    def test_text(self) -> None:
        """Test text method."""
        self.assertEqual(self.envelope.text(), "Test message")

    def test_text_none(self) -> None:
        """Test text method when body is None."""
        payload = MessagePayload(fromMe=True)
        envelope = MessageEventEnvelope(event="message", payload=payload)
        self.assertIsNone(envelope.text())


if __name__ == "__main__":
    unittest.main()
