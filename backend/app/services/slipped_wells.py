from pathlib import Path

import pandas as pd

from app.services.attribution import classify_due_status


# ============================================================
# LOAD SQL
# ============================================================

SQL_FILE = (
    Path(__file__)
    .resolve()
    .parents[2]
    / "sql"
    / "slipped_wells.sql"
)


# ============================================================
# SLIP REASONS
# ============================================================
#
# slipped_wells.sql emits one flag per milestone test. These are
# turned into a human-readable reason list so the UI can say WHY
# a well is in the list, rather than just that it is.

SLIP_REASON_LABELS = {
    "slip_rig_on": "RIG_ON",
    "slip_rig_off": "RIG_OFF",
    "slip_hookup": "HOOKUP",
    "slip_construction": "CONSTRUCTION",
    "slip_pegging": "PEGGING",
    "slip_flaf": "FLAF"
}

DQ_FLAGS = (
    "dq_rig_off_before_rig_on",
    "dq_missing_baseline",
    "dq_actual_far_before_plan"
)


def _slip_reasons(row):

    return [
        label
        for column, label in SLIP_REASON_LABELS.items()
        if row.get(column)
    ]


def get_slipped_wells(connection):

    query = SQL_FILE.read_text(
        encoding="utf-8"
    )

    df = pd.read_sql(
        query,
        connection
    )

    if df.empty:
        return df

    df["slip_reasons"] = df.apply(_slip_reasons, axis=1)

    df["due_status"] = df["kpi_miss_reason"].map(classify_due_status)

    df["has_data_issue"] = df.apply(
        lambda row: any(bool(row.get(flag)) for flag in DQ_FLAGS),
        axis=1
    )

    df = df.drop(
        columns=list(SLIP_REASON_LABELS) + list(DQ_FLAGS)
    )

    # SQL already orders by delay_days DESC; keep that ordering.
    return df.reset_index(drop=True)
