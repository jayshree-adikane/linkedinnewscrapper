"""JSON-lines checkpoint so interrupted jobs can resume without duplicates."""
from __future__ import annotations

import json
from pathlib import Path

from scraper.models import COMPLETED_STATUSES, ProspectRecord


def load_completed(path: Path) -> dict[str, ProspectRecord]:
    """Return completed records keyed by lower-cased URL. Corrupt lines are ignored."""
    completed: dict[str, ProspectRecord] = {}
    if not path.exists():
        return completed
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = ProspectRecord.from_dict(json.loads(line))
            except (ValueError, TypeError):
                continue
            if record.status in COMPLETED_STATUSES:
                completed[record.url.lower()] = record
    return completed


def append_record(path: Path, record: ProspectRecord) -> None:
    """Append one completed record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def reset(path: Path) -> None:
    """Delete the checkpoint (fresh run)."""
    if path.exists():
        path.unlink()
