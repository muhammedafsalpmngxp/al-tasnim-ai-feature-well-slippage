"""
PYTHON TRANSFORMATION -> UI JSON

Structures the raw deterministic evidence for the React dashboard.

This module RENAMES, GROUPS and FORMATS. It does not calculate. Every
date, delay, status, variance and classification here is copied from the
authoritative SQL result; the only derived values are the risk composite
(see risk.py) and the due/non-due attribution (see attribution.py), both
of which are documented as Python-side because the SQL does not produce
them.
"""

from app.services.attribution import classify_due_status
from app.services.evidence import delayed_activity_rows
from app.services.milestones import MILESTONE_GATES, MILESTONE_STATUS_COLUMNS
from app.services.risk import lagging_wbs_branches, risk_band, score_well
from app.services.serialization import (
    clean_date,
    clean_value,
    normalize_text,
    to_number
)


# Activity fields the dashboard renders, mapped from their authoritative
# SQL column names. Renaming only.
#
# business_rules.md §7/§8: crew/employee/equipment evidence must NOT be
# collapsed into one generic field — master_crew_code (the master
# mapping's crew), planned_crew, crew_id and crew_type_id are different
# concepts on different source columns and are kept separate. The user
# has explicitly said Crew ID and Crew Type ID may be shown directly.
ACTIVITY_FIELD_MAP = (
    ("task_id", "task_daily_id"),
    ("project_type", "project_type"),
    ("activity_id", "activity_id"),
    ("activity_code", "activity_code"),

    # business_rules.md §3: activity_group_description IS the WBS, not the
    # activity's name. An activity is identified by activity_code. §10
    # forbids interchanging the two, so this is exposed as `wbs`.
    ("wbs", "activity_group_description"),

    # From the master mapping (activity_master_csv.crew_code) — distinct
    # from the raw task_daily crew/resource columns below.
    ("master_crew_code", "master_crew_code"),

    # Raw task_daily resource evidence, each its own field.
    ("planned_crew", "planned_crew"),
    ("crew_id", "crew_id"),
    ("crew_type_id", "crew_type_id"),
    ("emp_id", "emp_id"),
    ("data_employees", "data_employees"),
    ("daily_employee_ids", "daily_employee_ids"),
    ("daily_equipment_ids", "daily_equipment_ids"),

    ("progress_percent", "progress_percent"),
    ("completed", "completed"),
    ("target_start", "target_start"),
    ("target_end", "target_end"),
    ("actual_start", "actual_start"),
    ("actual_end", "actual_end"),
    ("remaining_duration", "remaining_duration"),
    ("end_status", "end_status"),
    ("delay_days", "end_variance_days"),
    ("execution_status", "execution_status"),
    ("schedule_risk", "schedule_risk"),
    ("target_achievability", "target_achievability"),
    ("productivity_status", "productivity_data_status"),
    ("resource_status", "resource_data_status")
)

ACTIVITY_DATE_FIELDS = frozenset({
    "target_start", "target_end", "actual_start", "actual_end"
})

ACTIVITY_NUMBER_FIELDS = frozenset({
    "task_id", "progress_percent", "remaining_duration", "delay_days",
    "crew_id", "crew_type_id", "emp_id"
})

ACTIVITY_TEXT_FIELDS = frozenset({
    "wbs", "master_crew_code", "planned_crew",
    "data_employees", "daily_employee_ids", "daily_equipment_ids"
})

EVIDENCE_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


# ============================================================
# DATA-QUALITY ROLL-UP
# ============================================================

def _true_dq_flags(row):

    """
    Names of the SQL's dq_* flags that are set on this row. Discovered by
    prefix rather than from a fixed list, so a new flag added to the
    evidence layer is picked up automatically.
    """

    return [
        column
        for column, value in row.items()
        if column.startswith("dq_") and to_number(value) == 1
    ]


def _strongest_evidence_level(activities, column):

    levels = {
        activity.get(column)
        for activity in activities
        if activity.get(column) in EVIDENCE_RANK
    }

    if not levels:
        return None

    return max(levels, key=lambda level: EVIDENCE_RANK[level])


def build_data_quality(well_row, activities, delayed):

    """
    Roll the SQL's per-row data-quality verdicts up to the well.

    has_issue and the flag lists span EVERY current task, so a problem on
    a task that happens not to be delayed is still surfaced rather than
    hidden.

    The evidence LEVELS are scoped to the delayed activities, because
    they qualify the confidence behind the delays being reported — the
    strongest level among rows that are not part of the finding would
    overstate it.

    Nothing is inferred beyond OR-ing / ranking the SQL's own verdicts.
    """

    well_flags = _true_dq_flags(well_row)

    activity_flags = set()

    for activity in activities:
        activity_flags.update(_true_dq_flags(activity))

    activity_issue = any(
        to_number(activity.get("has_data_quality_issue")) == 1
        for activity in activities
    )

    unevaluated_gates = [
        column
        for column in MILESTONE_STATUS_COLUMNS
        if well_row.get(column) == "DATA_QUALITY_ISSUE"
    ]

    return {
        "has_issue": bool(
            well_flags or activity_issue or unevaluated_gates
        ),
        "schedule_evidence_level": _strongest_evidence_level(
            delayed, "schedule_evidence_level"
        ),
        "data_evidence_level": _strongest_evidence_level(
            delayed, "data_evidence_level"
        ),
        # Only the flags that are actually set — a list of false flags
        # would be noise.
        "well_flags": sorted(well_flags),
        "activity_flags": sorted(activity_flags),
        "unevaluated_gates": unevaluated_gates
    }


# ============================================================
# MILESTONES
# ============================================================

def build_milestone_delays(well_row):

    """
    Expected date, actual date, days late and status for each gate — all
    read directly from the authoritative SQL columns named in
    milestones.MILESTONE_GATES.
    """

    delays = {}

    for gate in MILESTONE_GATES:

        entry = {
            "name": gate["name"],
            "expected": clean_date(well_row.get(gate["expected"])),
            "actual": clean_date(well_row.get(gate["actual"])),
            "delay_days": to_number(well_row.get(gate["delay_days"])),
            "status": well_row.get(gate["status"])
        }

        # Signed variance, where the SQL provides it, so an early gate
        # keeps its negative number as evidence next to a delay of 0.
        if gate["variance_days"]:
            entry["variance_days"] = to_number(
                well_row.get(gate["variance_days"])
            )

        delays[gate["key"]] = entry

    return delays


# ============================================================
# ACTIVITIES
# ============================================================

def build_delayed_activities(activities):

    """
    The delayed / at-risk activities, projected onto the dashboard's field
    names. Ordering follows the authoritative SQL's own ORDER BY.
    """

    rows = []

    for activity in delayed_activity_rows(activities):

        record = {}

        for field, column in ACTIVITY_FIELD_MAP:

            value = activity.get(column)

            if field in ACTIVITY_DATE_FIELDS:
                record[field] = clean_date(value)

            elif field in ACTIVITY_NUMBER_FIELDS:
                record[field] = to_number(clean_value(value))

            elif field in ACTIVITY_TEXT_FIELDS:
                record[field] = normalize_text(clean_value(value))

            elif field == "completed":
                cleaned = clean_value(value)
                record[field] = None if cleaned is None else bool(cleaned)

            else:
                record[field] = clean_value(value)

        rows.append(record)

    return rows


# ============================================================
# UI JSON
# ============================================================

def build_ui_json(raw_evidence, project_ids=None, crews=None):

    """
    raw_evidence comes from evidence.get_well_evidence(); project_ids from
    the separate project lookup; crews from crew.get_well_crews(). Returns
    the dashboard payload, preserving the existing API contract.
    """

    well_row = raw_evidence["well"]
    activities = raw_evidence["activities"]

    delayed = delayed_activity_rows(activities)

    risk = score_well(well_row, delayed)

    return {

        "success": True,

        "well": {
            "well_id": to_number(well_row.get("well_id")),
            "ex_rig_on_date": clean_date(well_row.get("ex_rig_on_date")),
            "rig_on_date": clean_date(well_row.get("rig_on_date")),
            "ex_rig_off_date": clean_date(well_row.get("ex_rig_off_date")),
            "rig_off_date": clean_date(well_row.get("rig_off_date")),
            "pegged_date": clean_date(well_row.get("pegged_date")),
            "flaf_issue_date": clean_date(well_row.get("flaf_issue_date")),
            "eng_completion_date": clean_date(
                well_row.get("eng_completion_date")
            ),
            "well_progress": clean_value(well_row.get("well_progress_raw")),
            "flowline_progress": to_number(
                clean_value(well_row.get("flowline_const_progress"))
            ),
            "remarks": normalize_text(clean_value(well_row.get("remarks"))),
            "project_ids": project_ids or [],

            # Crews recorded against this well's tasks, each with its
            # supervisors and employees. Resolved in SQL and grouped in
            # crew.py — see well_crew.sql.
            "crews": crews or []
        },

        # The four gate statuses, verbatim from the SQL.
        "milestones": {
            column: well_row.get(column)
            for column in MILESTONE_STATUS_COLUMNS
        },

        # Expected / actual / days-late per gate, all SQL-computed.
        "milestone_delays": build_milestone_delays(well_row),

        "risk": {
            "scenario": risk["scenario"],

            # Has this well's own deadline passed, per the SQL's delay
            # column for the scenario gate?
            "deadline_status": risk["deadline_status"],

            # Is the delay Tasnim's to own, or FLAF/SCR/PDO-side?
            "due_status": classify_due_status(well_row.get("kpi_miss_reason")),
            "kpi_miss_reason": well_row.get("kpi_miss_reason"),

            "risk_score": risk["risk_score"],

            # Band for display, classified here so the dashboard does not
            # own a business threshold.
            "risk_band": risk_band(risk["risk_score"]),

            "expected_delay_days": risk["expected_delay_days"],

            # Which gate the well-level delay measures. The slipped-well
            # list reports the WORST gate instead, so both figures must
            # be labelled with what they mean.
            "expected_delay_gate": risk["expected_delay_gate"],
            "note": risk["note"],

            "lagging_wbs_branches": lagging_wbs_branches(delayed)
        },

        "delayed_activities": build_delayed_activities(activities),

        "data_quality": build_data_quality(well_row, activities, delayed),

        # Context for the dashboard: how much evidence stood behind this.
        "evidence_counts": {
            "current_tasks": len(activities),
            "delayed_activities": len(delayed)
        }
    }
