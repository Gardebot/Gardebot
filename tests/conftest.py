"""Root conftest for pytest – injects mock settings before test modules are imported."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock gardebot.settings before any test module that imports Gardebot or
# PollingAdapter is loaded. These modules transitively import settings.py,
# which instantiates ApiSettings (calling _load_secret) and requires
# DOPPLER_TOKEN in the environment. By injecting a mock module into
# sys.modules here (conftest is loaded before test modules), we avoid the
# ValueError in all test environments that don't have DOPPLER_TOKEN set.
# ---------------------------------------------------------------------------

_mock_api = MagicMock()
_mock_api.api_key = "mock-api-key"
_mock_api.base_url = "http://test:3000"
_mock_api.session = "default"
_mock_api.timeout_seconds = 10
_mock_api.retry_attempts = 3
_mock_api.retry_backoff_seconds = 0.5
_mock_api.retry_backoff_max_seconds = 5.0

_mock_settings_obj = MagicMock()
_mock_settings_obj.api = _mock_api

_mock_settings_module = MagicMock()
_mock_settings_module.settings = _mock_settings_obj

if "gardebot.settings" not in sys.modules:
    sys.modules["gardebot.settings"] = _mock_settings_module
