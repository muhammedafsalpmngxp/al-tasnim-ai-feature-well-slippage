"""LLM token-expense log -- deliberately independent of the rest of this project.

Every real call to the LLM (never a cached one -- see below) appends one row
to ``llm_usage_log.xlsx``, next to this file, recording what it cost: the
provider and model, when it ran, how long it took, and how many input/output
(and cached-input) tokens it used. A live totals row -- ``TOTAL calls: N`` in
its first cell, a real Excel ``SUM``/``COUNTA`` formula in every numeric one
-- always sits directly beneath the data, so opening the file in Excel shows
a running expense total with zero manual work, no matter how many rows have
been logged. That is the whole point of this file: a plain, inspectable
running total of LLM expense that a person can open in Excel at any time,
sort, filter, and sum -- without touching the application at all.

**Why this lives at the project root, not inside ``backend/``.** This module
must keep working -- and keep being auditable -- independently of the
backend's own code, so a refactor inside ``backend/app`` can never silently
break, or silently stop, expense tracking. To make that independence real
rather than just a location, this file:

* never imports anything from ``backend/`` or ``frontend/`` -- no
  ``app.config.settings``, no ``app.services.*``, nothing;
* reads the provider and model directly from ``backend/.env`` itself, with
  its own tiny parser below, rather than going through the backend's
  settings module;
* accepts everything else it cannot know on its own -- token counts and how
  long the call took -- as plain arguments from whoever calls ``log_usage``.

The **only** file this module reads is ``backend/.env``. It performs no
database access and does not import any other module in this project.

**Two sources, and why both are here.** The per-call log above only ever sees
calls that went through this application while it was running. It cannot see a
call made by the test suite (which deliberately disables this tracker so a test
run never lands in a real expense file), nor anything else that spends tokens
on the same API key -- another tool, another machine, a colleague. Those are
real money and were invisible here.

So the workbook also carries what the provider itself reports, which is the
authoritative figure:

* **LLM Usage** -- one row per real call this application made. Per-call
  detail, including how long each call took, which no billing API reports.
* **OpenAI Usage** -- what OpenAI says was actually spent on the organisation,
  per day and per model, whoever or whatever spent it.
* **Reconciliation** -- the two side by side per day, with the difference
  spelled out, so the gap between "what this app logged" and "what was really
  billed" is a number you can read rather than a suspicion.

The last two are filled by ``python llm_usage_tracker.py sync``, which calls
OpenAI's organisation usage and cost endpoints. That needs an **admin** API
key (``sk-admin-...``, from Organization -> Admin keys) in ``backend/.env`` as
``OPENAI_ADMIN_KEY``: the ordinary ``LLM_API_KEY`` this app answers requests
with cannot read organisation usage, by design. Nothing syncs automatically --
it is an explicit command, so this module still makes no network call of its
own accord.

Usage (from anywhere, e.g. the backend's LLM client, right after a real,
successful call to the provider -- never for a cache hit, which spent no
tokens at all)::

    import llm_usage_tracker

    llm_usage_tracker.log_usage(
        input_tokens=812,
        output_tokens=143,
        input_cache_tokens=256,     # optional -- omit or pass None if unknown
        duration_seconds=1.94,
    )

This can also be run directly::

    python llm_usage_tracker.py           # print what it would record, and
                                          # whether the authoritative sync is
                                          # configured
    python llm_usage_tracker.py sync      # pull real usage/cost from OpenAI
    python llm_usage_tracker.py sync --days 60
"""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as date_type, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Border, Font, Side
    from openpyxl.utils import get_column_letter
except ImportError as _exc:  # pragma: no cover - environment problem, not a logic path
    Workbook = None  # type: ignore[assignment]
    load_workbook = None  # type: ignore[assignment]
    _IMPORT_ERROR = _exc
else:
    _IMPORT_ERROR = None

#: This file's own directory is the project root -- the log and the .env it
#: reads both resolve relative to *this file*, never relative to whatever
#: directory the caller happens to be running from.
_PROJECT_ROOT = Path(__file__).resolve().parent
_ENV_FILE = _PROJECT_ROOT / "backend" / ".env"
_LOG_FILE = _PROJECT_ROOT / "llm_usage_log.xlsx"

_HEADERS = [
    "Timestamp",
    "Provider",
    "Model",
    "Duration (s)",
    "Input Tokens",
    "Output Tokens",
    "Input Cache Tokens",
]
_HEADER_ROW = 1
_FIRST_DATA_ROW = 2
#: 1-indexed columns that get a live SUM formula in the totals row: Duration,
#: Input Tokens, Output Tokens, Input Cache Tokens. Provider/Model (2, 3)
#: are text and are left blank in the totals row.
_SUM_COLUMNS = [4, 5, 6, 7]
_TOTAL_LABEL_PREFIX = "TOTAL calls: "
_COLUMN_WIDTHS = [22, 12, 22, 14, 14, 14, 20]

#: Sheet names. The per-call sheet is looked up by name rather than by
#: ``workbook.active``: once the workbook holds the synced sheets too,
#: whichever one Excel happened to leave selected is not necessarily the one
#: a new call must be appended to.
_SHEET_CALLS = "LLM Usage"
_SHEET_PROVIDER = "OpenAI Usage"
_SHEET_RECONCILIATION = "Reconciliation"

#: What OpenAI reports, per day and per model. "Requests" is its own count of
#: model requests -- not this app's count of calls, which is what makes the
#: two comparable rather than duplicated.
_PROVIDER_HEADERS = [
    "Date (UTC)",
    "Model",
    "Requests",
    "Input Tokens",
    "Input Cached Tokens",
    "Output Tokens",
    "Total Tokens",
]
_PROVIDER_SUM_COLUMNS = [3, 4, 5, 6, 7]
_PROVIDER_COLUMN_WIDTHS = [14, 24, 12, 14, 20, 14, 14]

#: The point of the sync: what this app logged, beside what was actually
#: billed, and the difference. A positive difference is usage that never
#: reached the per-call log -- a test run, another tool, another machine.
_RECONCILIATION_HEADERS = [
    "Date (UTC)",
    "Requests (OpenAI)",
    "Calls logged here",
    "Requests not logged",
    "Input Tokens (OpenAI)",
    "Input Tokens logged",
    "Output Tokens (OpenAI)",
    "Output Tokens logged",
    "Cost (USD)",
]
_RECONCILIATION_SUM_COLUMNS = [2, 3, 4, 5, 6, 7, 8, 9]
_RECONCILIATION_COLUMN_WIDTHS = [14, 18, 18, 20, 22, 20, 22, 20, 12]
_TOTAL_LABEL_DAYS = "TOTAL days: "

#: Where the organisation usage/cost endpoints live. Configurable for the
#: same reason every other endpoint in this project is -- nothing
#: environment-specific is hardcoded -- with OpenAI's documented base as the
#: default.
_DEFAULT_USAGE_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_SYNC_DAYS = 30
_USAGE_TIMEOUT_SECONDS = 30
#: Buckets per page. The API caps this; 31 covers a month of daily buckets in
#: one request, and `next_page` is followed for anything longer.
_USAGE_PAGE_LIMIT = 31

#: Serialises every append within this process. This does not protect
#: against two separate *processes* writing at the same instant -- if this
#: is ever run with multiple worker processes, use one shared writer, or
#: expect an occasional lost row. A single-process app (this project's own
#: ``run.py``) never hits that case.
_write_lock = threading.Lock()


def _read_env(path: Path) -> dict:
    """A minimal, dependency-free ``KEY=VALUE`` reader for one .env file.

    Deliberately not the backend's own env loader (``python-dotenv``, via
    ``app.config.settings``) -- this function's only job is to keep this
    module from needing to import anything from ``backend/`` at all. It
    handles exactly what this file needs: blank lines, ``#`` comments, and an
    optional surrounding quote on the value. Nothing fancier.
    """
    values: dict = {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _current_provider_and_model() -> "tuple[str, str]":
    """Read ``LLM_PROVIDER`` and ``LLM_MODEL`` straight from ``backend/.env``.

    Returns ``"unknown"`` for either value that is missing or blank, rather
    than raising -- a log row with an unknown provider is still useful; a
    crash that silences logging for every call after it is not.
    """
    values = _read_env(_ENV_FILE)
    provider = values.get("LLM_PROVIDER", "").strip() or "unknown"
    model = values.get("LLM_MODEL", "").strip() or "unknown"
    return provider, model


def _call_log_sheet(sheet_source):
    """The per-call sheet, by name.

    Falls back to the active sheet only for a workbook written before this
    module named its sheets -- there the active sheet *is* the per-call one.
    Once the synced sheets exist, ``workbook.active`` is whichever sheet was
    selected when the file was last saved in Excel, which is not something a
    new log row may depend on.
    """
    if _SHEET_CALLS in sheet_source.sheetnames:
        return sheet_source[_SHEET_CALLS]
    return sheet_source.active


def _is_totals_row(sheet, row_index: int) -> bool:
    """A totals row is identified by its own generated formula, not by
    position -- so re-running this against a file that already has one (or
    an older file that does not yet) both behave correctly."""
    value = sheet.cell(row=row_index, column=1).value
    return isinstance(value, str) and value.startswith("=")


def _style_header(sheet) -> None:
    bold = Font(bold=True)
    for column_index in range(1, len(_HEADERS) + 1):
        sheet.cell(row=_HEADER_ROW, column=column_index).font = bold


def _style_totals_row(sheet, row_index: int) -> None:
    bold = Font(bold=True)
    top_border = Border(top=Side(style="thin"))
    for column_index in range(1, len(_HEADERS) + 1):
        cell = sheet.cell(row=row_index, column=column_index)
        cell.font = bold
        cell.border = top_border


def _autosize_columns(sheet) -> None:
    for index, width in enumerate(_COLUMN_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _write_totals_row(sheet, *, last_data_row: int) -> None:
    """(Re)write the totals row directly beneath the data, overwriting
    whatever was there before (a now-stale totals row, from before this
    row was added). Only ever called with ``last_data_row >= _FIRST_DATA_ROW``
    -- i.e. once at least one data row exists -- so the ranges below are
    always valid, never an inverted (empty) range."""
    totals_row = last_data_row + 1

    def data_range(column_index: int) -> str:
        letter = get_column_letter(column_index)
        return f"{letter}{_FIRST_DATA_ROW}:{letter}{last_data_row}"

    sheet.cell(
        row=totals_row,
        column=1,
        value=f'="{_TOTAL_LABEL_PREFIX}"&COUNTA({data_range(1)})',
    )
    for column_index in (2, 3):  # Provider, Model -- text, not summable
        sheet.cell(row=totals_row, column=column_index, value=None)
    for column_index in _SUM_COLUMNS:
        sheet.cell(row=totals_row, column=column_index, value=f"=SUM({data_range(column_index)})")

    _style_totals_row(sheet, totals_row)


def _migrate_if_needed(sheet) -> List[list]:
    """Pull every existing data row out from under an older header layout,
    mapped onto the current one, so upgrading this script never loses a
    single previously-logged row.

    A column this version adds (e.g. "Input Cache Tokens") that an older
    file never had is filled with ``None`` for those historical rows --
    that data simply was never captured before, and is never guessed at.
    Returns a list of row-value-lists in the current column order; an
    already-current file returns its data rows unchanged.
    """
    current_headers = [cell.value for cell in next(sheet.iter_rows(min_row=_HEADER_ROW, max_row=_HEADER_ROW))]
    old_headers = current_headers

    rows: List[list] = []
    for row in sheet.iter_rows(min_row=_FIRST_DATA_ROW, values_only=True):
        first_cell = row[0]
        if first_cell is None:
            continue
        if isinstance(first_cell, str) and first_cell.startswith("="):
            continue  # an old totals row -- rebuilt fresh, never carried forward
        if old_headers == _HEADERS:
            rows.append(list(row))
        else:
            as_dict = dict(zip(old_headers, row))
            rows.append([as_dict.get(header) for header in _HEADERS])
    return rows


def _ensure_current_layout(path: Path) -> None:
    """Create the log fresh, or upgrade an older one in place, so headers,
    column order and the totals row always match this version exactly."""
    if not path.exists():
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = _SHEET_CALLS
        sheet.append(_HEADERS)
        _style_header(sheet)
        _autosize_columns(sheet)
        workbook.save(path)
        return

    workbook = load_workbook(path)
    sheet = _call_log_sheet(workbook)
    current_headers = [cell.value for cell in next(sheet.iter_rows(min_row=_HEADER_ROW, max_row=_HEADER_ROW))]
    if current_headers == _HEADERS and (sheet.max_row == _HEADER_ROW or _is_totals_row(sheet, sheet.max_row)):
        return  # already current: right headers, and either no data yet or a proper totals row

    data_rows = _migrate_if_needed(sheet)

    # Rebuild the sheet from scratch in the current layout -- simpler and
    # safer than patching individual cells of an unknown older shape.
    workbook.remove(sheet)
    sheet = workbook.create_sheet(_SHEET_CALLS, 0)
    sheet.append(_HEADERS)
    _style_header(sheet)
    for row_values in data_rows:
        sheet.append(row_values)
    if data_rows:
        _write_totals_row(sheet, last_data_row=_FIRST_DATA_ROW + len(data_rows) - 1)
    _autosize_columns(sheet)
    workbook.save(path)


def _append_row(sheet, row_values: list) -> None:
    """Append one data row, keeping the totals row (if any) last and its
    formulas covering every data row including this new one."""
    last_row = sheet.max_row

    if last_row < _FIRST_DATA_ROW or not _is_totals_row(sheet, last_row):
        # No totals row yet (a brand-new file, or exactly the state just
        # after migration with no rows at all) -- a plain append is enough.
        sheet.append(row_values)
        last_data_row = sheet.max_row
    else:
        # Insert a fresh row exactly where the totals row currently sits,
        # pushing the totals row down by one, then fill it in.
        sheet.insert_rows(last_row)
        for column_index, value in enumerate(row_values, start=1):
            sheet.cell(row=last_row, column=column_index, value=value)
        last_data_row = last_row

    _write_totals_row(sheet, last_data_row=last_data_row)


def log_usage(
    *,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    duration_seconds: Optional[float],
    input_cache_tokens: Optional[int] = None,
    timestamp: Optional[datetime] = None,
) -> bool:
    """Append one row for one real LLM call. Never raises.

    Only call this for a call that actually reached the provider -- a cache
    hit spent no tokens and must never appear here, or the log would
    overstate real expense.

    Args:
        input_tokens: prompt/input token count from the provider's response
            (its ``usage.prompt_tokens`` or equivalent), or ``None`` if the
            provider did not report one.
        output_tokens: completion/output token count (``usage.completion_tokens``
            or equivalent), or ``None`` if not reported.
        duration_seconds: wall-clock time the request took, start to finish.
        input_cache_tokens: the portion of ``input_tokens`` served from the
            provider's own prompt cache and typically billed at a discount
            (OpenAI's ``usage.prompt_tokens_details.cached_tokens``), or
            ``None`` when the provider does not report this breakdown.
        timestamp: when the call was made; defaults to now (UTC).

    Returns:
        ``True`` if the row was written, ``False`` if logging failed for any
        reason (missing ``openpyxl``, a locked/unwritable file, a bad path).
        The caller's own request must never fail because this did.
    """
    if Workbook is None or load_workbook is None:
        print(
            f"llm_usage_tracker: openpyxl is not installed ({_IMPORT_ERROR}); "
            "usage was not logged. Run: pip install openpyxl",
            file=sys.stderr,
        )
        return False

    when = timestamp or datetime.now(timezone.utc)
    provider, model = _current_provider_and_model()
    row = [
        when.isoformat(timespec="seconds"),
        provider,
        model,
        round(duration_seconds, 3) if duration_seconds is not None else None,
        input_tokens,
        output_tokens,
        input_cache_tokens,
    ]

    try:
        with _write_lock:
            _ensure_current_layout(_LOG_FILE)
            workbook = load_workbook(_LOG_FILE)
            sheet = _call_log_sheet(workbook)
            _append_row(sheet, row)
            workbook.save(_LOG_FILE)
        return True
    except Exception as exc:  # noqa: BLE001 - "never raises" is this function's whole contract
        # Broad on purpose: a locked file (OSError), a corrupt or non-.xlsx
        # workbook (openpyxl's own InvalidFileException/BadZipFile), or
        # anything else -- none of it may ever propagate into the caller's
        # own request.
        print(
            f"llm_usage_tracker: could not write to {_LOG_FILE} ({exc!r}); "
            "usage was not logged, but the request itself is unaffected.",
            file=sys.stderr,
        )
        return False




# ---------------------------------------------------------------------------
# Authoritative usage, straight from the provider
#
# Everything below answers one question the per-call log above cannot: what
# was *actually* billed, including every call this application never saw --
# a test run (the backend's test suite disables this tracker on purpose), a
# script, another machine, anything else sharing the API key.
#
# Read-only, and explicit: nothing here runs unless `sync` is invoked.
# ---------------------------------------------------------------------------


class UsageSyncError(RuntimeError):
    """The authoritative usage could not be fetched. Always says why, in
    words an operator can act on, and never with a key in the message."""


def _usage_api_settings() -> dict:
    """Read the sync's own configuration from ``backend/.env``.

    ``OPENAI_ADMIN_KEY`` is deliberately a *different* key from the
    ``LLM_API_KEY`` this application answers requests with: organisation
    usage and cost are admin-scoped endpoints, and an ordinary project key
    is refused by them. Keeping them apart also means the key that can read
    the whole organisation's spend is not the one sitting in a request
    header on every explanation.
    """
    values = _read_env(_ENV_FILE)
    project_ids = [
        part.strip()
        for part in (values.get("OPENAI_USAGE_PROJECT_IDS", "") or "").split(",")
        if part.strip()
    ]
    raw_days = (values.get("OPENAI_USAGE_DAYS", "") or "").strip()
    try:
        days = int(raw_days) if raw_days else _DEFAULT_SYNC_DAYS
    except ValueError:
        days = _DEFAULT_SYNC_DAYS
    return {
        "admin_key": (values.get("OPENAI_ADMIN_KEY", "") or "").strip(),
        "base_url": (values.get("OPENAI_USAGE_BASE_URL", "") or "").strip()
        or _DEFAULT_USAGE_BASE_URL,
        "project_ids": project_ids,
        "days": max(1, days),
    }


def _get_json(url: str, admin_key: str) -> dict:
    """One GET against the usage API, as JSON.

    Every failure is turned into a ``UsageSyncError`` whose message says what
    to do about it. The key is never echoed -- not in the message, not in a
    traceback -- and no response body is printed, because a usage response
    describes the organisation's spend.
    """
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {admin_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_USAGE_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise UsageSyncError(
                "OpenAI refused the admin key (HTTP "
                f"{exc.code}). Organisation usage needs an ADMIN key "
                "(sk-admin-..., from Organization -> Admin keys, with the "
                "api.usage.read permission). The ordinary LLM_API_KEY this "
                "app sends its requests with cannot read it."
            ) from None
        if exc.code == 429:
            raise UsageSyncError(
                "OpenAI rate-limited the usage request (HTTP 429). Wait a "
                "moment and run the sync again; nothing was written."
            ) from None
        raise UsageSyncError(
            f"OpenAI returned HTTP {exc.code} for the usage request. Nothing "
            "was written."
        ) from None
    except urllib.error.URLError as exc:
        raise UsageSyncError(
            f"Could not reach OpenAI ({exc.reason}). Check the network, or "
            "OPENAI_USAGE_BASE_URL in backend/.env."
        ) from None
    except (ValueError, UnicodeDecodeError):
        raise UsageSyncError(
            "OpenAI returned a usage response this script could not read."
        ) from None


def _fetch_buckets(path: str, settings: dict, params: dict) -> List[dict]:
    """Every bucket for one endpoint, following ``next_page`` to the end.

    The API returns time buckets a page at a time; stopping at the first page
    would silently under-report a longer window, which is exactly the kind of
    quiet shortfall this whole sync exists to remove.
    """
    base = settings["base_url"].rstrip("/")
    buckets: List[dict] = []
    page: Optional[str] = None
    seen_pages = 0
    while True:
        query = dict(params)
        if page:
            query["page"] = page
        url = f"{base}{path}?{urllib.parse.urlencode(query, doseq=True)}"
        body = _get_json(url, settings["admin_key"])
        buckets.extend(body.get("data") or [])
        page = body.get("next_page")
        seen_pages += 1
        if not body.get("has_more") or not page:
            break
        if seen_pages > 200:  # a runaway cursor must not loop forever
            raise UsageSyncError(
                "OpenAI kept returning more usage pages than expected; stopped "
                "after 200. Try a shorter window with --days."
            )
    return buckets


def _bucket_day(bucket: dict) -> str:
    """The UTC calendar day a bucket starts on, as YYYY-MM-DD.

    Buckets are daily by default, so this is the bucket's own day; it stays
    correct for an hourly bucket too, which simply rolls up into its day.
    """
    start = bucket.get("start_time")
    if not isinstance(start, (int, float)):
        return ""
    return datetime.fromtimestamp(start, tz=timezone.utc).date().isoformat()


def fetch_openai_usage(settings: dict, *, days: int) -> List[dict]:
    """Token usage per (day, model) from OpenAI's own records.

    Returns rows in the order the ``OpenAI Usage`` sheet shows them: by day,
    then by model. Figures are reported exactly as the API gives them and are
    never estimated, converted or filled in.
    """
    start_time = int(
        (datetime.now(timezone.utc) - timedelta(days=days))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )
    params: dict = {
        "start_time": start_time,
        "bucket_width": "1d",
        "group_by": ["model"],
        "limit": _USAGE_PAGE_LIMIT,
    }
    if settings["project_ids"]:
        params["project_ids"] = settings["project_ids"]

    rows: List[dict] = []
    for bucket in _fetch_buckets("/organization/usage/completions", settings, params):
        day = _bucket_day(bucket)
        for result in bucket.get("results") or []:
            requests_made = result.get("num_model_requests") or 0
            input_tokens = result.get("input_tokens") or 0
            output_tokens = result.get("output_tokens") or 0
            if not (requests_made or input_tokens or output_tokens):
                continue  # an empty bucket is not a day's worth of nothing
            rows.append(
                {
                    "date": day,
                    # A result is only unlabelled when nothing was grouped by;
                    # said plainly rather than guessed at.
                    "model": result.get("model") or "(not reported)",
                    "requests": requests_made,
                    "input_tokens": input_tokens,
                    "input_cached_tokens": result.get("input_cached_tokens") or 0,
                    "output_tokens": output_tokens,
                }
            )
    rows.sort(key=lambda row: (row["date"], str(row["model"])))
    return rows


def fetch_openai_costs(settings: dict, *, days: int) -> Dict[str, float]:
    """Cost in USD per UTC day, from OpenAI's own billing records.

    A day missing from the result simply had no cost reported for it, and is
    left blank in the workbook rather than written as a zero.
    """
    start_time = int(
        (datetime.now(timezone.utc) - timedelta(days=days))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )
    params = {"start_time": start_time, "bucket_width": "1d", "limit": _USAGE_PAGE_LIMIT}
    if settings["project_ids"]:
        params["project_ids"] = settings["project_ids"]

    by_day: Dict[str, float] = {}
    for bucket in _fetch_buckets("/organization/costs", settings, params):
        day = _bucket_day(bucket)
        for result in bucket.get("results") or []:
            amount = (result.get("amount") or {}).get("value")
            if isinstance(amount, (int, float)):
                by_day[day] = by_day.get(day, 0.0) + float(amount)
    return by_day


def _logged_totals_by_day(path: Path) -> Dict[str, dict]:
    """What the per-call sheet in this workbook recorded, per UTC day.

    Read back from the sheet itself rather than kept in a second place, so
    the reconciliation always compares against exactly what the workbook
    shows -- including rows logged by an earlier version of this script.
    """
    totals: Dict[str, dict] = {}
    if not path.exists():
        return totals
    workbook = load_workbook(path, data_only=False)
    sheet = _call_log_sheet(workbook)
    for row in sheet.iter_rows(min_row=_FIRST_DATA_ROW, values_only=True):
        timestamp = row[0] if row else None
        if timestamp is None:
            continue
        if isinstance(timestamp, str) and timestamp.startswith("="):
            continue  # the totals row
        if isinstance(timestamp, datetime):
            day = timestamp.date().isoformat()
        elif isinstance(timestamp, date_type):
            day = timestamp.isoformat()
        else:
            day = str(timestamp)[:10]
        entry = totals.setdefault(day, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        entry["calls"] += 1
        for key, index in (("input_tokens", 4), ("output_tokens", 5)):
            value = row[index] if len(row) > index else None
            if isinstance(value, (int, float)):
                entry[key] += int(value)
    return totals


def _write_sheet(
    workbook,
    *,
    title: str,
    headers: List[str],
    widths: List[int],
    rows: List[list],
    sum_columns: List[int],
    label_prefix: str,
    footer: Optional[str] = None,
) -> None:
    """Rebuild one synced sheet from scratch.

    Rebuilt, never appended to: these sheets are a copy of what the provider
    reports for a window, so re-syncing an overlapping window must replace
    that window's rows rather than duplicate them. The per-call sheet is the
    opposite -- an append-only history -- and is never touched here.
    """
    if title in workbook.sheetnames:
        workbook.remove(workbook[title])
    sheet = workbook.create_sheet(title)
    sheet.append(headers)
    bold = Font(bold=True)
    for column_index in range(1, len(headers) + 1):
        sheet.cell(row=_HEADER_ROW, column=column_index).font = bold
    for row_values in rows:
        sheet.append(row_values)

    if rows:
        last_data_row = _FIRST_DATA_ROW + len(rows) - 1
        totals_row = last_data_row + 1

        def data_range(column_index: int) -> str:
            letter = get_column_letter(column_index)
            return f"{letter}{_FIRST_DATA_ROW}:{letter}{last_data_row}"

        sheet.cell(
            row=totals_row,
            column=1,
            value=f'="{label_prefix}"&COUNTA({data_range(1)})',
        )
        for column_index in sum_columns:
            sheet.cell(
                row=totals_row, column=column_index, value=f"=SUM({data_range(column_index)})"
            )
        top_border = Border(top=Side(style="thin"))
        for column_index in range(1, len(headers) + 1):
            cell = sheet.cell(row=totals_row, column=column_index)
            cell.font = bold
            cell.border = top_border
        if footer:
            sheet.cell(row=totals_row + 2, column=1, value=footer)
    elif footer:
        sheet.cell(row=_FIRST_DATA_ROW, column=1, value=footer)

    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def sync_openai_usage(days: Optional[int] = None) -> dict:
    """Pull real usage and cost from OpenAI into the workbook.

    Rewrites the ``OpenAI Usage`` and ``Reconciliation`` sheets for the
    window and leaves the per-call ``LLM Usage`` sheet exactly as it is.

    Raises:
        UsageSyncError: no admin key configured, the provider refused the
            request, or it could not be reached. Nothing is written in any of
            those cases -- a half-written expense record is worse than none.
    """
    if Workbook is None or load_workbook is None:
        raise UsageSyncError(
            f"openpyxl is not installed ({_IMPORT_ERROR}). Run: pip install openpyxl"
        )

    settings = _usage_api_settings()
    if not settings["admin_key"]:
        raise UsageSyncError(
            "No OPENAI_ADMIN_KEY in backend/.env, so there is nothing to ask "
            "OpenAI with. Create an admin key at Organization -> Admin keys "
            "(it starts sk-admin-, and is not the same as LLM_API_KEY), then "
            "add:\n\n    OPENAI_ADMIN_KEY=sk-admin-...\n\n"
            "Optional, in the same file: OPENAI_USAGE_DAYS (default "
            f"{_DEFAULT_SYNC_DAYS}), OPENAI_USAGE_PROJECT_IDS to limit the "
            "sync to one project, OPENAI_USAGE_BASE_URL to point elsewhere."
        )

    window_days = max(1, int(days)) if days else settings["days"]
    usage_rows = fetch_openai_usage(settings, days=window_days)
    costs_by_day = fetch_openai_costs(settings, days=window_days)
    logged_by_day = _logged_totals_by_day(_LOG_FILE)

    provider_rows = [
        [
            row["date"],
            row["model"],
            row["requests"],
            row["input_tokens"],
            row["input_cached_tokens"],
            row["output_tokens"],
            row["input_tokens"] + row["output_tokens"],
        ]
        for row in usage_rows
    ]

    # One reconciliation row per day that either source knows about, so a day
    # this app logged nothing for -- the case that started all this -- is a
    # visible line rather than a missing one.
    provider_by_day: Dict[str, dict] = {}
    for row in usage_rows:
        entry = provider_by_day.setdefault(
            row["date"], {"requests": 0, "input_tokens": 0, "output_tokens": 0}
        )
        entry["requests"] += row["requests"]
        entry["input_tokens"] += row["input_tokens"]
        entry["output_tokens"] += row["output_tokens"]

    reconciliation_rows = []
    for day in sorted(set(provider_by_day) | set(logged_by_day) | set(costs_by_day)):
        provider = provider_by_day.get(day, {"requests": 0, "input_tokens": 0, "output_tokens": 0})
        logged = logged_by_day.get(day, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        reconciliation_rows.append(
            [
                day,
                provider["requests"],
                logged["calls"],
                provider["requests"] - logged["calls"],
                provider["input_tokens"],
                logged["input_tokens"],
                provider["output_tokens"],
                logged["output_tokens"],
                # Left blank, never zero, when OpenAI reported no cost for the
                # day -- the two mean different things.
                round(costs_by_day[day], 6) if day in costs_by_day else None,
            ]
        )

    synced_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    window_note = (
        f"Synced {synced_at} from OpenAI for the last {window_days} day(s). "
        "These figures are OpenAI's own and cover every call on the "
        "organisation, including calls this application never made."
    )

    with _write_lock:
        _ensure_current_layout(_LOG_FILE)
        workbook = load_workbook(_LOG_FILE)
        _write_sheet(
            workbook,
            title=_SHEET_PROVIDER,
            headers=_PROVIDER_HEADERS,
            widths=_PROVIDER_COLUMN_WIDTHS,
            rows=provider_rows,
            sum_columns=_PROVIDER_SUM_COLUMNS,
            label_prefix="TOTAL rows: ",
            footer=window_note,
        )
        _write_sheet(
            workbook,
            title=_SHEET_RECONCILIATION,
            headers=_RECONCILIATION_HEADERS,
            widths=_RECONCILIATION_COLUMN_WIDTHS,
            rows=reconciliation_rows,
            sum_columns=_RECONCILIATION_SUM_COLUMNS,
            label_prefix=_TOTAL_LABEL_DAYS,
            footer=(
                '"Requests not logged" is usage OpenAI billed that never reached '
                "this workbook's per-call sheet -- a test run, another tool, or "
                "another machine on the same key. It is not an error; it is the "
                "part this application could not see."
            ),
        )
        workbook.save(_LOG_FILE)

    return {
        "days": window_days,
        "usage_rows": len(provider_rows),
        "days_reconciled": len(reconciliation_rows),
        "provider_requests": sum(row["requests"] for row in usage_rows),
        "provider_input_tokens": sum(row["input_tokens"] for row in usage_rows),
        "provider_output_tokens": sum(row["output_tokens"] for row in usage_rows),
        "logged_calls": sum(entry["calls"] for entry in logged_by_day.values()),
        "cost_usd": round(sum(costs_by_day.values()), 6) if costs_by_day else None,
    }


def _main(argv: List[str]) -> int:
    """The command line: report what would be logged, or run the sync."""
    args = list(argv)
    provider, model = _current_provider_and_model()
    settings = _usage_api_settings()

    if not args or args[0] in {"-h", "--help", "help"}:
        print(f"backend/.env  ->  provider={provider!r}  model={model!r}")
        print(f"log file      ->  {_LOG_FILE}")
        if settings["admin_key"]:
            print(
                "authoritative ->  OPENAI_ADMIN_KEY is set; run "
                "'python llm_usage_tracker.py sync' to pull what OpenAI "
                f"actually billed (last {settings['days']} days by default)."
            )
        else:
            print(
                "authoritative ->  not configured. Only calls made through "
                "this running application are logged; test runs and anything "
                "else on the same key are invisible. Set OPENAI_ADMIN_KEY in "
                "backend/.env and run 'python llm_usage_tracker.py sync'."
            )
        return 0

    if args[0] != "sync":
        print(f"llm_usage_tracker: unknown command {args[0]!r}.", file=sys.stderr)
        print("Usage: python llm_usage_tracker.py [sync [--days N]]", file=sys.stderr)
        return 2

    days: Optional[int] = None
    rest = args[1:]
    if rest:
        if rest[0] in {"--days", "-d"} and len(rest) > 1:
            try:
                days = int(rest[1])
            except ValueError:
                print(f"llm_usage_tracker: --days needs a number, got {rest[1]!r}.", file=sys.stderr)
                return 2
        else:
            print(f"llm_usage_tracker: unknown option {rest[0]!r}.", file=sys.stderr)
            return 2

    if provider.lower() != "openai":
        # Not fatal: the admin key decides what the endpoint answers for. But
        # a Groq-configured project asking OpenAI for its usage is worth
        # saying out loud rather than quietly returning nothing.
        print(
            f"llm_usage_tracker: note - LLM_PROVIDER is {provider!r}, and this "
            "sync reads OpenAI's organisation usage. Only OpenAI usage will "
            "appear.",
            file=sys.stderr,
        )

    try:
        result = sync_openai_usage(days)
    except UsageSyncError as exc:
        print(f"llm_usage_tracker: {exc}", file=sys.stderr)
        return 1

    print(f"Synced {result['days']} day(s) of OpenAI usage into {_LOG_FILE}")
    print(
        f"  OpenAI reports : {result['provider_requests']} request(s), "
        f"{result['provider_input_tokens']} input + "
        f"{result['provider_output_tokens']} output tokens"
    )
    print(f"  Logged here    : {result['logged_calls']} call(s) in the same window")
    gap = result["provider_requests"] - result["logged_calls"]
    if gap > 0:
        print(
            f"  Not logged here: {gap} request(s) -- test runs, other tools or "
            "other machines on the same key. See the Reconciliation sheet."
        )
    if result["cost_usd"] is not None:
        print(f"  Cost reported  : {result['cost_usd']} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
