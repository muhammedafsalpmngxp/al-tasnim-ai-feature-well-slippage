"""Tests for llm_usage_tracker.py.

Kept at the project root, next to the module it tests, rather than inside
``backend/tests/`` -- that keeps this test file discoverable and runnable
completely independently of the backend's own test suite (``pytest.ini``
there only looks under ``backend/tests``), matching the tracker's own
independence from the rest of the project. Run directly with:

    python -m pytest test_llm_usage_tracker.py -v

Every test points the module at a throwaway ``.env``/log file under
``tmp_path`` (via ``monkeypatch``), so no test ever touches the real
``backend/.env`` or the real ``llm_usage_log.xlsx`` at the project root.
"""

from __future__ import annotations

import openpyxl
import pytest

import llm_usage_tracker as tracker


@pytest.fixture(autouse=True)
def _isolated_files(tmp_path, monkeypatch):
    """Every test gets its own env file and log file; nothing here ever
    touches the real project-root llm_usage_log.xlsx or backend/.env."""
    env_file = tmp_path / "fake.env"
    env_file.write_text("LLM_PROVIDER=openai\nLLM_MODEL=gpt-4o-mini\n", encoding="utf-8")
    log_file = tmp_path / "usage.xlsx"
    monkeypatch.setattr(tracker, "_ENV_FILE", env_file)
    monkeypatch.setattr(tracker, "_LOG_FILE", log_file)
    return env_file, log_file


def _rows(log_file):
    """Every row's cell values, each as a list (so it compares equal to
    ``tracker._HEADERS``, itself a plain list)."""
    workbook = openpyxl.load_workbook(log_file)
    sheet = workbook.active
    return [[cell.value for cell in row] for row in sheet.iter_rows()]


class TestEnvParsing:
    def test_reads_provider_and_model_from_the_env_file(self, _isolated_files):
        provider, model = tracker._current_provider_and_model()
        assert provider == "openai"
        assert model == "gpt-4o-mini"

    def test_missing_env_file_reports_unknown_rather_than_raising(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tracker, "_ENV_FILE", tmp_path / "does-not-exist.env")
        provider, model = tracker._current_provider_and_model()
        assert provider == "unknown"
        assert model == "unknown"

    def test_quoted_and_commented_values_are_handled(self, tmp_path, monkeypatch):
        env_file = tmp_path / "fake.env"
        env_file.write_text(
            "# a comment\nLLM_PROVIDER=\"groq\"\n\nLLM_MODEL='openai/gpt-oss-120b'\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(tracker, "_ENV_FILE", env_file)
        provider, model = tracker._current_provider_and_model()
        assert provider == "groq"
        assert model == "openai/gpt-oss-120b"


class TestLoggingOneCall:
    def test_a_first_call_creates_the_file_with_headers_data_and_totals(self, _isolated_files):
        _, log_file = _isolated_files
        ok = tracker.log_usage(input_tokens=100, output_tokens=20, duration_seconds=1.5)
        assert ok is True

        rows = _rows(log_file)
        assert rows[0] == tracker._HEADERS
        assert rows[1][1:] == ["openai", "gpt-4o-mini", 1.5, 100, 20, None]
        totals = rows[2]
        assert totals[0] == '="TOTAL calls: "&COUNTA(A2:A2)'
        assert totals[3] == "=SUM(D2:D2)"
        assert totals[4] == "=SUM(E2:E2)"
        assert totals[5] == "=SUM(F2:F2)"
        assert totals[6] == "=SUM(G2:G2)"

    def test_input_cache_tokens_is_recorded_when_given(self, _isolated_files):
        _, log_file = _isolated_files
        tracker.log_usage(input_tokens=100, output_tokens=20, input_cache_tokens=64, duration_seconds=1.5)
        rows = _rows(log_file)
        assert rows[1][-1] == 64

    def test_missing_token_counts_are_stored_as_blank_not_zero(self, _isolated_files):
        """A provider that doesn't report usage must not look like it used
        zero tokens -- None and 0 mean different things here."""
        _, log_file = _isolated_files
        tracker.log_usage(input_tokens=None, output_tokens=None, duration_seconds=0.9)
        rows = _rows(log_file)
        assert rows[1][4] is None
        assert rows[1][5] is None


class TestTotalsRowStaysAtTheBottom:
    def test_three_calls_keep_the_totals_row_last_with_a_growing_range(self, _isolated_files):
        _, log_file = _isolated_files
        tracker.log_usage(input_tokens=10, output_tokens=1, duration_seconds=0.1)
        tracker.log_usage(input_tokens=20, output_tokens=2, duration_seconds=0.2)
        tracker.log_usage(input_tokens=30, output_tokens=3, duration_seconds=0.3)

        rows = _rows(log_file)
        assert len(rows) == 5  # header + 3 data rows + 1 totals row
        assert rows[1][4] == 10 and rows[2][4] == 20 and rows[3][4] == 30
        totals = rows[4]
        assert totals[0] == '="TOTAL calls: "&COUNTA(A2:A4)'
        assert totals[3] == "=SUM(D2:D4)"
        assert totals[4] == "=SUM(E2:E4)"

    def test_the_actual_sums_are_arithmetically_correct(self, _isolated_files):
        """Formulas aren't evaluated by openpyxl -- recompute by hand from
        the raw cell values to prove the *ranges* the formulas reference
        actually cover the right data, not just that a formula exists."""
        _, log_file = _isolated_files
        tracker.log_usage(input_tokens=10, output_tokens=1, input_cache_tokens=5, duration_seconds=0.1)
        tracker.log_usage(input_tokens=20, output_tokens=2, input_cache_tokens=None, duration_seconds=0.2)
        tracker.log_usage(input_tokens=30, output_tokens=3, input_cache_tokens=7, duration_seconds=0.3)

        rows = _rows(log_file)
        data_rows = rows[1:4]
        assert sum(r[4] for r in data_rows) == 60  # Input Tokens
        assert sum(r[5] for r in data_rows) == 6  # Output Tokens
        assert sum(r[6] for r in data_rows if r[6] is not None) == 12  # Input Cache Tokens
        assert round(sum(r[3] for r in data_rows), 6) == 0.6  # Duration


class TestMigrationFromAnOlderFile:
    """Simulates upgrading a log file written before this version existed:
    no "Input Cache Tokens" column, no totals row."""

    def _write_old_format_file(self, log_file):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(["Timestamp", "Provider", "Model", "Duration (s)", "Input Tokens", "Output Tokens"])
        sheet.append(["2026-08-01T00:00:00+00:00", "groq", "openai/gpt-oss-120b", 2.0, 500, 80])
        workbook.save(log_file)

    def test_existing_rows_are_preserved_with_a_blank_new_column(self, _isolated_files):
        _, log_file = _isolated_files
        self._write_old_format_file(log_file)

        tracker.log_usage(input_tokens=100, output_tokens=10, input_cache_tokens=5, duration_seconds=1.0)

        rows = _rows(log_file)
        assert rows[0] == tracker._HEADERS
        old_row = rows[1]
        assert old_row[:6] == ["2026-08-01T00:00:00+00:00", "groq", "openai/gpt-oss-120b", 2.0, 500, 80]
        assert old_row[6] is None  # never captured for this historical row
        new_row = rows[2]
        assert new_row[4:] == [100, 10, 5]

    def test_a_totals_row_is_added_covering_old_and_new_rows_together(self, _isolated_files):
        _, log_file = _isolated_files
        self._write_old_format_file(log_file)
        tracker.log_usage(input_tokens=100, output_tokens=10, duration_seconds=1.0)

        rows = _rows(log_file)
        totals = rows[-1]
        assert totals[0] == '="TOTAL calls: "&COUNTA(A2:A3)'
        assert totals[4] == "=SUM(E2:E3)"

    def test_re_running_against_an_already_current_file_changes_nothing_but_the_new_row(
        self, _isolated_files
    ):
        _, log_file = _isolated_files
        tracker.log_usage(input_tokens=1, output_tokens=1, duration_seconds=0.1)
        tracker.log_usage(input_tokens=2, output_tokens=2, duration_seconds=0.2)
        rows = _rows(log_file)
        assert rows[0] == tracker._HEADERS
        assert len(rows) == 4  # header + 2 data + totals -- no duplicate migration


class TestNeverRaises:
    def test_a_file_that_cannot_be_written_returns_false_not_an_exception(self, tmp_path, monkeypatch):
        # A directory where the log file path should be forces a write error.
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        monkeypatch.setattr(tracker, "_LOG_FILE", blocked)  # a directory, not a file
        result = tracker.log_usage(input_tokens=1, output_tokens=1, duration_seconds=0.1)
        assert result is False
