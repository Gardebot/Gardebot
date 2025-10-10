import unittest

from gardebot.app import create_app


class TestAppMessageValidationIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.client = create_app().test_client()

    def test_valid_message_event_flow(self) -> None:
        resp = self.client.post(
            "/webhook",
            json={
                "event": "message",
                "payload": {
                    "from_me": False,
                    "from": "123",
                    "body": "!ping hello",
                    "timestamp": 1000,
                },
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json["status"], "success")  # type: ignore[index]
        self.assertTrue(resp.json["handled"])  # type: ignore[index]

    def test_invalid_message_missing_from_me(self) -> None:
        resp = self.client.post(
            "/webhook",
            json={
                "event": "message",
                "payload": {
                    "from": "123",
                    "body": "Hello",
                },
            },
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json["message"], "invalid_message_payload")  # type: ignore[index]

    def test_non_message_event_basic_check(self) -> None:
        resp = self.client.post(
            "/webhook",
            json={"event": "poll.vote", "payload": {"x": 1}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json["status"], "success")  # type: ignore[index]

    def test_non_message_event_missing_event(self) -> None:
        resp = self.client.post(
            "/webhook",
            json={"payload": {"x": 1}},
        )
        self.assertIn(resp.status_code, (400, 422))  # Expect a failure
        self.assertEqual(resp.json["message"], "invalid_event")  # type: ignore[index]
