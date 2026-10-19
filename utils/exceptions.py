"""Exception hierarchy used across the application."""
from __future__ import annotations


class ScraperError(Exception):
    """Base class for all application errors."""


class InputFileError(ScraperError):
    """The uploaded Excel file is missing, unsupported or unreadable."""


class BrowserSetupError(ScraperError):
    """Playwright or its browser binaries are not installed correctly."""


class TemporaryFetchError(ScraperError):
    """A transient technical failure. Safe to retry with backoff."""


class ProfileUnavailableError(ScraperError):
    """The profile does not exist or is not visible to the signed-in user."""


class AccessBlockedError(ScraperError):
    """Access denied, CAPTCHA, login wall or rate limit. Stops the whole run."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


class RunStopped(ScraperError):
    """The user asked to stop while an operation was in progress."""
