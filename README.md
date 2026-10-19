# LinkedIn Prospect Data Extractor (Python + Playwright + Streamlit)

Reads an Excel file of LinkedIn profile URLs, opens each profile **one at a time in a browser you
signed into yourself**, extracts the fields visible to your account, and writes
`linkedin_prospects_output.xlsx` (sheets: **Prospects**, **Errors**, **Summary**).

## Read this first: compliance and limits

* LinkedIn's terms restrict automated access. Use this tool only where you are permitted to, on
  profiles you are authorised to view, at low volume. You are responsible for that decision.
* You log in manually. No password is ever stored; cookies live only in the local browser profile
  folder (`.browser-profile/`) and are never shown or logged (log lines are also redacted).
* CAPTCHA, login wall, access denied or a rate-limit warning **stops the whole run**. Nothing is
  bypassed: no proxies, no CAPTCHA solving, no behaviour imitation (the delay is a fixed value).
* If automation is not permitted for you, use the **Import authorised export** tab (no browser).

## Windows 10/11 setup (PowerShell)

```powershell
cd linkedin-prospect-scraper
py -3.10 -m venv .venv            # Python 3.10+ required
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process Bypass
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
```

## Run

```powershell
streamlit run app.py
```

1. Upload the `.xlsx` / `.xls` file and confirm the URL column (auto-detected).
2. Set **max profiles** and **delay** (defaults 25 and 10 s; minimum delay 5 s) in the sidebar.
3. Click **Dry run** to validate the file without opening a browser.
4. Click **Start**. Chromium opens; sign in to LinkedIn yourself (complete 2FA/CAPTCHA yourself).
   The app waits, then processes profiles sequentially.
5. **Stop safely** finishes the current profile then stops. Download the workbook and the error
   report at any time after the run ends. Files are also saved in `output/`.

Resume: results of completed profiles are kept in `output/checkpoint.jsonl`. With "Resume" ticked,
a new run skips them (no duplicates) and retries only failed/unprocessed rows. Untick it to start fresh.

Run tests: `pytest`

Optional environment variables: `LPS_MAX_PROFILES`, `LPS_DELAY_SECONDS`, `LPS_MIN_DELAY_SECONDS`,
`LPS_MAX_PROFILES_HARD_CAP`, `LPS_PAGE_TIMEOUT_MS`, `LPS_MAX_RETRIES`, `LPS_BACKOFF_BASE_SECONDS`,
`LPS_HEADLESS`, `LPS_OUTPUT_DIR`, `LPS_LOG_DIR`, `LPS_USER_DATA_DIR`.

## Output rules

| Field | Notes |
|---|---|
| Full name, Location | From the profile header as displayed. Blank if not shown. |
| Current job (title, company, start/end month and year, duration) | Only when the first listed role is explicitly marked **Present**. End month/year are then `Present`. If no role is ongoing, current fields stay blank and the row is **Incomplete**. |
| Previous job | The next role listed after the current one (or the first role if none is ongoing). Start/end are shown as `Month Year`. |
| Dates | Never guessed. Year-only dates keep the month blank. English month names and "Present" only. |
| Status | `Success`, `Incomplete` (page loaded, fields missing), `Failed` (visit failed), `Skipped` (invalid/duplicate/empty URL, per-run limit, or run stopped). |

Fields that may be unavailable: anything hidden by profile privacy or your connection degree,
roles under "Show all experiences" (the profile page lists only the first few; this tool does not
open the detail page), and non-English month names.

## Project layout

`app.py` UI · `config.py` settings · `browser/` Playwright, login wait, page object, selectors ·
`scraper/` parsers, extraction service, job runner, checkpoint · `excel/` reader, writer, manual import ·
`utils/` rate limiter, retries, logging, validators · `tests/` unit tests with saved HTML fixtures.

## Testing the parser on your own saved pages

Save a profile you are authorised to view (browser > Save page as > "Webpage, HTML only" after the
page fully loads) into `tests/fixtures/`, then:

```python
from scraper.profile_parser import parse_profile_html
print(parse_profile_html(open("tests/fixtures/mine.html", encoding="utf-8").read()))
```

## Troubleshooting

* **Browser won't start / "Executable doesn't exist"**: run `python -m playwright install chromium`
  inside the activated venv.
* **`streamlit` or `playwright` not recognised**: activate the venv (`.\.venv\Scripts\Activate.ps1`).
* **Excel parsing errors**: `.xlsx` needs `openpyxl`, `.xls` needs `xlrd`; both are in
  requirements. Password-protected or `.xlsb`/`.csv` files are rejected; re-save as `.xlsx`.
  Close the output workbook in Excel before a run ends, or the save fails (use the download buttons).
* **"No valid LinkedIn profile URLs"**: URLs must look like `https://www.linkedin.com/in/<name>/`
  (company, school and search URLs are rejected).
* **Many `Incomplete` rows / missing fields**: the profile may hide them, or markup changed.
  Save the page and run the parser snippet above to see what is detected.
* **Selector changes**: update the lists in `browser/selectors.py` (name, location, Experience anchor);
  role parsing lives in `scraper/employment_parser.py`. Add a new saved-HTML fixture and test first.
* **Run halted (captcha / login_required / rate_limited)**: resolve it manually in the browser, wait,
  lower the profile count, raise the delay, and start again; resume skips completed profiles.
* **Login timeout**: finish signing in within 5 minutes (`LPS_LOGIN_TIMEOUT_SECONDS`).

## Alternative workflow (no scraping)

Open the **Import authorised export** tab, upload a workbook with the Prospects column headers
(only `LinkedIn Profile URL` is mandatory), and download the formatted 3-sheet workbook.
