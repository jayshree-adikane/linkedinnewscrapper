from pathlib import Path

import pandas as pd
import pytest

from config import AppConfig
from excel.excel_reader import build_input_records
from scraper.access_checks import detect_access_issue
from scraper.job_runner import JobRunner, RunOptions
from scraper.models import STATUS_FAILED, STATUS_SKIPPED, STATUS_SUCCESS
from utils.exceptions import AccessBlockedError, ProfileUnavailableError, TemporaryFetchError
from utils.retry_handler import retry_with_backoff

HTML = (Path(__file__).parent / "fixtures" / "profile_full.html").read_text(encoding="utf-8")
URLS = [f"https://www.linkedin.com/in/p{i}/" for i in range(1, 4)]


def make_config(tmp_path):
    return AppConfig(output_dir=tmp_path / "out", log_dir=tmp_path / "logs", user_data_dir=tmp_path / "ud",
                     max_retries=2, backoff_base_seconds=0.0)


def records(urls=URLS):
    return build_input_records(pd.DataFrame({"URL": urls}), "URL")


def run(tmp_path, fetcher, urls=URLS, max_profiles=10, resume=True):
    runner = JobRunner(make_config(tmp_path), records(urls), RunOptions(max_profiles, 0.0, resume))
    runner.run_with_fetcher(fetcher)
    return runner, runner.snapshot()


def test_processes_in_order_and_writes_outputs(tmp_path):
    runner, snap = run(tmp_path, lambda url: HTML)
    assert [r.status for r in snap["results"]] == [STATUS_SUCCESS] * 3
    assert [r.row_number for r in snap["results"]] == [2, 3, 4]
    assert runner.config.output_path.exists() and runner.config.errors_path.exists()
    assert snap["status"] == "finished"


def test_limit_and_invalid_rows(tmp_path):
    _, snap = run(tmp_path, lambda url: HTML, urls=URLS + ["junk", URLS[0]], max_profiles=2)
    statuses = [(r.status, r.error_category) for r in snap["results"]]
    assert statuses[:2] == [(STATUS_SUCCESS, "")] * 2
    assert statuses[2] == (STATUS_SKIPPED, "limit_reached")
    assert statuses[3] == (STATUS_SKIPPED, "invalid_url")
    assert statuses[4] == (STATUS_SKIPPED, "duplicate_url")


def test_captcha_halts_run_and_skips_rest(tmp_path):
    calls = []

    def fetcher(url):
        calls.append(url)
        if len(calls) == 2:
            raise AccessBlockedError("captcha", "CAPTCHA appeared")
        return HTML

    _, snap = run(tmp_path, fetcher)
    assert len(calls) == 2  # third profile never visited
    assert snap["results"][1].status == STATUS_FAILED and snap["results"][1].error_category == "captcha"
    assert snap["results"][2].status == STATUS_SKIPPED
    assert snap["status"] == "stopped" and "captcha" in snap["stop_reason"]


def test_temporary_errors_are_retried_then_succeed(tmp_path):
    attempts = {"n": 0}

    def flaky(url):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TemporaryFetchError("timeout")
        return HTML

    _, snap = run(tmp_path, flaky, urls=URLS[:1])
    assert attempts["n"] == 3 and snap["results"][0].status == STATUS_SUCCESS


def test_retry_limit_is_strict(tmp_path):
    attempts = {"n": 0}

    def always_fails(url):
        attempts["n"] += 1
        raise TemporaryFetchError("timeout")

    _, snap = run(tmp_path, always_fails, urls=URLS[:1])
    assert attempts["n"] == 3  # 1 try + 2 retries
    assert snap["results"][0].error_category == "temporary_failure"


def test_unavailable_profile_is_failed_but_run_continues(tmp_path):
    def fetcher(url):
        if url.endswith("p1/"):
            raise ProfileUnavailableError("not available")
        return HTML

    _, snap = run(tmp_path, fetcher)
    assert snap["results"][0].error_category == "profile_unavailable"
    assert snap["results"][1].status == STATUS_SUCCESS


def test_resume_does_not_revisit_completed(tmp_path):
    run(tmp_path, lambda url: HTML)
    calls = []
    _, snap = run(tmp_path, lambda url: calls.append(url) or HTML)
    assert calls == [] and [r.status for r in snap["results"]] == [STATUS_SUCCESS] * 3


def test_retry_helper_only_retries_listed_errors():
    with pytest.raises(ValueError):
        retry_with_backoff(lambda: (_ for _ in ()).throw(ValueError("x")), max_retries=3, base_delay=0)


def test_access_issue_detection():
    assert detect_access_issue("https://www.linkedin.com/checkpoint/challenge/abc") == "captcha"
    assert detect_access_issue("https://www.linkedin.com/authwall?trk=x") == "login_required"
    assert detect_access_issue("https://www.linkedin.com/in/login-guy/") is None  # slug is not a login page
    assert detect_access_issue("https://www.linkedin.com/in/x/", status=429) == "rate_limited"
    assert detect_access_issue("https://www.linkedin.com/in/x/", status=999) == "access_denied"
    assert detect_access_issue("https://www.linkedin.com/in/x/", html="<p>Let's do a quick security check</p>") == "captcha"
