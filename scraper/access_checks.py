"""Detect login walls, CAPTCHAs, rate limits and unavailable profiles.

These conditions are never bypassed. Anything in ``STOP_CATEGORIES`` ends the
run so the user can resolve it manually.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

STOP_CATEGORIES = {"captcha", "login_required", "rate_limited", "access_denied"}

_CAPTCHA_MARKERS = (
    "let's do a quick security check",
    "security verification",
    "verify you are a human",
    "i'm not a robot",
    "unusual activity",
)
_RATE_MARKERS = ("too many requests", "request limit", "rate limit")
_UNAVAILABLE_MARKERS = (
    "this profile is not available",
    "profile isn't available",
    "this page doesn't exist",
    "page not found",
)


def detect_access_issue(url: str, status: Optional[int] = None, html: str = "") -> Optional[str]:
    """Return a category from ``STOP_CATEGORIES`` or ``None`` when access looks fine."""
    if status == 429:
        return "rate_limited"
    if status in (401, 403, 999):
        return "access_denied"
    path = urlparse(url).path.lower()
    if path.startswith("/checkpoint"):
        return "captcha"
    if path.startswith(("/authwall", "/login", "/uas/login", "/signup")):
        return "login_required"
    if html:
        low = html[:300_000].lower()
        if any(marker in low for marker in _CAPTCHA_MARKERS):
            return "captcha"
        if any(marker in low for marker in _RATE_MARKERS):
            return "rate_limited"
    return None


def detect_unavailable(html: str) -> bool:
    """True when the page says the profile does not exist / is not visible."""
    low = html[:300_000].lower()
    return any(marker in low for marker in _UNAVAILABLE_MARKERS)
