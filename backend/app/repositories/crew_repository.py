"""Read-only access to the crew-suggestion evidence.

Exactly one query, exactly one round trip: sql/crew_suggestion.sql resolves
the target task, its eligibility, its current crew and (when eligible) the
single top-ranked suggested crew, all in one SELECT. Nothing here calculates
anything further -- see app/services/crew_suggestion_service.py for how the
raw row is turned into the evidence shape the LLM receives.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

from app.config.database import fetch_all
from app.utils.sql_loader import load_sql

logger = logging.getLogger(__name__)


class CrewRepository:
    """Read-only access to crew_suggestion.sql."""

    def fetch_target_task(
        self, *, well_id: int, task_code: str, report_date: date
    ) -> Optional[Dict[str, Any]]:
        """One row of crew-suggestion evidence for this task, or ``None`` if
        the task itself cannot be found for this well/task_code/report_date.
        """
        sql = load_sql("crew_suggestion")
        rows = fetch_all(
            sql,
            (report_date, well_id, task_code),
            label="crew_suggestion",
        )
        if not rows:
            return None
        return rows[0]
