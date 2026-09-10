"""
AUTHORITATIVE DETERMINISTIC EVIDENCE LAYER (execution side).

Runs backend/sql/well_evidence.sql — the single source of truth for every
well-slippage calculation — and hands back its RAW output untouched.

Nothing here calculates a milestone, a delay, a status, a variance or a
classification. Those all come out of the SQL. This module only:

  - binds the well_id parameter
  - walks the two result sets the query returns
  - zips column names onto rows

The raw result is deliberately preserved (see build_evidence_bundle in
investigation.py) so that a summary can be audited later without going
back to the database.
"""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

EVIDENCE_SQL_FILE = BASE_DIR / "sql" / "well_evidence.sql"


# A column unique to the activity-level result set, used to tell the two
# result sets apart without depending on their order.
ACTIVITY_MARKER_COLUMN = "task_daily_id"


class WellNotFoundError(Exception):
    """Raised when a well_id has no record in well_master."""


def load_evidence_sql():

    if not EVIDENCE_SQL_FILE.exists():

        raise FileNotFoundError(
            f"Authoritative evidence SQL not found: {EVIDENCE_SQL_FILE}"
        )

    query = EVIDENCE_SQL_FILE.read_text(encoding="utf-8")

    if not query.strip():
        raise ValueError("Authoritative evidence SQL file is empty.")

    return query


def _read_result_sets(cursor):

    """
    Collect every result set the batch produced, as
    (columns, list-of-row-dicts) pairs, in order.
    """

    result_sets = []

    while True:

        if cursor.description is not None:

            columns = [column[0] for column in cursor.description]

            result_sets.append([
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ])

        if not cursor.nextset():
            break

    return result_sets


def get_well_evidence(connection, well_id: int):

    """
    Execute the authoritative SQL for one well.

    Returns the raw deterministic evidence:

        {
            "well_id":    <int>,
            "well":       {<41 well-level evidence columns>},
            "activities": [{<170 activity-level evidence columns>}, ...]
        }

    `activities` holds EVERY current logical task for the well, not only
    the delayed ones — the SQL's own delayed-only filter is applied
    downstream so this one query serves both the full evidence view and
    the delayed-activity view.
    """

    query = load_evidence_sql()

    cursor = connection.cursor()

    try:

        cursor.execute(query, well_id)

        result_sets = _read_result_sets(cursor)

    finally:
        cursor.close()

    well_row = None
    activities = []

    # Identify the sets by their columns rather than by position, so a
    # driver that reports an extra empty set cannot misalign them.
    for rows in result_sets:

        if not rows:
            continue

        if ACTIVITY_MARKER_COLUMN in rows[0]:
            activities = rows
        elif well_row is None:
            well_row = rows[0]

    if well_row is None:

        raise WellNotFoundError(
            f"Well {well_id} was not found."
        )

    return {
        "well_id": well_id,
        "well": well_row,
        "activities": activities
    }


def delayed_activity_rows(activities):

    """
    The delayed / at-risk subset, using the SQL's OWN classification
    columns — the same three conditions the authoritative query applies
    in its trailing WHERE clause. This is a filter over deterministic
    fields, not a re-classification.
    """

    return [
        activity
        for activity in activities
        if activity.get("schedule_risk") == "RED_DELAYED"
        or activity.get("end_status") == "OVERDUE_CURRENT_TASK_LAGGING"
        or activity.get("ai_schedule_classification") == "DELAYED"
    ]
