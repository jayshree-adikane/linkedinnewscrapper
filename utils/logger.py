"""Structured (JSON) logging with automatic secret redaction."""
from __future__ import annotations

import json
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

_SENSITIVE = re.compile(
    r"(li_at|jsessionid|bcookie|bscookie|liap|csrf-token|cookie|authorization|password)"
    r"\s*[=:]\s*[^\s;,]+",
    re.IGNORECASE,
)


class RedactingFilter(logging.Filter):
    """Masks cookie / token / password values before a record is emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = _SENSITIVE.sub(r"\1=[REDACTED]", record.getMessage())
        record.msg, record.args = message, ()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line; extra fields come from ``log_event``."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(
    name: str = "prospect_scraper", log_dir: Optional[Path] = None, level: int = logging.INFO
) -> logging.Logger:
    """Return a configured logger (idempotent, safe under Streamlit reruns)."""
    logger = logging.getLogger(name)
    if getattr(logger, "_lps_configured", False):
        return logger
    logger.setLevel(level)
    logger.propagate = False
    formatter = JsonFormatter()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / "scraper.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
            )
        )
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(RedactingFilter())
        logger.addHandler(handler)
    logger._lps_configured = True  # type: ignore[attr-defined]
    return logger


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Emit a structured event with key/value fields."""
    logger.log(level, event, extra={"fields": fields})
