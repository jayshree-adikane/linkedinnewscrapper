import pandas as pd
import pytest

from excel.excel_reader import (
    build_input_records,
    detect_url_column,
    read_excel_file,
    summarize_records,
)
from utils.exceptions import InputFileError
from utils.validators import normalize_profile_url

URLS = [
    "https://www.linkedin.com/in/alice/",
    "https://www.linkedin.com/in/Alice?trk=abc",  # duplicate of row 2 (case/query)
    "https://example.com/in/bob",
    None,
    "https://www.linkedin.com/company/acme/",
    "linkedin.com/in/carol",
]


def make_xlsx(tmp_path, data):
    path = tmp_path / "input.xlsx"
    pd.DataFrame(data).to_excel(path, index=False)
    return path


def test_normalize_profile_url():
    assert normalize_profile_url("https://in.linkedin.com/in/jane-doe/?x=1") == "https://www.linkedin.com/in/jane-doe/"
    assert normalize_profile_url("linkedin.com/in/jane") == "https://www.linkedin.com/in/jane/"
    assert normalize_profile_url("https://www.linkedin.com/company/x/") is None
    assert normalize_profile_url("") is None


def test_reads_detects_column_and_flags_rows(tmp_path):
    df = read_excel_file(make_xlsx(tmp_path, {"Name": list("abcdef"), "LinkedIn Profile URL": URLS}))
    column = detect_url_column(df)
    assert column == "LinkedIn Profile URL"
    records = build_input_records(df, column)
    assert [r.row_number for r in records] == [2, 3, 4, 5, 6, 7]
    assert records[0].processable and records[0].normalized_url == "https://www.linkedin.com/in/alice/"
    assert records[1].skip_category == "duplicate_url" and "row 2" in records[1].skip_reason
    assert records[2].skip_category == "invalid_url"
    assert records[3].skip_category == "empty_value"
    assert records[4].skip_category == "invalid_url"
    assert records[5].processable
    assert summarize_records(records) == {
        "total_rows": 6, "unique_valid": 2, "invalid": 2, "duplicates": 1, "empty": 1,
    }


def test_detects_unlabelled_column(tmp_path):
    df = read_excel_file(make_xlsx(tmp_path, {"A": ["x", "y"], "Col B": URLS[:1] + URLS[5:]}))
    assert detect_url_column(df) == "Col B"


def test_no_url_column_returns_none(tmp_path):
    df = read_excel_file(make_xlsx(tmp_path, {"A": ["x", "y"]}))
    assert detect_url_column(df) is None


def test_rejects_unsupported_and_corrupt_files(tmp_path):
    with pytest.raises(InputFileError):
        read_excel_file(b"a,b", "data.csv")
    with pytest.raises(InputFileError):
        read_excel_file(b"not really excel", "broken.xlsx")


def test_reads_bytes_upload(tmp_path):
    path = make_xlsx(tmp_path, {"URL": URLS[:1]})
    df = read_excel_file(path.read_bytes(), "upload.xlsx")
    assert len(df) == 1
