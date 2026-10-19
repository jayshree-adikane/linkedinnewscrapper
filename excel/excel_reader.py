"""Read and validate the uploaded Excel workbook of profile URLs."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from scraper.models import InputRecord
from utils.exceptions import InputFileError
from utils.validators import is_valid_profile_url, normalize_profile_url

SUPPORTED_EXTENSIONS = {".xlsx": "openpyxl", ".xls": "xlrd"}
_NAME_HINTS = ("linkedin", "profile", "url", "link")

Source = Union[str, Path, bytes, io.BytesIO]


def read_excel_file(source: Source, filename: Optional[str] = None) -> pd.DataFrame:
    """Load the first worksheet as text. Raises ``InputFileError`` on any problem."""
    name = filename or (str(source) if isinstance(source, (str, Path)) else "")
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise InputFileError("Unsupported file type. Please upload an .xlsx or .xls file.")
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    try:
        df = pd.read_excel(source, dtype=str, engine=SUPPORTED_EXTENSIONS[suffix])
    except ImportError as exc:
        raise InputFileError(f"Missing Excel engine for {suffix} files: {exc}") from exc
    except Exception as exc:  # corrupt file, password protected, wrong format...
        raise InputFileError(f"Could not read the Excel file: {exc}") from exc
    df = df.dropna(how="all")
    if df.empty or len(df.columns) == 0:
        raise InputFileError("The Excel file contains no data rows.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def detect_url_column(df: pd.DataFrame) -> Optional[str]:
    """Pick the column most likely to hold LinkedIn profile URLs, or ``None``."""
    best: Optional[str] = None
    best_score = (0, 0)
    for column in df.columns:
        valid = int(df[column].map(is_valid_profile_url).sum())
        if valid == 0:
            continue
        hinted = int(any(h in str(column).lower() for h in _NAME_HINTS))
        if (valid, hinted) > best_score:
            best, best_score = column, (valid, hinted)
    return best


def build_input_records(df: pd.DataFrame, column: str) -> list[InputRecord]:
    """Create one ``InputRecord`` per row, preserving order and row numbers.

    Row numbers match Excel (header is row 1). Empty, invalid and duplicate rows
    are kept in the list but flagged with a ``skip_category``.
    """
    if column not in df.columns:
        raise InputFileError(f"Column '{column}' not found in the workbook.")
    records: list[InputRecord] = []
    first_seen: dict[str, int] = {}
    for position, raw in enumerate(df[column].tolist()):
        row = position + 2
        text = "" if pd.isna(raw) else str(raw).strip()
        if not text:
            records.append(InputRecord(row, "", None, "empty_value", "Empty URL cell"))
            continue
        normalized = normalize_profile_url(text)
        if normalized is None:
            records.append(
                InputRecord(row, text, None, "invalid_url", "Not a LinkedIn profile URL (/in/...)")
            )
            continue
        key = normalized.lower()
        if key in first_seen:
            records.append(
                InputRecord(
                    row, text, normalized, "duplicate_url", f"Duplicate of row {first_seen[key]}"
                )
            )
            continue
        first_seen[key] = row
        records.append(InputRecord(row, text, normalized))
    return records


def summarize_records(records: list[InputRecord]) -> dict[str, int]:
    """Counts used by the dry-run report."""
    return {
        "total_rows": len(records),
        "unique_valid": sum(r.processable for r in records),
        "invalid": sum(r.skip_category == "invalid_url" for r in records),
        "duplicates": sum(r.skip_category == "duplicate_url" for r in records),
        "empty": sum(r.skip_category == "empty_value" for r in records),
    }
