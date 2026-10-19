from pathlib import Path

from scraper.employment_parser import parse_date_range, select_current_and_previous
from scraper.extraction_service import build_prospect_record
from scraper.models import STATUS_FAILED, STATUS_INCOMPLETE, STATUS_SUCCESS, InputRecord
from scraper.profile_parser import parse_profile_html

FIXTURES = Path(__file__).parent / "fixtures"
REC = InputRecord(2, "https://www.linkedin.com/in/x/", "https://www.linkedin.com/in/x/")


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_date_range_variants():
    r = parse_date_range("Mar 2021 - Present · 5 yrs 7 mos")
    assert (r.start_month, r.start_year, r.end_month, r.end_year, r.is_current, r.duration) == (
        "March", "2021", "Present", "Present", True, "5 yrs 7 mos")
    r = parse_date_range("2015 – Dec 2019 · 5 yrs")
    assert (r.start_month, r.start_year, r.end_month, r.end_year, r.is_current) == ("", "2015", "December", "2019", False)
    assert parse_date_range("Sept 2010 to Oct 2011").start_month == "September"
    assert parse_date_range("Pune, Maharashtra, India") is None
    assert parse_date_range("Foo 2020 - 2021") is None  # not a month: never guessed


def test_full_profile_flat_and_grouped_roles():
    parsed = parse_profile_html(load("profile_full.html"))
    assert parsed.full_name == "Jane Doe"
    assert parsed.location == "Pune, Maharashtra, India"
    assert [(p.title, p.company) for p in parsed.positions] == [
        ("Senior Data Engineer", "Acme Analytics"),
        ("Data Engineer", "Globex Corporation"),
        ("Junior Analyst", "Globex Corporation"),
    ]
    rec = build_prospect_record(REC, parsed)
    assert rec.status == STATUS_SUCCESS and rec.error_message == ""
    assert (rec.current_title, rec.current_company) == ("Senior Data Engineer", "Acme Analytics")
    assert (rec.current_start_month, rec.current_start_year) == ("March", "2021")
    assert (rec.current_end_month, rec.current_end_year) == ("Present", "Present")
    assert rec.employment_duration == "5 yrs 7 mos"
    assert (rec.previous_title, rec.previous_company) == ("Data Engineer", "Globex Corporation")
    assert (rec.previous_start, rec.previous_end) == ("January 2018", "February 2021")


def test_no_current_position_is_incomplete_and_not_guessed():
    parsed = parse_profile_html(load("profile_no_current.html"))
    rec = build_prospect_record(REC, parsed)
    assert rec.status == STATUS_INCOMPLETE
    assert rec.current_title == "" and rec.current_end_year == ""  # no invented "Present"
    assert rec.location == ""
    assert "location" in rec.error_message and "current" in rec.error_message
    assert (rec.previous_title, rec.previous_company) == ("Business Analyst", "Initech")
    assert (rec.previous_start, rec.previous_end) == ("2015", "December 2019")


def test_limited_view_is_a_failed_parse():
    rec = build_prospect_record(REC, parse_profile_html(load("profile_limited.html")))
    assert rec.status == STATUS_FAILED and rec.error_category == "parse_error"


def test_select_current_and_previous_edge_cases():
    assert select_current_and_previous([]) == (None, None)
