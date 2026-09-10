"""
PYTHON TRANSFORMATION -> AI EVIDENCE JSON

A compact, purpose-built view of the deterministic evidence, built for
one job: giving the LLM exactly the facts it needs to write a summary,
and nothing else.

The authoritative SQL returns ~170 activity columns and ~41 well columns.
Sending that to the model would be wasteful and would invite it to
interpret raw internals. What goes in here instead:

  KEPT      stage dates, per-gate expected/actual/delay/status,
            accountability, the delayed activities' own status fields
            (including the crew/resource identifiers business_rules.md
            §7 names — master_crew_code, crew_id, crew_type_id), the
            risk composite, lagging branches, remarks, projects, and
            only the data-quality flags that are actually set.

  DROPPED   task_data / daily_data blobs, url, created_at / updated_at /
            time_stamp, schedule_id, uom internal IDs, employee/equipment
            ID lists (emp_id / data_employees / daily_employee_ids /
            daily_equipment_ids — narratively not useful and the full
            UI JSON already exposes them), every mapping and CSV
            diagnostic count, WBS conflict counters, quantity and
            productivity intermediates, P6 reference dates, assignee
            emails, and any dq_* flag that is false.

Every value is copied from the evidence layer. This module derives
nothing.
"""

from app.services.attribution import classify_due_status
from app.services.milestones import MILESTONE_GATES
from app.services.serialization import (
    clean_date,
    clean_value,
    normalize_text,
    to_number
)


# Bound the prompt on wells with a long tail of delayed activities. The
# authoritative SQL orders them worst-first, so the truncation keeps the
# most delayed.
MAX_ACTIVITIES = 10

# Per-activity fields the narrative can actually use, mapped from the
# authoritative SQL column names.
ACTIVITY_FIELDS = (
    ("task_id", "task_daily_id"),
    ("activity_id", "activity_id"),
    ("activity_code", "activity_code"),

    # business_rules.md §3: this column is the WBS, not the activity's
    # name. Named `wbs` so the narrative cannot present it as an activity.
    ("wbs", "activity_group_description"),

    ("delay_days", "end_variance_days"),
    ("progress_percent", "progress_percent"),
    ("execution_status", "execution_status"),
    ("schedule_risk", "schedule_risk"),
    ("target_achievability", "target_achievability"),

    # business_rules.md §7/§8: distinct crew concepts, kept separate —
    # the user is explicitly comfortable with crew_id/crew_type_id being
    # shown. The raw employee/equipment ID lists are left out of this
    # compact object (see module docstring); they are still in the UI JSON.
    ("master_crew_code", "master_crew_code"),
    ("crew_id", "crew_id"),
    ("crew_type_id", "crew_type_id"),

    ("resource_status", "resource_data_status"),
    ("productivity_status", "productivity_data_status")
)

NUMBER_FIELDS = frozenset({
    "task_id", "delay_days", "progress_percent", "crew_id", "crew_type_id"
})

TEXT_FIELDS = frozenset({"wbs", "master_crew_code"})


def _accountability(due_status, kpi_miss_reason):

    """
    Turn the authoritative due_status into an unambiguous, ready-made
    sentence.

    The model was observed INVERTING the enum — reading NON_DUE and
    writing "attributed to Tasnim's responsibility" — so the enum is no
    longer left to interpretation. Python states the meaning once, from
    the deterministic verdict, and the model reproduces it. This does not
    decide accountability; attribution.classify_due_status already did.

    Wording follows business_rules.md §18: state the CLASSIFICATION
    ("is classified as NON-DUE under the current accountability rules"),
    not a strong ownership assertion — the underlying rule is
    kpi_miss_reason text matching only (see attribution.py); it does not
    yet implement the Location-vs-Flowline distinction in §6, so the
    wording must not claim more certainty than that.
    """

    cause = kpi_miss_reason or None

    if due_status == "NON_DUE":

        statement = (
            "This well is classified as NON-DUE under the current "
            f"accountability rules, with recorded reason '{cause}'."
            if cause else
            "This well is classified as NON-DUE under the current "
            "accountability rules. No reason is recorded."
        )
        owner = "NOT_TASNIM"

    elif due_status == "DUE":

        statement = (
            "This well is classified as DUE under the current "
            f"accountability rules, with recorded reason '{cause}'."
            if cause else
            "This well is classified as DUE under the current "
            "accountability rules. No reason is recorded."
        )
        owner = "TASNIM"

    else:

        statement = "Accountability could not be determined from the evidence."
        owner = None

    return {
        "due_status": due_status,
        "owner": owner,
        "kpi_miss_reason": cause,
        # Reproduce this meaning verbatim; never re-derive it.
        "statement": statement
    }


def _activity(activity):

    record = {}

    for field, column in ACTIVITY_FIELDS:

        value = activity.get(column)

        if field in NUMBER_FIELDS:
            record[field] = to_number(clean_value(value))

        elif field in TEXT_FIELDS:
            record[field] = normalize_text(clean_value(value))

        else:
            record[field] = clean_value(value)

    return record


def build_ai_evidence(raw_evidence, ui_json, project_ids=None):

    """
    Build the compact AI evidence object.

    Takes the numbers from `ui_json` where the UI already read them out of
    the SQL result, so the model and the dashboard are guaranteed to be
    quoting the same figures — there is no second interpretation of the
    database anywhere in this path.
    """

    well_row = raw_evidence["well"]

    ui_well = ui_json["well"]
    ui_risk = ui_json["risk"]
    ui_delays = ui_json["milestone_delays"]
    ui_dq = ui_json["data_quality"]

    # ---- milestones as a flat list, one entry per gate ----
    #
    # A list rather than a dict so the model reads them as parallel facts
    # and is less likely to blur one gate's delay into another's.
    milestones = []

    for gate in MILESTONE_GATES:

        entry = ui_delays.get(gate["key"]) or {}

        milestone = {
            "name": entry.get("name") or gate["name"],
            "expected": entry.get("expected"),
            "actual": entry.get("actual"),
            "delay_days": entry.get("delay_days"),
            "status": entry.get("status")
        }

        if "variance_days" in entry:
            milestone["variance_days"] = entry["variance_days"]

        milestones.append(milestone)

    # ---- delayed activities, capped ----
    delayed = ui_json.get("delayed_activities") or []

    raw_delayed = [
        activity
        for activity in raw_evidence["activities"]
        if activity.get("schedule_risk") == "RED_DELAYED"
        or activity.get("end_status") == "OVERDUE_CURRENT_TASK_LAGGING"
        or activity.get("ai_schedule_classification") == "DELAYED"
    ]

    activities = [_activity(activity) for activity in raw_delayed[:MAX_ACTIVITIES]]

    evidence = {

        "well_id": ui_well.get("well_id"),

        "stage": {
            "scenario": ui_risk.get("scenario"),
            "rig_on_date": ui_well.get("rig_on_date"),
            "rig_off_date": ui_well.get("rig_off_date"),
            "eng_completion_date": ui_well.get("eng_completion_date")
        },

        "accountability": _accountability(
            ui_risk.get("due_status"),
            ui_risk.get("kpi_miss_reason")
        ),

        "milestones": milestones,

        "delayed_activities": activities,

        "risk": {
            "risk_score": ui_risk.get("risk_score"),

            # The well-level delay, and WHICH gate it measures — so the
            # narrative cannot confuse it with an activity's delay.
            "expected_delay_days": ui_risk.get("expected_delay_days"),
            "expected_delay_gate": ui_risk.get("expected_delay_gate"),
            "deadline_status": ui_risk.get("deadline_status"),

            "lagging_wbs_branches": ui_risk.get("lagging_wbs_branches") or []
        },

        "remarks": ui_well.get("remarks"),

        "data_quality": {
            "has_issue": ui_dq.get("has_issue"),
            "schedule_evidence_level": ui_dq.get("schedule_evidence_level"),
            "data_evidence_level": ui_dq.get("data_evidence_level"),
            # Set flags only; false ones are omitted entirely. A flag can
            # be raised at both well and activity level, so de-duplicate
            # or the narrative repeats it.
            "flags": sorted(set(
                (ui_dq.get("well_flags") or [])
                + (ui_dq.get("activity_flags") or [])
            )),
            "unevaluated_gates": ui_dq.get("unevaluated_gates") or []
        },

        "counts": {
            "current_tasks": ui_json["evidence_counts"]["current_tasks"],
            "delayed_activities": len(raw_delayed)
        }
    }

    if ui_risk.get("note"):
        evidence["risk"]["note"] = ui_risk["note"]

    projects = project_ids or ui_well.get("project_ids") or []

    if projects:
        evidence["projects"] = [
            {
                "project_code": project.get("project_code"),
                "project_name": project.get("project_name")
            }
            for project in projects
        ]

    if len(raw_delayed) > MAX_ACTIVITIES:
        evidence["delayed_activities_truncated_from"] = len(raw_delayed)

    return evidence


# ============================================================
# HIGHLIGHT TERMS
# ============================================================
#
# Words the model is likely to quote verbatim FROM the database, so the
# frontend can colour them differently from the numeric figures. Built
# per response from the evidence actually present — never a fixed list.
#
# Raw status enums are deliberately excluded: once translated into prose
# ("due", "missed") they are ordinary English words, and highlighting
# them would colour normal sentence structure rather than data.

MIN_TERM_LENGTH = 3


def _collect(*values):

    terms = set()

    for value in values:

        if not isinstance(value, str):
            continue

        text = " ".join(value.split())

        if len(text) >= MIN_TERM_LENGTH:
            terms.add(text)

    # Longest first, so a multi-word term is matched before a shorter
    # term that is a substring of it.
    return sorted(terms, key=len, reverse=True)


def highlight_terms(ai_evidence):

    terms = [
        ai_evidence.get("accountability", {}).get("kpi_miss_reason"),
        ai_evidence.get("remarks")
    ]

    for activity in ai_evidence.get("delayed_activities") or []:
        terms.append(activity.get("wbs"))
        terms.append(activity.get("activity_code"))
        terms.append(activity.get("activity_id"))

    for branch in ai_evidence.get("risk", {}).get("lagging_wbs_branches") or []:
        terms.append(branch.get("branch"))

    for project in ai_evidence.get("projects") or []:
        terms.append(project.get("project_code"))
        terms.append(project.get("project_name"))

    return _collect(*terms)
