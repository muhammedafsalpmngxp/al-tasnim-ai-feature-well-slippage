"""All database access for the daily morning brief.

Queries live in backend/sql and are executed here with bound parameters only.
No SQL is ever built by concatenating a user-supplied value.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List

from app.config.database import fetch_all, get_connection
from app.models.daily import DayCounters
from app.utils.sql_loader import load_sql

logger = logging.getLogger(__name__)


class DailyRepository:
    """Read-only access to the resolved daily task evidence."""

    def fetch_day(self, report_date: date) -> tuple[List[Dict[str, Any]], DayCounters]:
        """Return the resolved detail rows and the day-level counters.

        Both statements run on one connection so the dashboard costs exactly two
        round trips per report date -- never one query per well.
        """
        detail_sql = load_sql("daily_detail")
        summary_sql = load_sql("daily_summary")

        with get_connection() as connection:
            rows = fetch_all(
                detail_sql, (report_date,), label="daily_detail", connection=connection
            )
            counter_rows = fetch_all(
                summary_sql, (report_date,), label="daily_summary", connection=connection
            )

        counters = self._to_counters(counter_rows)
        logger.info(
            "daily evidence for %s: %d raw row(s) resolved to %d logical task(s)",
            report_date,
            counters.raw_row_count,
            len(rows),
        )
        return rows, counters

    @staticmethod
    def _to_counters(counter_rows: List[Dict[str, Any]]) -> DayCounters:
        if not counter_rows:
            return DayCounters()
        row = counter_rows[0]
        return DayCounters(
            raw_row_count=int(row.get("raw_row_count") or 0),
            raw_well_count=int(row.get("raw_well_count") or 0),
            raw_actual_entry_count=int(row.get("raw_actual_entry_count") or 0),
            invalid_json_row_count=int(row.get("invalid_json_row_count") or 0),
            unparseable_actual_row_count=int(row.get("unparseable_actual_row_count") or 0),
            logical_task_count=int(row.get("logical_task_count") or 0),
            multi_row_task_count=int(row.get("multi_row_task_count") or 0),
            duplicate_actual_task_count=int(row.get("duplicate_actual_task_count") or 0),
            superseded_row_count=int(row.get("superseded_row_count") or 0),
        )

    def fetch_dates_with_activity(self, limit: int) -> List[Dict[str, Any]]:
        """Recent report dates that hold daily entries, for the date picker.

        ``limit`` is bound as a parameter, never interpolated into the text.

        well.task_daily.well_id is stored as varchar and a minority of rows
        hold non-numeric junk (e.g. '0000F') -- see daily_tasks.sql for the
        full explanation. TRY_CONVERT is used here for the same reason: a bare
        comparison/JOIN against the int well_master.well_id would throw
        SQLSTATE 22018 on those rows instead of just excluding them.
        """
        sql = """
            SELECT TOP (?) td.ActionOn AS report_date,
                   COUNT(*) AS row_count,
                   COUNT(DISTINCT TRY_CONVERT(int, td.well_id)) AS well_count
            FROM well.task_daily AS td
            INNER JOIN well.well_master AS wm
                    ON wm.well_id = TRY_CONVERT(int, td.well_id)
                   AND wm.eng_completion_date IS NULL
            WHERE TRY_CONVERT(int, td.well_id) > 1
              AND td.daily_data IS NOT NULL
              AND ISJSON(td.daily_data) = 1
              AND JSON_VALUE(td.daily_data, '$.actual_quantity') IS NOT NULL
            GROUP BY td.ActionOn
            ORDER BY td.ActionOn DESC
        """
        return fetch_all(sql, (limit,), label="dates_with_activity")
