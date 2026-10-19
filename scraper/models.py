"""Shared data models."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Any, Optional

STATUS_SUCCESS = "Success"
STATUS_INCOMPLETE = "Incomplete"
STATUS_FAILED = "Failed"
STATUS_SKIPPED = "Skipped"
COMPLETED_STATUSES = (STATUS_SUCCESS, STATUS_INCOMPLETE)

# (Excel header, ProspectRecord attribute) in output order.
PROSPECT_COLUMNS: list[tuple[str, str]] = [
    ("Original Row", "row_number"),
    ("Full Name", "full_name"),
    ("Current Job Title", "current_title"),
    ("Current Company", "current_company"),
    ("Current Job Start Month", "current_start_month"),
    ("Current Job Start Year", "current_start_year"),
    ("Current Job End Month", "current_end_month"),
    ("Current Job End Year", "current_end_year"),
    ("Employment Duration", "employment_duration"),
    ("Previous Job Title", "previous_title"),
    ("Previous Company", "previous_company"),
    ("Previous Job Start (Month Year)", "previous_start"),
    ("Previous Job End (Month Year)", "previous_end"),
    ("Location", "location"),
    ("LinkedIn Profile URL", "url"),
    ("Processing Status", "status"),
    ("Error Message", "error_message"),
]


@dataclass(frozen=True)
class InputRecord:
    """One row of the uploaded workbook."""

    row_number: int
    raw_url: str
    normalized_url: Optional[str] = None
    skip_category: str = ""
    skip_reason: str = ""

    @property
    def processable(self) -> bool:
        return not self.skip_category

    @property
    def key(self) -> str:
        """Case-insensitive identity used for de-duplication and resume."""
        return (self.normalized_url or "").lower()


@dataclass
class Position:
    """A single job entry from the Experience section."""

    title: str = ""
    company: str = ""
    start_month: str = ""
    start_year: str = ""
    end_month: str = ""
    end_year: str = ""
    duration: str = ""
    is_current: bool = False

    @property
    def start_label(self) -> str:
        return " ".join(p for p in (self.start_month, self.start_year) if p)

    @property
    def end_label(self) -> str:
        if self.is_current:
            return "Present"
        return " ".join(p for p in (self.end_month, self.end_year) if p)


@dataclass
class ParsedProfile:
    """Raw parser output for one profile page."""

    full_name: str = ""
    location: str = ""
    positions: list[Position] = field(default_factory=list)


@dataclass
class ProspectRecord:
    """Final per-profile result written to Excel."""

    row_number: int
    url: str
    full_name: str = ""
    current_title: str = ""
    current_company: str = ""
    current_start_month: str = ""
    current_start_year: str = ""
    current_end_month: str = ""
    current_end_year: str = ""
    employment_duration: str = ""
    previous_title: str = ""
    previous_company: str = ""
    previous_start: str = ""
    previous_end: str = ""
    location: str = ""
    status: str = STATUS_SUCCESS
    error_category: str = ""
    error_message: str = ""

    def to_row(self) -> dict[str, Any]:
        """Map to ``{Excel header: value}`` in output order."""
        return {header: getattr(self, attr) for header, attr in PROSPECT_COLUMNS}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProspectRecord":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class RunInfo:
    """Metadata for the Summary sheet."""

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    total_input: int = 0
    unique_urls: int = 0
    stop_reason: str = ""
