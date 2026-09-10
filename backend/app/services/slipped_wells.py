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
    "dq_missing_baseline"
)


def _slip_reasons(row):

    return [
        label
        for column, label in SLIP_REASON_LABELS.items()
        if row.get(column)
    ]


# ============================================================
# PICKER CATEGORIES
# ============================================================
#
# The dashboard's well picker colours every well by one of four
# mutually exclusive states. The display wording lives here rather than
# in the frontend so the classification and its label have one home.
#
# AL TASNIM / PDO are the business names for the accountability split
# the evidence layer already computes (DUE / NON_DUE): a slipped well
# Al Tasnim owns, versus one attributed to PDO-side causes.

WELL_CATEGORY_LABELS = {
    "COMPLETED": "Completed",
    "AL_TASNIM": "AL TASNIM",
    "PDO": "PDO",
    "ON_TRACK": "On track"
}


def _read_wells(connection):

    """
    Every well, classified. slipped_wells.sql returns one row per well
    with its is_completed / is_slipped verdicts already decided.
    """

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

    return df.drop(
        columns=list(SLIP_REASON_LABELS) + list(DQ_FLAGS)
    )


def _category(row):

    """
    One state per well, in precedence order. Completion wins: a
    hooked-up well is reported as completed rather than by whatever its
    milestones once looked like.
    """

    if row["is_completed"] == 1:
        return "COMPLETED"

    if row["is_slipped"] != 1:
        return "ON_TRACK"

    return "AL_TASNIM" if row["due_status"] == "DUE" else "PDO"


def get_slipped_wells(connection):

    """
    The slipped wells only — the existing contract, used by the summary
    counts and the portfolio narrative. The SQL now returns every well,
    so the slipped subset is selected on its is_slipped verdict.
    """

    df = _read_wells(connection)

    if df.empty:
        return df

    slipped = df[df["is_slipped"] == 1]

    # Constant once filtered, so they would only be noise downstream.
    return (
        slipped
        .drop(columns=["is_slipped", "is_completed"])
        .reset_index(drop=True)
    )


def get_well_list(connection):

    """
    Every well for the dashboard picker: the id and its category, and
    nothing else. Ordered ascending by well_id by the SQL.
    """

    df = _read_wells(connection)

    if df.empty:
        return []

    wells = []

    for _, row in df.iterrows():

        category = _category(row)

        wells.append({
            "well_id": int(row["well_id"]),
            "category": category,
            "category_label": WELL_CATEGORY_LABELS[category]
        })

    return wells
