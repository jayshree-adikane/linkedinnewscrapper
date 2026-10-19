"""Sequential, stoppable, resumable extraction job (runs in a background thread)."""
from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Optional

from config import AppConfig
from excel.excel_writer import write_errors_workbook, write_workbook
from scraper import checkpoint
from scraper.access_checks import STOP_CATEGORIES  # noqa: F401  (documented contract)
from scraper.extraction_service import ExtractionService, Fetcher
from scraper.models import (
    COMPLETED_STATUSES,
    STATUS_FAILED,
    STATUS_SKIPPED,
    InputRecord,
    ProspectRecord,
    RunInfo,
)
from utils.exceptions import (
    AccessBlockedError,
    BrowserSetupError,
    RunStopped,
    TemporaryFetchError,
)
from utils.logger import get_logger, log_event
from utils.rate_limiter import RateLimiter
from utils.retry_handler import retry_with_backoff


@dataclass(frozen=True)
class RunOptions:
    """User-selected limits for one run."""

    max_profiles: int
    delay_seconds: float
    resume: bool = True


def _skipped(rec: InputRecord, category: str, message: str) -> ProspectRecord:
    return ProspectRecord(
        rec.row_number, rec.normalized_url or rec.raw_url,
        status=STATUS_SKIPPED, error_category=category, error_message=message,
    )


class JobRunner:
    """Processes records one at a time, in input order."""

    def __init__(self, config: AppConfig, input_records: list[InputRecord], options: RunOptions) -> None:
        self.config = config
        self.input_records = list(input_records)
        self.options = options
        self.logger = get_logger(log_dir=config.log_dir)
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._results: list[ProspectRecord] = []
        self._thread: Optional[threading.Thread] = None
        self.status = "idle"
        self.message = ""
        self.stop_reason = ""
        self.run_info = RunInfo(
            total_input=len(self.input_records),
            unique_urls=sum(r.processable for r in self.input_records),
        )

    # ---- public API -------------------------------------------------------
    def start(self) -> None:
        """Launch the job in a daemon thread."""
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="extraction-job")
        self._thread.start()

    def request_stop(self) -> None:
        """Ask the job to stop safely after the current profile."""
        self.stop_event.set()
        self._set("stopping", "Stopping after the current profile...")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def snapshot(self) -> dict[str, Any]:
        """Thread-safe view of the current state for the UI."""
        with self._lock:
            return {
                "status": self.status,
                "message": self.message,
                "stop_reason": self.stop_reason,
                "results": list(self._results),
                "done": len(self._results),
                "total": len(self.input_records),
                "run_info": self.run_info,
            }

    def run_with_fetcher(self, fetcher: Fetcher) -> None:
        """Run the whole job with the given fetcher, then finalise outputs."""
        self.run_info.started_at = self.run_info.started_at or datetime.now()
        self._set("running", "Processing profiles...")
        try:
            self.run_batch(fetcher)
        finally:
            self._finalize()

    # ---- internals --------------------------------------------------------
    def _set(self, status: str, message: str = "") -> None:
        with self._lock:
            self.status, self.message = status, message

    def _add(self, record: ProspectRecord) -> None:
        with self._lock:
            self._results.append(record)

    def run_batch(self, fetcher: Fetcher) -> None:
        """Core loop: appends exactly one result per input record, in order."""
        cfg, opts = self.config, self.options
        service = ExtractionService(fetcher)
        limiter = RateLimiter(opts.delay_seconds)
        if opts.resume:
            completed = checkpoint.load_completed(cfg.checkpoint_path)
        else:
            checkpoint.reset(cfg.checkpoint_path)
            completed = {}
        visits = 0
        halt: Optional[tuple[str, str]] = None

        for rec in self.input_records:
            if not rec.processable:
                self._add(_skipped(rec, rec.skip_category, rec.skip_reason))
                continue
            if halt:
                self._add(_skipped(rec, halt[0], halt[1]))
                continue
            previous = completed.get(rec.key)
            if previous:
                self._add(replace(previous, row_number=rec.row_number))
                continue
            if visits >= opts.max_profiles:
                self._add(_skipped(rec, "limit_reached", f"Per-run limit of {opts.max_profiles} profiles reached"))
                continue
            if self.stop_event.is_set() or not limiter.wait(self.stop_event):
                halt = ("stopped_by_user", "Stopped by user")
                self.stop_reason = halt[1]
                self._add(_skipped(rec, *halt))
                continue

            record, halt = self._process_one(rec, service)
            limiter.mark()
            visits += 1
            if halt:
                self.stop_reason = halt[1]
            if record.status in COMPLETED_STATUSES:
                checkpoint.append_record(cfg.checkpoint_path, record)
            self._add(record)
            self._set("running", f"Processed {visits} profile(s) this run")

    def _process_one(
        self, rec: InputRecord, service: ExtractionService
    ) -> tuple[ProspectRecord, Optional[tuple[str, str]]]:
        url = rec.normalized_url or rec.raw_url
        try:
            record = retry_with_backoff(
                lambda: service.extract(rec),
                max_retries=self.config.max_retries,
                base_delay=self.config.backoff_base_seconds,
                stop_event=self.stop_event,
                logger=self.logger,
            )
            log_event(self.logger, "profile_processed", row=rec.row_number, status=record.status)
            return record, None
        except AccessBlockedError as exc:
            log_event(self.logger, "run_halted", row=rec.row_number, category=exc.category)
            failed = ProspectRecord(
                rec.row_number, url, status=STATUS_FAILED,
                error_category=exc.category, error_message=str(exc),
            )
            return failed, ("run_halted", f"Run halted ({exc.category}): {exc}")
        except RunStopped:
            return _skipped(rec, "stopped_by_user", "Stopped by user"), ("stopped_by_user", "Stopped by user")
        except TemporaryFetchError as exc:
            return (
                ProspectRecord(
                    rec.row_number, url, status=STATUS_FAILED,
                    error_category="temporary_failure",
                    error_message=f"Gave up after {self.config.max_retries} retries: {exc}",
                ),
                None,
            )
        except Exception as exc:  # never let one profile crash the job
            self.logger.exception("unexpected error on row %s", rec.row_number)
            return (
                ProspectRecord(
                    rec.row_number, url, status=STATUS_FAILED,
                    error_category="unexpected_error", error_message=type(exc).__name__,
                ),
                None,
            )

    def _finalize(self) -> None:
        """Skip anything unprocessed, stamp end time and write the workbooks."""
        with self._lock:
            for rec in self.input_records[len(self._results):]:
                self._results.append(_skipped(rec, "not_processed", self.stop_reason or "Run ended early"))
            results = list(self._results)
        self.run_info.finished_at = datetime.now()
        self.run_info.stop_reason = self.stop_reason
        try:
            self.config.ensure_dirs()
            write_workbook(self.config.output_path, results, self.run_info)
            write_errors_workbook(self.config.errors_path, results)
            note = f"Saved {self.config.output_path.name}"
        except OSError as exc:
            note = f"Could not save workbook ({type(exc).__name__}); is it open in Excel? Use the download buttons."
        final = "stopped" if self.stop_reason else "finished"
        self._set(final, f"{self.stop_reason + '. ' if self.stop_reason else ''}{note}")

    def _thread_main(self) -> None:
        """Open the browser, wait for manual login, then run the batch."""
        from browser.browser_manager import BrowserManager
        from browser.profile_page import ProfilePage
        from browser.session_manager import SessionManager

        self.run_info.started_at = datetime.now()
        try:
            with BrowserManager(self.config) as browser:
                self._set("waiting_login", "Opening browser...")
                session = SessionManager(browser.page, self.config, self.logger)
                if not session.ensure_login(self.stop_event, lambda m: self._set("waiting_login", m)):
                    self.stop_reason = "Login was not completed"
                    self._finalize()
                    return
                self.run_with_fetcher(ProfilePage(
                    browser.page, self.config.page_timeout_ms, debug_dir=self.config.log_dir / "debug"
                ).open)
        except BrowserSetupError as exc:
            self.stop_reason = str(exc)
            self._finalize()
            self._set("error", str(exc))
        except Exception as exc:
            self.logger.exception("job crashed")
            self.stop_reason = f"Unexpected error: {type(exc).__name__}"
            self._finalize()
