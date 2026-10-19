"""Parse a saved/rendered LinkedIn profile HTML document."""
from __future__ import annotations

from typing import Any, Optional

from bs4 import BeautifulSoup

from browser import selectors
from scraper.employment_parser import parse_experience_section, visible_lines
from scraper.models import ParsedProfile

_LOCATION_NOISE = ("connections", "followers", "contact info")


def _first_text(soup: BeautifulSoup, candidates: list[str]) -> str:
    for selector in candidates:
        for tag in soup.select(selector):
            text = " ".join(tag.get_text(" ", strip=True).split())
            if text and not any(noise in text.lower() for noise in _LOCATION_NOISE):
                return text
    return ""


def find_experience_section(soup: BeautifulSoup) -> Optional[Any]:
    """Locate the Experience card via its anchor, falling back to its heading."""
    anchor = soup.select_one(selectors.EXPERIENCE_ANCHOR)
    if anchor is not None:
        return anchor.find_parent("section") or anchor.parent
    for section in soup.find_all("section"):
        heading = section.find("h2")
        if heading:
            lines = visible_lines(heading)
            if lines and lines[0].lower() == selectors.EXPERIENCE_HEADING:
                return section
    return None


def parse_profile_html(html: str) -> ParsedProfile:
    """Extract name, location and positions. Missing parts stay empty."""
    soup = BeautifulSoup(html, "html.parser")
    section = find_experience_section(soup)
    return ParsedProfile(
        full_name=_first_text(soup, selectors.NAME),
        location=_first_text(soup, selectors.LOCATION),
        positions=parse_experience_section(section) if section is not None else [],
    )
