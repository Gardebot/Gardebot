import importlib
import os
import sys
import unittest

import gardebot.settings as settings_mod


class TestSettings(unittest.TestCase):
    def setUp(self) -> None:
        # Ensure re-import for clean state
        for k in list(os.environ.keys()):
            if k.startswith("SERVER_") or k.startswith("WAHA_") or k.startswith("LOG_"):
                # Remove environment variables with specified prefixes for test isolation
                os.environ.pop(k)

    def test_default_settings(self) -> None:
        # Force a reload of settings module
        if "gardebot.settings" in globals():
            sys.modules.pop("gardebot.settings", None)

        self.assertEqual(settings_mod.settings.server.port, 5000)

    def test_env_override(self) -> None:
        os.environ["SERVER_PORT"] = "5555"

        importlib.reload(settings_mod)
        self.assertEqual(settings_mod.settings.server.port, 5555)
        os.environ.pop("SERVER_PORT")
