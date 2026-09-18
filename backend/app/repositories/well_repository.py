"""Database access for well lifecycle evidence (not scoped to a report date).

Queries live in backend/sql and are executed here with bound parameters only,
same contract as app/repositories/daily_repository.py.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List

from app.config.database import fetch_all
from app.utils.sql_loader import load_sql

logger = logging.getLogger(__name__)


class WellRepository:
    """Read-only access to well.well_master lifecycle evidence."""

    def fetch_outstanding_milestones(self) -> List[Dict[str, Any]]:
        """One row per not-yet-reached milestone, for every live well.

        No parameters: the query itself decides nothing about what is "near" a
        deadline, only what is still outstanding. Windowing is owned by
        app/services/milestone_service.py.
        """
        sql = load_sql("well_milestones")
        rows = fetch_all(sql, label="well_milestones")
        logger.info("well milestones: %d outstanding row(s)", len(rows))
        return rows

    def fetch_well_task_activity(self, report_date: date) -> List[Dict[str, Any]]:
        """Per-well task-activity counters for every live well with task
        evidence as of ``report_date``.

        One set-based query for the whole well universe -- never one query per
        well. The report date is always bound as a parameter.
        """
        sql = load_sql("well_task_activity")
        rows = fetch_all(sql, (report_date,), label="well_task_activity")
        logger.info(
            "well task activity for %s: %d live well(s) with task evidence",
            report_date,
            len(rows),
        )
        return rows

    def fetch_well_task_activity_detail(self, report_date: date) -> List[Dict[str, Any]]:
        """The incomplete logical tasks behind those counters, for every live
        well at once.

        Loaded on demand (the front page's own figures do not need it) and
        then cached for the report date, so expanding one well's task list --
        and then another's -- costs one query in total, not one per well.
        """
        sql = load_sql("well_task_activity_detail")
        rows = fetch_all(sql, (report_date,), label="well_task_activity_detail")
        logger.info(
            "well task activity detail for %s: %d incomplete logical task(s)",
            report_date,
            len(rows),
        )
        return rows
