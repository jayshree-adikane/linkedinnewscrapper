"""Page object for a LinkedIn profile: navigates and returns rendered HTML."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from browser import selectors
from scraper.access_checks import detect_access_issue, detect_unavailable
from utils.exceptions import AccessBlockedError, ProfileUnavailableError, TemporaryFetchError

logger = logging.getLogger("prospect_scraper")

_ISSUE_MESSAGES = {
    "captcha": "A CAPTCHA / security check appeared. Solve it manually, then start a new run.",
    "login_required": "The session is not signed in (login wall). Sign in manually and retry.",
    "rate_limited": "A rate-limit warning was detected. Wait before running again.",
    "access_denied": "Access was denied by the site.",
}


def _short(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return (text[0] if text else type(exc).__name__)[:200]


class ProfilePage:
    """Visits one profile URL at a time using event-based waits (no fixed sleeps)."""

    def __init__(self, page: Any, timeout_ms: int = 30_000, debug_dir: Optional[Path] = None) -> None:
        self.page = page
        self.timeout_ms = timeout_ms
        self.debug_dir = debug_dir

    def _has_main_content(self) -> bool:
        """True if the page has a <main> with real text (i.e. it did render)."""
        try:
            text = self.page.inner_text("main", timeout=2000)
        except Exception:
            return False
        return len(text.strip()) > 200

    def _dump_debug(self, url: str, html: str) -> None:
        """Save the page HTML so selectors can be fixed against real markup."""
        if self.debug_dir is None:
            return
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^A-Za-z0-9_-]+", "_", url.rstrip("/").rsplit("/", 1)[-1])[:60] or "profile"
            path = self.debug_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{slug}.html"
            path.write_text(html, encoding="utf-8")
            logger.warning("saved page snapshot for debugging: %s", path)
        except OSError as exc:
            logger.warning("could not save debug snapshot: %s", exc)

    def _raise_on_issue(self, status: Any, html: str = "") -> None:
        issue = detect_access_issue(self.page.url, status, html)
        if issue:
            raise AccessBlockedError(issue, _ISSUE_MESSAGES[issue])

    def open(self, url: str) -> str:
        """Navigate to ``url`` and return the page HTML.

        Raises ``TemporaryFetchError`` (retryable), ``ProfileUnavailableError``
        (per-record failure) or ``AccessBlockedError`` (stops the whole run).
        """
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            response = self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        except PlaywrightTimeout as exc:
            raise TemporaryFetchError("Navigation timed out") from exc
        except PlaywrightError as exc:
            raise TemporaryFetchError(f"Navigation error: {_short(exc)}") from exc

        status = response.status if response else None
        self._raise_on_issue(status)
        if status == 404:
            raise ProfileUnavailableError("Profile not found (HTTP 404)")
        if status is not None and status >= 500:
            raise TemporaryFetchError(f"Server error (HTTP {status})")

        try:
            self.page.wait_for_selector(selectors.PROFILE_READY, state="attached", timeout=self.timeout_ms)
        except PlaywrightTimeout as exc:
            html = self.page.content()
            self._dump_debug(url, html)
            self._raise_on_issue(status, html)
            if detect_unavailable(html):
                raise ProfileUnavailableError("Profile is not available to this account") from exc
            if not self._has_main_content():
                raise TemporaryFetchError("Profile content did not load in time") from exc
            # The page rendered but our ready-selectors did not match (markup
            # changed). Hand the HTML to the parser so partial data is kept.
            logger.warning("ready selector not found, parsing anyway: %s", url)
            return html

        try:  # Experience may be absent on limited views; that is not an error.
            self.page.wait_for_selector(selectors.EXPERIENCE_ANCHOR, state="attached", timeout=5000)
        except PlaywrightTimeout:
            pass

        html = self.page.content()
        self._raise_on_issue(status, html)
        if detect_unavailable(html):
            raise ProfileUnavailableError("Profile is not available to this account")
        return html
