"""Pytest configuration: mock Doppler secret loading so tests run without credentials."""

from unittest.mock import patch

# Patch _load_secret globally so that gardebot.settings can be imported without DOPPLER_TOKEN.
# This must happen before any gardebot module that transitively imports gardebot.settings.
_patcher = patch("gardebot.common.common._load_secret", return_value="test-api-key")
_patcher.start()
