"""Playwright lifecycle with a persistent, user-authorised profile.

The browser profile directory keeps the session between runs so the user only
signs in manually once. Cookies/tokens are never read, printed or logged.
"""
from __future__ import annotations

from typing import Any, Optional

from config import AppConfig
from utils.exceptions import BrowserSetupError


class BrowserManager:
    """Context manager that owns Playwright, the browser context and one page."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._playwright: Any = None
        self.context: Any = None
        self.page: Any = None

    def __enter__(self) -> "BrowserManager":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserSetupError(
                "Playwright is not installed. Run: pip install -r requirements.txt"
            ) from exc
        self._playwright = sync_playwright().start()
        try:
            self.config.user_data_dir.mkdir(parents=True, exist_ok=True)
            self.context = self._playwright.chromium.launch_persistent_context(
                str(self.config.user_data_dir),
                headless=self.config.headless,
                viewport={"width": 1280, "height": 900},
            )
        except Exception as exc:
            self._playwright.stop()
            message = str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__
            raise BrowserSetupError(
                f"Could not start Chromium ({message}). "
                "Run: python -m playwright install chromium"
            ) from exc
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(self.config.page_timeout_ms)
        return self

    def __exit__(self, *exc_info: Optional[object]) -> None:
        try:
            if self.context:
                self.context.close()
        finally:
            if self._playwright:
                self._playwright.stop()
