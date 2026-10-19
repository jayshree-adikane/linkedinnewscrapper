"""Manual-login handling. The user signs in; this class only waits and checks."""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable

from config import AppConfig
from scraper.access_checks import detect_access_issue

FEED_URL = "https://www.linkedin.com/feed/"
_AUTHENTICATED_RE = re.compile(r"linkedin\.com/(feed|mynetwork|jobs|messaging|notifications)")


class SessionManager:
    """Checks whether the browser has an authenticated session."""

    def __init__(self, page: Any, config: AppConfig, logger: logging.Logger) -> None:
        self.page = page
        self.config = config
        self.logger = logger

    def is_authenticated(self) -> bool:
        url = self.page.url
        return bool(_AUTHENTICATED_RE.search(url)) and detect_access_issue(url) is None

    def ensure_login(self, stop_event: threading.Event, on_status: Callable[[str], None]) -> bool:
        """Open LinkedIn and wait for the user to finish signing in manually.

        Any verification step (2FA, CAPTCHA) is completed by the user in the
        browser window. Returns ``False`` on timeout or when the user stops.
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        self.page.goto(FEED_URL, wait_until="domcontentloaded")
        if self.is_authenticated():
            self.logger.info("existing authorised session found")
            return True
        on_status("Sign in to LinkedIn in the opened browser window. Waiting...")
        deadline = time.monotonic() + self.config.login_timeout_seconds
        while time.monotonic() < deadline and not stop_event.is_set():
            try:
                self.page.wait_for_url(_AUTHENTICATED_RE, timeout=3000)
                self.logger.info("manual login completed")
                return True
            except PlaywrightTimeout:
                continue
        return False
