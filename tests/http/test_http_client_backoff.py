import time
import unittest
from typing import Any
from unittest.mock import patch

import requests  # type: ignore[import-untyped]

from gardebot.errors import ExternalServiceError
from gardebot.http.http_client import HttpClient


class TestHttpClientBackoff(unittest.TestCase):
    """Additional tests for retry + backoff behavior."""

    def test_exhaust_retries_with_backoff(self) -> None:
        """Test that retries are exhausted with backoff delays."""
        client = HttpClient(
            "http://example.com",
            retries=2,
            backoff_base=0.01,
            backoff_cap=0.02,
        )
        with patch("requests.request", side_effect=requests.RequestException("boom")):
            start = time.time()
            with self.assertRaises(ExternalServiceError):
                client.request("GET", "/x")
            # Expect at least one sleep (cannot be 0)
            elapsed = time.time() - start
            self.assertGreaterEqual(elapsed, 0.01)

    def test_eventual_success_after_failures(self) -> None:
        """Test that a request eventually succeeds after some failures."""
        client = HttpClient(
            "http://example.com",
            retries=3,
            backoff_base=0.001,
            backoff_cap=0.002,
        )

        seq = [
            requests.RequestException("net1"),
            requests.RequestException("net2"),
            self._mk_response(200, b'{"ok": true}'),
        ]

        def side_effect(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
            """Side effect function to simulate failures followed by success."""
            item = seq.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with patch("requests.request", side_effect=side_effect):
            resp = client.request("GET", "/ping", raise_for_status=True)
            self.assertEqual(resp.status_code, 200)

    def _mk_response(self, status: int, content: bytes) -> requests.Response:
        """Create a mock Response object."""
        r = requests.Response()
        r.status_code = status
        r._content = content  # noqa: SLF001
        return r
