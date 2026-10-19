"""Exponential backoff with a strict retry limit."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, Tuple, Type, TypeVar

from utils.exceptions import RunStopped, TemporaryFetchError

T = TypeVar("T")


def retry_with_backoff(
    func: Callable[[], T],
    *,
    max_retries: int,
    base_delay: float,
    retry_on: Tuple[Type[BaseException], ...] = (TemporaryFetchError,),
    stop_event: Optional[threading.Event] = None,
    logger: Optional[logging.Logger] = None,
) -> T:
    """Call ``func``; on a retryable error wait ``base_delay * 2**n`` and retry.

    At most ``max_retries`` retries are made, then the last error is re-raised.
    Only exceptions listed in ``retry_on`` are retried. Raises ``RunStopped`` if
    the stop event fires during a backoff wait.
    """
    attempt = 0
    while True:
        try:
            return func()
        except retry_on as exc:
            if attempt >= max_retries:
                raise
            delay = base_delay * (2**attempt)
            attempt += 1
            if logger:
                logger.warning("retrying after temporary failure (%s/%s): %s", attempt, max_retries, exc)
            if stop_event is not None:
                if stop_event.wait(delay):
                    raise RunStopped("Stopped by user during retry backoff") from exc
            elif delay > 0:
                threading.Event().wait(delay)
