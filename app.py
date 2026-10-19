"""Streamlit UI. Run with:  streamlit run app.py"""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from config import AppConfig
from excel.excel_reader import (
    SUPPORTED_EXTENSIONS,
    build_input_records,
    detect_url_column,
    read_excel_file,
    summarize_records,
)
from excel.excel_writer import errors_workbook_bytes, workbook_bytes
from excel.manual_import import import_prospect_export
from scraper.job_runner import JobRunner, RunOptions
from scraper.models import STATUS_SKIPPED, RunInfo
from utils.exceptions import InputFileError

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
config = AppConfig.from_env()
config.ensure_dirs()

st.set_page_config(page_title="LinkedIn Prospect Extractor", layout="wide")
st.title("LinkedIn Prospect Data Extractor")
st.info(
    "Use only with profiles you are authorised to access, and make sure your use complies "
    "with LinkedIn's terms. You sign in manually; CAPTCHAs, login walls and rate limits stop "
    "the run and are never bypassed. No passwords or cookies are stored by this app."
)


@st.cache_data(show_spinner=False)
def load_workbook_df(data: bytes, filename: str) -> pd.DataFrame:
    return read_excel_file(data, filename)


def render_results(runner: JobRunner) -> None:
    snap = runner.snapshot()
    st.progress(snap["done"] / max(snap["total"], 1), text=f"{snap['done']} / {snap['total']} rows  ·  {snap['status']}")
    if snap["message"]:
        st.write(snap["message"])
    rows = [r.to_row() for r in snap["results"] if r.status != STATUS_SKIPPED]
    if rows:
        st.subheader("Collected records")
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    if not runner.is_running() and snap["status"] in {"finished", "stopped", "error"}:
        info: RunInfo = snap["run_info"]
        c1, c2 = st.columns(2)
        c1.download_button("Download workbook (.xlsx)", workbook_bytes(snap["results"], info),
                           config.output_filename, XLSX_MIME)
        c2.download_button("Download error report (.xlsx)", errors_workbook_bytes(snap["results"]),
                           config.errors_filename, XLSX_MIME)


tab_extract, tab_import = st.tabs(["Extract from profiles", "Import authorised export (no browser)"])

with tab_extract:
    with st.sidebar:
        st.header("Run limits")
        max_profiles = st.number_input("Max profiles per run", 1, config.max_profiles_hard_cap,
                                       min(config.max_profiles_default, config.max_profiles_hard_cap))
        delay = st.number_input("Delay between visits (seconds)", float(config.min_delay_seconds), 300.0,
                                float(max(config.delay_seconds, config.min_delay_seconds)), step=1.0)
        resume = st.checkbox("Resume (skip profiles already completed)", value=True)

    upload = st.file_uploader("Excel file with LinkedIn profile URLs", type=[e[1:] for e in SUPPORTED_EXTENSIONS])
    runner: JobRunner | None = st.session_state.get("runner")
    busy = bool(runner and runner.is_running())

    if upload is not None:
        try:
            df = load_workbook_df(upload.getvalue(), upload.name)
        except InputFileError as exc:
            st.error(str(exc))
            df = None
    if upload is not None and df is not None:
        detected = detect_url_column(df)
        columns = list(df.columns)
        column = st.selectbox("URL column", columns, index=columns.index(detected) if detected else 0)
        records = build_input_records(df, column)
        stats = summarize_records(records)
        m = st.columns(5)
        for box, (label, key) in zip(m, [("Rows", "total_rows"), ("Unique valid", "unique_valid"),
                                         ("Invalid", "invalid"), ("Duplicates", "duplicates"), ("Empty", "empty")]):
            box.metric(label, stats[key])
        if stats["unique_valid"] == 0:
            st.warning("No valid LinkedIn profile URLs (https://www.linkedin.com/in/...) in this column.")

        b1, b2, b3 = st.columns(3)
        if b1.button("Dry run (validate only)", disabled=busy):
            st.success(f"Dry run OK: {min(stats['unique_valid'], int(max_profiles))} profile(s) would be visited "
                       f"this run. No browser was opened.")
            st.dataframe(pd.DataFrame([{"Row": r.row_number, "URL": r.normalized_url or r.raw_url,
                                        "Result": r.skip_reason or "Will process"} for r in records]),
                         use_container_width=True)
        if b2.button("Start", type="primary", disabled=busy or stats["unique_valid"] == 0):
            runner = JobRunner(config, records, RunOptions(int(max_profiles), float(delay), resume))
            runner.start()
            st.session_state["runner"] = runner
            st.rerun()
        if b3.button("Stop safely", disabled=not busy):
            runner.request_stop()

    if runner is not None:
        render_results(runner)
        if runner.is_running():
            time.sleep(1.5)
            st.rerun()

with tab_import:
    st.write(
        "No scraping: upload a workbook you collected manually or exported with permission. "
        "Use the same headers as the Prospects sheet (only **LinkedIn Profile URL** is required)."
    )
    imp = st.file_uploader("Prospect workbook", type=["xlsx", "xls"], key="import")
    if imp is not None:
        try:
            imported = import_prospect_export(imp.getvalue(), imp.name)
        except InputFileError as exc:
            st.error(str(exc))
        else:
            st.dataframe(pd.DataFrame([r.to_row() for r in imported]), use_container_width=True)
            info = RunInfo(total_input=len(imported), unique_urls=len(imported))
            st.download_button("Download formatted workbook", workbook_bytes(imported, info),
                               config.output_filename, XLSX_MIME)
