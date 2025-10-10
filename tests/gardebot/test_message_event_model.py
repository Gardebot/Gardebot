import unittest

from pydantic import ValidationError

from gardebot.models.message_event import MessageEventEnvelope


class TestMessageEventModel(unittest.TestCase):
    def test_valid_message_event(self) -> None:
        envelope = MessageEventEnvelope(
            event="message",
            payload={  # type: ignore[arg-type]
                "from_me": False,
                "from": "123",
                "body": "Hello",
                "timestamp": 999,
            },
        )
        self.assertEqual(envelope.event, "message")
        self.assertFalse(envelope.is_from_self())
        self.assertEqual(envelope.sender(), "123")
        self.assertEqual(envelope.text(), "Hello")

    def test_missing_required_field(self) -> None:
        # from_me is required
        with self.assertRaises(ValidationError):
            MessageEventEnvelope(
                event="message",
                payload={  # type: ignore[arg-type]
                    "from": "123",
                    "body": "Hello",
                },
            )

    def test_alias_field(self) -> None:
        envelope = MessageEventEnvelope(
            event="message",
            payload={  # type: ignore[arg-type]
                "from_me": True,
                "from": "456",
            },
        )
        self.assertEqual(envelope.payload.from_, "456")
        self.assertTrue(envelope.is_from_self())
