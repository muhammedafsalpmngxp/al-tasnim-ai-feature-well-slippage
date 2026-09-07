from pathlib import Path

import pandas as pd

from app.services.slipped_wells import get_slipped_wells


# ============================================================
# LOAD SQL
# ============================================================

SQL_FILE = (
    Path(__file__)
    .resolve()
    .parents[2]
    / "sql"
    / "well_summary.sql"
)


def get_well_summary(connection):

    query = SQL_FILE.read_text(
        encoding="utf-8"
    )

    counts = pd.read_sql(query, connection).iloc[0]

    total_wells = int(counts["total_wells"])
    live_wells = int(counts["live_wells"])
    completed_wells = int(counts["completed_wells"])

    df = get_slipped_wells(connection)

    if df.empty:
        due = 0
        non_due = 0
    else:
        due_counts = df["due_status"].value_counts()
        due = int(due_counts.get("DUE", 0))
        non_due = int(due_counts.get("NON_DUE", 0))

    return {
        "success": True,

        # Every well on record.
        "total_wells": total_wells,

        # Detection scope — a hooked-up well cannot slip.
        "live_wells": live_wells,
        "completed_wells": completed_wells,

        # Tasnim-side risk: the actionable list.
        "slipped_wells": due,

        # Delay attributed to FLAF / SCR / PDO-side causes.
        "non_due_wells": non_due,

        "not_slipped_wells": live_wells - (due + non_due)
    }
