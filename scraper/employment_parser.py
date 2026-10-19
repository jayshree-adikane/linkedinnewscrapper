"""Parse the Experience section into structured positions.

Handles flat entries and "grouped" entries (several roles under one company).
Date parsing supports English month names; dates are never guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from scraper.models import Position

_MONTHS = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]
_MONTH_LOOKUP = {m.lower(): m for m in _MONTHS}
_MONTH_LOOKUP.update({m[:3].lower(): m for m in _MONTHS})
_MONTH_LOOKUP["sept"] = "September"

_RANGE_RE = re.compile(
    r"^(?:(?P<sm>[A-Za-z]{3,9})\.?\s+)?(?P<sy>\d{4})\s*(?:-|–|—|to)\s*"
    r"(?:(?:(?P<em>[A-Za-z]{3,9})\.?\s+)?(?P<ey>\d{4})|(?P<pres>Present))"
    r"(?:\s*[·•]\s*(?P<dur>.+))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DateRange:
    """A parsed ``Mon YYYY - Mon YYYY | Present`` range."""

    start_month: str
    start_year: str
    end_month: str
    end_year: str
    is_current: bool
    duration: str


def normalize_month(token: Optional[str]) -> Optional[str]:
    """``"Jan"`` -> ``"January"``; ``""`` for no token; ``None`` if not a month."""
    if not token:
        return ""
    return _MONTH_LOOKUP.get(token.lower().rstrip("."))


def parse_date_range(text: str) -> Optional[DateRange]:
    """Parse a LinkedIn date line, or return ``None`` if it is not one."""
    match = _RANGE_RE.match(text.strip())
    if not match:
        return None
    start_month = normalize_month(match.group("sm"))
    end_month = normalize_month(match.group("em"))
    if start_month is None or end_month is None:
        return None
    duration = (match.group("dur") or "").strip()
    if match.group("pres"):
        return DateRange(start_month, match.group("sy"), "Present", "Present", True, duration)
    return DateRange(start_month, match.group("sy"), end_month, match.group("ey"), False, duration)


def visible_lines(element: Any) -> list[str]:
    """Visible text lines of a tag.

    LinkedIn duplicates text in ``span[aria-hidden]`` and a visually-hidden
    twin; we read the visible one and drop consecutive duplicates.
    """
    spans = element.select('span[aria-hidden="true"]')
    raw = [s.get_text(" ", strip=True) for s in spans] if spans else list(element.stripped_strings)
    lines: list[str] = []
    for text in raw:
        text = " ".join(text.split())
        if text and (not lines or lines[-1] != text):
            lines.append(text)
    return lines


def _first_date(lines: list[str]) -> tuple[int, Optional[DateRange]]:
    for index, line in enumerate(lines):
        parsed = parse_date_range(line)
        if parsed:
            return index, parsed
    return -1, None


def _clean_company(text: str) -> str:
    return text.split("·")[0].strip()


def _position_from_lines(lines: list[str], company: Optional[str] = None) -> Optional[Position]:
    index, dates = _first_date(lines)
    if dates is None:
        return None
    if company is None:
        company = _clean_company(lines[1]) if index >= 2 else ""
    return Position(
        title=lines[0] if index > 0 else "",
        company=company,
        start_month=dates.start_month,
        start_year=dates.start_year,
        end_month=dates.end_month,
        end_year=dates.end_year,
        duration=dates.duration,
        is_current=dates.is_current,
    )


def parse_experience_section(section: Any) -> list[Position]:
    """Return positions in the order shown on the page (most recent first)."""
    positions: list[Position] = []
    for item in section.find_all("li"):
        if item.find_parent("li") is not None:
            continue  # nested roles are handled by their company entry
        roles = [n for n in item.find_all("li") if _first_date(visible_lines(n))[1]]
        if roles:  # grouped: company header + several roles
            header = visible_lines(item)
            company = _clean_company(header[0]) if header else ""
            for role in roles:
                position = _position_from_lines(visible_lines(role), company=company)
                if position:
                    positions.append(position)
        else:
            position = _position_from_lines(visible_lines(item))
            if position:
                positions.append(position)
    return positions


def select_current_and_previous(
    positions: list[Position],
) -> tuple[Optional[Position], Optional[Position]]:
    """Choose current and previous roles without guessing.

    *Current* is the first listed position explicitly marked ``Present``;
    otherwise there is no current position. *Previous* is the next listed
    position (or the first one if nothing is ongoing).
    """
    if not positions:
        return None, None
    if positions[0].is_current:
        return positions[0], positions[1] if len(positions) > 1 else None
    return None, positions[0]
