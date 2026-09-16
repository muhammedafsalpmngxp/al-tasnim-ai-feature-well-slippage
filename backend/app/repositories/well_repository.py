"""Database access for well lifecycle evidence (not scoped to a report date).

Queries live in backend/sql and are executed here with bound parameters only,
same contract as app/repositories/daily_repository.py.
"""

from __future__ import annotations

import logging
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
