import unittest

from gardebot.validation import MessageValidationError, validate_message_event


class TestMessageValidation(unittest.TestCase):
    def test_validate_success(self) -> None:
        """Test that valid message events are parsed correctly."""
        data = {
            "event": "message",
            "payload": {
                "fromMe": False,
                "from": "abc",
                "body": "Ping",
                "timestamp": 111,
            },
        }
        envelope = validate_message_event(data)
        self.assertEqual(envelope.payload.body, "Ping")

    def test_validate_failure(self) -> None:
        """Test that invalid message events raise MessageValidationError."""
        # Missing 'fromMe'
        data = {
            "event": "message",
            "payload": {
                "from": "abc",
                "body": "Ping",
            },
        }
        with self.assertRaises(MessageValidationError):
            validate_message_event(data)
