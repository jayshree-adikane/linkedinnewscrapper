"""All page selectors in one place.

LinkedIn changes its markup often. When fields stop being extracted, this is
the first file to update (see README > Troubleshooting > Selector changes).
Selectors are tried in order; the first non-empty match wins.
"""
from __future__ import annotations

NAME = ["main h1", "h1"]

LOCATION = [
    "span.text-body-small.inline.t-black--light.break-words",
    "div.mt2 span.text-body-small",
    "[data-test-id='profile-location']",
]

# Anchor element inside the Experience card, and fallback heading text.
EXPERIENCE_ANCHOR = "#experience"
EXPERIENCE_HEADING = "experience"

# Used by Playwright to know the profile has rendered. Any one match is enough;
# kept broad because LinkedIn no longer reliably renders the name as an <h1>.
PROFILE_READY = ", ".join([
    "main h1",
    "h1",
    "#experience",
    "main section h2",
    "[data-view-name='profile-card']",
    "section.artdeco-card",
])
