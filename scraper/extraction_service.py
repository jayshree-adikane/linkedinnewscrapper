"""Turns one input record into one ``ProspectRecord`` using an injected fetcher."""
from __future__ import annotations

from typing import Callable

from scraper.employment_parser import select_current_and_previous
from scraper.models import (
    STATUS_FAILED,
    STATUS_INCOMPLETE,
    STATUS_SUCCESS,
    InputRecord,
    ParsedProfile,
    ProspectRecord,
)
from scraper.profile_parser import parse_profile_html
from utils.exceptions import ProfileUnavailableError

Fetcher = Callable[[str], str]


def build_prospect_record(rec: InputRecord, parsed: ParsedProfile) -> ProspectRecord:
    """Map parsed data to the output record; never invents missing values."""
    url = rec.normalized_url or rec.raw_url
    if not parsed.full_name and not parsed.positions:
        return ProspectRecord(
            rec.row_number,
            url,
            status=STATUS_FAILED,
            error_category="parse_error",
            error_message="No name or experience found (limited view or selectors changed)",
        )
    current, previous = select_current_and_previous(parsed.positions)
    out = ProspectRecord(rec.row_number, url, full_name=parsed.full_name, location=parsed.location)
    if current:
        out.current_title, out.current_company = current.title, current.company
        out.current_start_month, out.current_start_year = current.start_month, current.start_year
        out.current_end_month, out.current_end_year = current.end_month, current.end_year
        out.employment_duration = current.duration
    if previous:
        out.previous_title, out.previous_company = previous.title, previous.company
        out.previous_start, out.previous_end = previous.start_label, previous.end_label
    missing = [
        label
        for label, ok in (
            ("full name", parsed.full_name),
            ("location", parsed.location),
            ("current (ongoing) position", current),
        )
        if not ok
    ]
    if missing:
        out.status = STATUS_INCOMPLETE
        out.error_category = "incomplete_data"
        out.error_message = "Not available on page: " + ", ".join(missing)
    else:
        out.status = STATUS_SUCCESS
    return out


class ExtractionService:
    """Fetch + parse. ``fetcher`` maps a URL to HTML (Playwright, or a mock in tests)."""

    def __init__(self, fetcher: Fetcher, parser: Callable[[str], ParsedProfile] = parse_profile_html) -> None:
        self.fetcher = fetcher
        self.parser = parser

    def extract(self, rec: InputRecord) -> ProspectRecord:
        """Extract one profile. Retryable/blocking errors propagate to the caller."""
        url = rec.normalized_url or rec.raw_url
        try:
            html = self.fetcher(url)
        except ProfileUnavailableError as exc:
            return ProspectRecord(
                rec.row_number, url, status=STATUS_FAILED,
                error_category="profile_unavailable", error_message=str(exc),
            )
        try:
            parsed = self.parser(html)
        except Exception as exc:  # parser must not kill the run
            return ProspectRecord(
                rec.row_number, url, status=STATUS_FAILED,
                error_category="parse_error", error_message=f"Parser error: {type(exc).__name__}",
            )
        return build_prospect_record(rec, parsed)
