"""A simple debouncer utility."""

from __future__ import annotations

import threading
from typing import Callable


class Debouncer:
    """A simple debouncer to delay action execution until a period of inactivity."""

    def __init__(self, delay: float, action: Callable[[], None]) -> None:
        """Initialize the debouncer with a delay in seconds and an action to perform."""
        self.delay = delay
        self.action = action
        self._timer: threading.Timer | None = None

    def trigger(self) -> None:
        """Trigger the action after the specified delay, resetting the timer if already running."""
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(self.delay, self.action)
        self._timer.start()
