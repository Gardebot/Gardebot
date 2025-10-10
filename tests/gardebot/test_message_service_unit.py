import unittest
from typing import Any, List

from gardebot.services.message_service import MessageService


class DummySender:
    """A dummy sender that records sent messages for testing."""

    def __init__(self) -> None:
        """Initialize the dummy sender with an empty list of sent messages."""
        self.sent: List[Any] = []

    def send_text(self, to_number: str, message_text: str) -> None:
        """Record the sent message."""
        self.sent.append((to_number, message_text))


class TestMessageService(unittest.TestCase):
    """Unit tests for the MessageService class."""

    def test_echo_path(self) -> None:
        """Test the echo behavior for a normal message."""
        sender = DummySender()
        svc = MessageService(sender=sender)
        svc.handle_webhook_payload({"payload": {"from_me": False, "from": "123", "body": "Hello world", "timestamp": 1111}})
        self.assertEqual(len(sender.sent), 1)
        self.assertIn("Echoing", sender.sent[0][1])

    def test_ping_command(self) -> None:
        """Test the !ping command handling."""
        sender = DummySender()
        svc = MessageService(sender=sender)
        svc.handle_webhook_payload({"payload": {"from_me": False, "from": "123", "body": "!ping test", "timestamp": 2222}})
        self.assertEqual(len(sender.sent), 1)
        self.assertTrue(sender.sent[0][1].startswith("[pong]"))

    def test_ignore_from_me(self) -> None:
        """Test that messages from self are ignored."""
        sender = DummySender()
        svc = MessageService(sender=sender)
        svc.handle_webhook_payload({"payload": {"from_me": True}})
        self.assertEqual(sender.sent, [])

    def test_missing_payload(self) -> None:
        """Test handling of missing payload."""
        sender = DummySender()
        svc = MessageService(sender=sender)
        svc.handle_webhook_payload({})
        self.assertEqual(sender.sent, [])

    def test_unknown_command(self) -> None:
        """Test handling of an unknown command."""
        sender = DummySender()
        svc = MessageService(sender=sender)
        svc.handle_webhook_payload({"payload": {"from_me": False, "from": "X", "body": "!noop"}})
        self.assertEqual(len(sender.sent), 1)
        self.assertIn("Unknown command", sender.sent[0][1])
