"""Dashboard calculations for the active well portfolio."""

from pathlib import Path

SQL_FILE = (
    Path(__file__)
    .resolve()
    .parents[2]
    / "sql"
    / "calculation.sql"
)


def calculate_well_metrics(connection, wells):
    """Return dashboard counts for all wells and the active portfolio."""
    query = SQL_FILE.read_text(encoding="utf-8")
    cursor = connection.cursor()

    try:
        cursor.execute(query)
        count_row = cursor.fetchone()
    finally:
        cursor.close()

    total_wells = int(count_row[0] or 0)
    live_wells = int(count_row[1] or 0)
    slipped_wells = len(wells)
    non_due_wells = sum(
        1
        for well in wells
        if str(well.get("well_slippage_status", "")).upper() == "SLIPPED - FLAF"
    )
    due_wells = slipped_wells - non_due_wells

    return {
        "total_wells": total_wells,
        "live_wells": live_wells,
        "slipped_wells": slipped_wells,
        "due_wells": due_wells,
        "non_due_wells": non_due_wells,
        "due_owner": "Al Tasnim",
        "non_due_owner": "PDO",
    }