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
database access, no HTTP calls, and does not import any other module in this
project.

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

This can also be run directly (``python llm_usage_tracker.py``) to print the
provider/model it would currently record, as a quick sanity check that
``backend/.env`` parses the way you expect.
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

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
        sheet.title = "LLM Usage"
        sheet.append(_HEADERS)
        _style_header(sheet)
        _autosize_columns(sheet)
        workbook.save(path)
        return

    workbook = load_workbook(path)
    sheet = workbook.active
    current_headers = [cell.value for cell in next(sheet.iter_rows(min_row=_HEADER_ROW, max_row=_HEADER_ROW))]
    if current_headers == _HEADERS and (sheet.max_row == _HEADER_ROW or _is_totals_row(sheet, sheet.max_row)):
        return  # already current: right headers, and either no data yet or a proper totals row

    data_rows = _migrate_if_needed(sheet)

    # Rebuild the sheet from scratch in the current layout -- simpler and
    # safer than patching individual cells of an unknown older shape.
    workbook.remove(sheet)
    sheet = workbook.create_sheet("LLM Usage", 0)
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
            sheet = workbook.active
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


if __name__ == "__main__":
    provider, model = _current_provider_and_model()
    print(f"backend/.env  ->  provider={provider!r}  model={model!r}")
    print(f"log file      ->  {_LOG_FILE}")
