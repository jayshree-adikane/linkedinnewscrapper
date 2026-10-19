"""Fixed, configurable pacing between profile visits.

The delay is deliberately constant: it exists to keep request volume low, not
to imitate human behaviour.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional


class RateLimiter:
    """Guarantees at least ``delay_seconds`` between visits."""

    def __init__(self, delay_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.delay_seconds = max(0.0, delay_seconds)
        self._clock = clock
        self._last: Optional[float] = None

    def mark(self) -> None:
        """Record that a visit just finished."""
        self._last = self._clock()

    def wait(self, stop_event: Optional[threading.Event] = None) -> bool:
        """Block until the next visit is allowed.

        Returns ``False`` if ``stop_event`` was set while waiting.
        """
        if self._last is None:
            return True
        remaining = self.delay_seconds - (self._clock() - self._last)
        if remaining <= 0:
            return True
        if stop_event is not None:
            return not stop_event.wait(remaining)
        time.sleep(remaining)
        return True
