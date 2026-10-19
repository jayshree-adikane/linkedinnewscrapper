"""Alternative workflow: import user-authorized exports / manually collected data.

Use this when automated extraction is not permitted or a profile is not
accessible. The workbook must use the same column headers as the Prospects
sheet (only ``LinkedIn Profile URL`` is mandatory); matching is case-insensitive.
"""
from __future__ import annotations

import pandas as pd

from excel.excel_reader import Source, read_excel_file
from scraper.models import (
    PROSPECT_COLUMNS,
    STATUS_INCOMPLETE,
    STATUS_SUCCESS,
    ProspectRecord,
)
from utils.exceptions import InputFileError
from utils.validators import normalize_profile_url


def import_prospect_export(source: Source, filename: str) -> list[ProspectRecord]:
    """Convert a manually prepared workbook into ``ProspectRecord`` objects."""
    df = read_excel_file(source, filename)
    lookup = {h.lower(): attr for h, attr in PROSPECT_COLUMNS if attr != "row_number"}
    lookup.update({"url": "url", "linkedin url": "url", "profile url": "url"})
    mapping = {col: lookup[str(col).strip().lower()] for col in df.columns if str(col).strip().lower() in lookup}
    if "url" not in mapping.values():
        raise InputFileError("The workbook needs a 'LinkedIn Profile URL' column.")

    records: list[ProspectRecord] = []
    for position, (_, row) in enumerate(df.iterrows()):
        values = {
            attr: ("" if pd.isna(row[col]) else str(row[col]).strip()) for col, attr in mapping.items()
        }
        url = normalize_profile_url(values.get("url", "")) or values.get("url", "")
        record = ProspectRecord(row_number=position + 2, url=url)
        for attr, value in values.items():
            if attr not in {"url", "status", "error_message"}:
                setattr(record, attr, value)
        core = [record.full_name, record.current_title, record.current_company, record.location]
        if all(core):
            record.status = STATUS_SUCCESS
        else:
            record.status = STATUS_INCOMPLETE
            record.error_message = "Imported from user-provided data; some fields are blank"
        records.append(record)
    return records
