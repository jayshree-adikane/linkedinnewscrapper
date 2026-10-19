"""LinkedIn profile URL validation and normalisation."""
from __future__ import annotations

import re
from typing import Any, Optional

_PROFILE_RE = re.compile(
    r"^https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/(?P<slug>[^/?#\s]+)/?(?:[?#].*)?$",
    re.IGNORECASE,
)


def normalize_profile_url(raw: Any) -> Optional[str]:
    """Return a canonical ``https://www.linkedin.com/in/<slug>/`` URL.

    Returns ``None`` when the value is empty or is not a personal profile URL
    (company pages, search URLs and other sites are rejected).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return None
    if text.lower().startswith(("linkedin.com/", "www.linkedin.com/")):
        text = "https://" + text
    match = _PROFILE_RE.match(text)
    if not match:
        return None
    return f"https://www.linkedin.com/in/{match.group('slug')}/"


def is_valid_profile_url(raw: Any) -> bool:
    """True when ``raw`` is a valid LinkedIn personal profile URL."""
    return normalize_profile_url(raw) is not None
