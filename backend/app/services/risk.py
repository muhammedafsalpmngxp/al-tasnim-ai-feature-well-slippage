import math
from datetime import date, timedelta

import pandas as pd

from app.services.attribution import classify_due_status
from app.services.investigation import clean_value


# ============================================================
# TUNABLE CONSTANTS (v1 heuristic — not a trained model)
# ============================================================
#
# These thresholds encode the rules described by the business:
#   - Before Drilling: construction must finish 1 day before
#     RIG_ON. Risk ramps up over a 60-day window (matching the
#     existing pegging-deadline window already used elsewhere
#     in this project) and spikes once the deadline is missed.
#   - After Drilling: a well is "due" once
#     today > rig_off_date + 2 days (Hoist On/Off and Wellpad
#     Handover dates are not yet available in the schema, so
#     they are intentionally omitted from this calculation).
#
# Tune these once real outcomes are available to validate against.

BEFORE_DRILLING_WINDOW_DAYS = 60
BEFORE_DRILLING_OVERDUE_BASE_SCORE = 60
BEFORE_DRILLING_OVERDUE_SCORE_PER_DAY = 2
BEFORE_DRILLING_MIN_PROBLEM_SEVERITY = 0.2
BEFORE_DRILLING_PROBLEM_TASKS_FOR_FULL_SEVERITY = 3

AFTER_DRILLING_HOOKUP_GRACE_DAYS = 2
AFTER_DRILLING_OVERDUE_BASE_SCORE = 50
AFTER_DRILLING_OVERDUE_SCORE_PER_DAY = 3
AFTER_DRILLING_LOOKAHEAD_DAYS = 14
AFTER_DRILLING_ANTICIPATORY_MAX_SCORE = 30

CONSTRUCTION_PROJECT_TYPES = {"FLOWLINE", "LOCATION"}

TOP_WBS_BRANCHES = 5

MILESTONE_FIELDS = (
    "pegging_status",
    "flaf_status",
    "construction_status",
    "hookup_status"
)

# Per-activity fields exposed in delayed_activities, in output order.
ACTIVITY_FIELDS = (
    "task_id",
    "project_type",
    "activity_id",
    "activity_code",
    "activity",
    "crew",
    "progress_percent",
    "completed",
    "target_start",
    "target_end",
    "actual_start",
    "actual_end",
    "remaining_duration",
    "end_status",
    "delay_days",
    "execution_status",
    "schedule_risk",
    "target_achievability",
    "productivity_status",
    "resource_status"
)

ACTIVITY_BOOL_FIELDS = {"completed"}

ACTIVITY_NUMBER_FIELDS = {
    "task_id",
    "progress_percent",
    "remaining_duration",
    "delay_days"
}

EVIDENCE_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


# ============================================================
# VALUE HELPERS
# ============================================================

def _number(value):

    """
    Keep whole numbers whole: a pandas column containing NULLs is
    float-typed, which would otherwise render delay_days as 32.0.
    """

    if value is None or isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):

        if math.isnan(value) or math.isinf(value):
            return None

        return int(value) if value.is_integer() else round(value, 2)

    return value


def _normalize_text(series):

    # Activity descriptions in the source data contain embedded
    # newlines — collapse whitespace so labels group and display
    # consistently.
    return (
        series
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def _strongest_evidence(task_df, column):

    if column not in task_df.columns:
        return None

    levels = [
        value
        for value in task_df[column].dropna().unique()
        if value in EVIDENCE_RANK
    ]

    if not levels:
        return None

    return max(levels, key=lambda level: EVIDENCE_RANK[level])


# ============================================================
# SCENARIO CLASSIFICATION
# ============================================================

def classify_scenario(well_row):

    if well_row.get("eng_completion_date"):
        return "COMPLETED"

    if not well_row.get("rig_on_date"):
        return "BEFORE_DRILLING"

    if not well_row.get("rig_off_date"):
        return "DRILLING_IN_PROGRESS"

    return "AFTER_DRILLING"


# ============================================================
# BEFORE-DRILLING RISK
# ============================================================

def score_before_drilling(well_row, task_df, today):

    ex_rig_on_date = well_row.get("ex_rig_on_date")

    if not ex_rig_on_date:

        return {
            "due_status": None,
            "risk_score": None,
            "expected_delay_days": None,
            "note": (
                "Missing ex_rig_on_date — construction deadline "
                "cannot be evaluated (data quality issue)."
            )
        }

    construction_deadline = ex_rig_on_date - timedelta(days=1)
    days_to_deadline = (construction_deadline - today).days

    if "project_type" in task_df.columns:
        construction_tasks = task_df[
            task_df["project_type"]
            .fillna("")
            .str.upper()
            .isin(CONSTRUCTION_PROJECT_TYPES)
        ]
    else:
        construction_tasks = task_df

    if days_to_deadline < 0:

        overdue_days = -days_to_deadline

        risk_score = min(
            100,
            BEFORE_DRILLING_OVERDUE_BASE_SCORE
            + overdue_days * BEFORE_DRILLING_OVERDUE_SCORE_PER_DAY
        )

        return {
            "due_status": "DUE",
            "risk_score": risk_score,
            "expected_delay_days": overdue_days,
            "note": None
        }

    urgency = 1 - min(days_to_deadline / BEFORE_DRILLING_WINDOW_DAYS, 1)

    problem_severity = min(
        1.0,
        len(construction_tasks)
        / BEFORE_DRILLING_PROBLEM_TASKS_FOR_FULL_SEVERITY
    )

    severity = max(problem_severity, BEFORE_DRILLING_MIN_PROBLEM_SEVERITY * urgency)

    risk_score = round(100 * urgency * severity)

    max_remaining = 0

    if not construction_tasks.empty and "remaining_duration" in construction_tasks.columns:

        remaining_values = pd.to_numeric(
            construction_tasks["remaining_duration"],
            errors="coerce"
        ).dropna()

        if not remaining_values.empty:
            max_remaining = max(0, int(remaining_values.max()))

    expected_delay_days = max(0, max_remaining - days_to_deadline)

    return {
        "due_status": "NON_DUE",
        "risk_score": risk_score,
        "expected_delay_days": expected_delay_days,
        "note": None
    }


# ============================================================
# AFTER-DRILLING RISK
# ============================================================

def score_after_drilling(well_row, task_df, today):

    rig_off_date = well_row.get("rig_off_date")

    due_date = rig_off_date + timedelta(days=AFTER_DRILLING_HOOKUP_GRACE_DAYS)
    days_overdue = (today - due_date).days

    if days_overdue > 0:

        risk_score = min(
            100,
            AFTER_DRILLING_OVERDUE_BASE_SCORE
            + days_overdue * AFTER_DRILLING_OVERDUE_SCORE_PER_DAY
        )

        return {
            "due_status": "DUE",
            "risk_score": risk_score,
            "expected_delay_days": days_overdue,
            "note": None
        }

    days_remaining = -days_overdue

    proximity = max(
        0,
        1 - (days_remaining / AFTER_DRILLING_LOOKAHEAD_DAYS)
    )

    risk_score = round(AFTER_DRILLING_ANTICIPATORY_MAX_SCORE * proximity)

    return {
        "due_status": "NON_DUE",
        "risk_score": risk_score,
        "expected_delay_days": 0,
        "note": None
    }


# ============================================================
# LAGGING WBS BRANCHES
# ============================================================

def lagging_wbs_branches(task_df, top_n=TOP_WBS_BRANCHES):

    if task_df.empty:
        return []

    df = task_df.copy()

    df["branch"] = _normalize_text(
        df.get("activity")
        .fillna(df.get("activity_code"))
        .fillna("UNSPECIFIED")
        .astype(str)
    )

    df["delay_days_numeric"] = pd.to_numeric(
        df.get("delay_days"),
        errors="coerce"
    ).fillna(0)

    grouped = (
        df.groupby("branch")
        .agg(
            delayed_task_count=("branch", "count"),
            max_delay_days=("delay_days_numeric", "max")
        )
        .reset_index()
        .sort_values(
            ["max_delay_days", "delayed_task_count"],
            ascending=False
        )
        .head(top_n)
    )

    return [
        {
            "branch": row["branch"],
            "delayed_task_count": int(row["delayed_task_count"]),
            "max_delay_days": int(row["max_delay_days"])
        }
        for row in grouped.to_dict(orient="records")
    ]


# ============================================================
# DELAYED ACTIVITIES
# ============================================================

def delayed_activities(task_df):

    """
    Every delayed / at-risk activity for the well.

    investigation.sql already filters to delayed and at-risk rows
    and orders them worst-first, so that order is preserved here.
    """

    if task_df.empty:
        return []

    df = task_df.copy()

    if "activity" in df.columns:
        df["activity"] = _normalize_text(df["activity"])

    available_columns = [
        column for column in ACTIVITY_FIELDS if column in df.columns
    ]

    records = df[available_columns].to_dict(orient="records")

    activities = []

    for record in records:

        activity = {}

        # Iterate the full field list so the shape stays stable
        # even if a column is absent from the result set.
        for field in ACTIVITY_FIELDS:

            value = clean_value(record.get(field))

            if field in ACTIVITY_BOOL_FIELDS:
                value = None if value is None else bool(value)

            elif field in ACTIVITY_NUMBER_FIELDS:
                value = _number(value)

            activity[field] = value

        activities.append(activity)

    return activities


# ============================================================
# DATA QUALITY ROLL-UP
# ============================================================

def data_quality(well_row, task_df):

    """
    investigation.sql computes these per activity; roll them up to
    the well.

    has_issue is true if any activity is flagged, or if a milestone
    could not be evaluated at all (which happens when a baseline
    date is missing, and is itself a data-quality problem).

    Evidence levels report the STRONGEST evidence available across
    the well's activities.
    """

    milestone_issue = any(
        well_row.get(field) == "DATA_QUALITY_ISSUE"
        for field in MILESTONE_FIELDS
    )

    activity_issue = False

    if not task_df.empty and "has_data_quality_issue" in task_df.columns:

        flags = pd.to_numeric(
            task_df["has_data_quality_issue"],
            errors="coerce"
        ).fillna(0)

        activity_issue = bool(flags.max())

    return {
        "has_issue": bool(activity_issue or milestone_issue),
        "schedule_evidence_level": _strongest_evidence(
            task_df, "schedule_evidence_level"
        ),
        "data_evidence_level": _strongest_evidence(
            task_df, "data_evidence_level"
        )
    }


# ============================================================
# ORCHESTRATOR
# ============================================================

def build_well_risk_summary(well_row, task_df):

    today = date.today()

    scenario = classify_scenario(well_row)

    if scenario == "BEFORE_DRILLING":
        risk = score_before_drilling(well_row, task_df, today)

    elif scenario == "AFTER_DRILLING":
        risk = score_after_drilling(well_row, task_df, today)

    else:
        risk = {
            "due_status": None,
            "risk_score": None,
            "expected_delay_days": None,
            "note": (
                "Drilling in progress — outside current risk-scoring scope."
                if scenario == "DRILLING_IN_PROGRESS"
                else None
            )
        }

    return {

        "success": True,

        "well": {
            "well_id": well_row.get("well_id"),
            "ex_rig_on_date": clean_value(well_row.get("ex_rig_on_date")),
            "rig_on_date": clean_value(well_row.get("rig_on_date")),
            "ex_rig_off_date": clean_value(well_row.get("ex_rig_off_date")),
            "rig_off_date": clean_value(well_row.get("rig_off_date")),
            "pegged_date": clean_value(well_row.get("pegged_date")),
            "flaf_issue_date": clean_value(well_row.get("flaf_issue_date")),
            "eng_completion_date": clean_value(well_row.get("eng_completion_date")),
            "well_progress": clean_value(well_row.get("well_progress_raw")),
            "flowline_progress": _number(
                clean_value(well_row.get("flowline_const_progress"))
            )
        },

        "milestones": {
            field: well_row.get(field)
            for field in MILESTONE_FIELDS
        },

        "risk": {
            "scenario": scenario,

            # Has this well's own deadline passed?
            "deadline_status": risk["due_status"],

            # Is the delay Tasnim's to own, or FLAF/SCR/PDO-side?
            "due_status": classify_due_status(well_row.get("kpi_miss_reason")),
            "kpi_miss_reason": well_row.get("kpi_miss_reason"),

            "risk_score": risk["risk_score"],
            "expected_delay_days": risk["expected_delay_days"],
            "note": risk.get("note"),
            "lagging_wbs_branches": lagging_wbs_branches(task_df)
        },

        "delayed_activities": delayed_activities(task_df),

        "data_quality": data_quality(well_row, task_df)
    }
