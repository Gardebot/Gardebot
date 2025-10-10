import unittest

from gardebot.app import create_app


class TestDispatcherMessageIntegration(unittest.TestCase):
    def setUp(self) -> None:
        """Set up the Flask test client."""
        self.client = create_app().test_client()

    def test_message_handled(self) -> None:
        """Test that a message event is handled correctly."""
        resp = self.client.post(
            "/webhook", json={"event": "message", "payload": {"from_me": False, "from": "123", "body": "Hi", "timestamp": 1}}
        )
        self.assertEqual(resp.status_code, 200)
        if resp.json is None:
            self.fail("Response JSON is None")
        self.assertTrue(resp.json["handled"])
