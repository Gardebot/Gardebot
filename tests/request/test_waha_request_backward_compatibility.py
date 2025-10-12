"""Tests for WahaRequest backward compatibility."""

import unittest
from unittest.mock import Mock, patch

import requests  # type: ignore[import-untyped]

from gardebot.request import WahaRequest


class TestWahaRequestBackwardCompat(unittest.TestCase):
    """Test the WahaRequest class for backward compatibility."""

    def setUp(self) -> None:
        """Set up a WahaRequest instance."""
        self.req = WahaRequest(api_key="k", base_url="http://waha.local", session="s")

    @patch("requests.request")
    def test_post_success(self, mock_req: Mock) -> None:
        """Test a successful POST request."""
        resp = requests.Response()
        resp.status_code = 201
        resp._content = b"created"
        mock_req.return_value = resp
        r = self.req.send_post_request("/api/sendText", {"x": 1})
        self.assertTrue(self.req._is_success(r.status_code))

    @patch("requests.request")
    def test_post_network_error(self, mock_req: Mock) -> None:
        """Test a network error during POST request."""
        mock_req.side_effect = requests.RequestException("net down")
        r = self.req.send_post_request("/api/sendText", {"x": 1})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.text)
