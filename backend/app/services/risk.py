"""
Risk scoring and scenario classification.

WHAT THIS MODULE MAY DO
    Combine deterministic facts the authoritative SQL already produced
    into the 0-100 composite score and the scenario label.

WHAT IT MUST NOT DO
    Calculate a date, a day difference, a milestone status, a delay or an
    attribution. Those come out of backend/sql/well_evidence.sql. There is
    no date arithmetic anywhere in this file — the lateness input is read
    straight from the SQL's own delay column for the relevant gate.

WHY THE SCORE LIVES HERE AND NOT IN SQL
    The authoritative SQL produces ai_schedule_classification,
    schedule_evidence_level and data_evidence_level, but it has no 0-100
    composite score. The dashboard needs one, so it is assembled here
    from SQL-supplied inputs. This is the only deliberate Python-side
    calculation in the evidence path, and it is documented as such.
"""

from app.services.milestones import (
    MILESTONE_STATUS_COLUMNS,
    SLIPPED_MILESTONE_STATUSES
)
from app.services.serialization import to_number


# ============================================================
# TUNABLE CONSTANTS (deterministic heuristic — not a trained model)
# ============================================================
#
# The score blends three normalised components so no single input can
# pin it at 100:
#
#   lateness  how far past the scenario's deadline   (saturating curve)
#   breadth   how many milestone gates have slipped  (0..1)
#   activity  delayed-activity count/severity        (0..1, may be unknown)
#
# Lateness uses days / (days + HALF_LIFE) rather than a linear ramp: a
# linear ramp hit its ceiling around 20 days overdue, which put 31% of
# wells at exactly 100 and could not tell a 30-day slip from a 300-day one.

LATENESS_HALF_LIFE_DAYS = 90

WEIGHT_LATENESS = 0.55
WEIGHT_BREADTH = 0.25
WEIGHT_ACTIVITY = 0.20

ACTIVITY_DELAY_HALF_LIFE_DAYS = 30
ACTIVITY_COUNT_FOR_FULL_SEVERITY = 5

TOP_WBS_BRANCHES = 5

# Score bands. Defined here rather than in the dashboard so the
# classification has one home and the frontend only renders it.
RISK_BAND_THRESHOLDS = (
    ("HIGH", 70),
    ("MEDIUM", 40),
    ("LOW", 0)
)


# Which SQL delay column measures the well's own lateness in each
# scenario. Before drilling, the gate is construction (rig-on must happen
# by ex_rig_on_date - 1). After drilling, it is hook-up (due at
# rig_off_date + 2). Both numbers are computed by the SQL.
# Scenarios with no scoring gate. Both are legitimate states rather than
# failures, so each says why no score is shown instead of leaving a blank.
UNSCORED_SCENARIO_NOTES = {
    "DRILLING_IN_PROGRESS": (
        "Drilling in progress — outside current risk-scoring scope."
    ),
    "COMPLETED": (
        "Hook-up complete — this well is finished, so it is outside "
        "slippage scoring. The evidence below is its final record."
    )
}


SCENARIO_DELAY_SOURCE = {
    "BEFORE_DRILLING": {
        "delay_column": "construction_lag_days",
        "status_column": "construction_status",
        "gate": "construction"
    },
    "AFTER_DRILLING": {
        "delay_column": "hookup_delay_days",
        "status_column": "hookup_status",
        "gate": "hookup"
    }
}


# ============================================================
# SCENARIO
# ============================================================

def classify_scenario(well_row):

    """
    Before / during / after drilling, from the three master dates the SQL
    returns. The authoritative SQL has no scenario column, so the label is
    derived here — by reading dates, never by comparing them to today.
    """

    if well_row.get("eng_completion_date"):
        return "COMPLETED"

    if not well_row.get("rig_on_date"):
        return "BEFORE_DRILLING"

    if not well_row.get("rig_off_date"):
        return "DRILLING_IN_PROGRESS"

    return "AFTER_DRILLING"


# ============================================================
# SCORE COMPONENTS
# ============================================================

def _saturating(value, half_life):

    """
    Map 0..inf onto 0..1 without ever reaching 1, so the score keeps
    discriminating no matter how large the input gets. Reaches 0.5 at
    `half_life`.
    """

    if not value or value <= 0:
        return 0.0

    return value / (value + half_life)


def _breadth_factor(well_row):

    """How many of the gate statuses the SQL reported have slipped."""

    slipped = sum(
        1
        for column in MILESTONE_STATUS_COLUMNS
        if well_row.get(column) in SLIPPED_MILESTONE_STATUSES
    )

    return slipped / len(MILESTONE_STATUS_COLUMNS)


def _activity_factor(delayed_activities):

    """
    Severity of the well's delayed activities, or None when there are no
    activity rows at all — the weight is then redistributed rather than
    scoring the well as though it had no problems.

    Reads each activity's SQL-computed end_variance_days.
    """

    if not delayed_activities:
        return None

    count_factor = min(
        1.0,
        len(delayed_activities) / ACTIVITY_COUNT_FOR_FULL_SEVERITY
    )

    delays = [
        to_number(activity.get("end_variance_days")) or 0
        for activity in delayed_activities
    ]

    worst_delay = max(delays) if delays else 0

    delay_factor = _saturating(worst_delay, ACTIVITY_DELAY_HALF_LIFE_DAYS)

    return (count_factor + delay_factor) / 2


def risk_band(risk_score):

    """
    Band a score for display. Returns None when there is no score, so the
    dashboard shows "no score" rather than implying low risk.
    """

    if risk_score is None:
        return None

    for band, threshold in RISK_BAND_THRESHOLDS:
        if risk_score >= threshold:
            return band

    return "LOW"


def _blend(lateness, breadth, activity):

    components = [
        (WEIGHT_LATENESS, lateness),
        (WEIGHT_BREADTH, breadth)
    ]

    if activity is not None:
        components.append((WEIGHT_ACTIVITY, activity))

    total_weight = sum(weight for weight, _ in components)

    weighted = sum(weight * value for weight, value in components)

    return round(100 * weighted / total_weight)


# ============================================================
# SCORING
# ============================================================

def score_well(well_row, delayed_activities):

    """
    Build the composite risk figure.

    `expected_delay_days` is NOT calculated here — it is the SQL's delay
    column for the scenario's own gate, so the number the dashboard shows
    is the same number the SQL computed.
    """

    scenario = classify_scenario(well_row)

    source = SCENARIO_DELAY_SOURCE.get(scenario)

    if source is None:

        return {
            "scenario": scenario,
            "deadline_status": None,
            "risk_score": None,
            "expected_delay_days": None,
            "expected_delay_gate": None,
            "note": UNSCORED_SCENARIO_NOTES.get(scenario)
        }

    delay_days = to_number(well_row.get(source["delay_column"]))
    gate_status = well_row.get(source["status_column"])

    # A NULL delay means the SQL could not evaluate the gate, because the
    # baseline date it needs is missing. That is a data-quality signal,
    # not a zero.
    if delay_days is None:

        return {
            "scenario": scenario,
            "deadline_status": None,
            "risk_score": None,
            "expected_delay_days": None,
            "expected_delay_gate": source["gate"],
            "note": (
                "Baseline date missing — this well's deadline could not be "
                "evaluated by the evidence layer (data quality issue)."
            )
        }

    # ---------- past the deadline ----------
    if delay_days > 0:

        breadth = _breadth_factor(well_row)
        activity = _activity_factor(delayed_activities)
        lateness = _saturating(delay_days, LATENESS_HALF_LIFE_DAYS)

        return {
            "scenario": scenario,
            "deadline_status": "DUE",
            "risk_score": _blend(lateness, breadth, activity),
            "expected_delay_days": delay_days,
            "expected_delay_gate": source["gate"],
            "note": None
        }

    # ---------- deadline not reached (SQL reports 0 days late) ----------
    #
    # On track: this well has not missed its own scenario gate, so there
    # is no lateness to score. A number here — even a low one — would
    # read as risk that does not exist yet, so no risk_score is shown at
    # all rather than an anticipatory figure, matching how a COMPLETED or
    # DRILLING_IN_PROGRESS well shows no score above.
    return {
        "scenario": scenario,
        "deadline_status": "NON_DUE",
        "risk_score": None,
        "expected_delay_days": delay_days,
        "expected_delay_gate": source["gate"],
        "note": (
            "The evidence layer flagged this gate as a data-quality issue."
            if gate_status == "DATA_QUALITY_ISSUE"
            else None
        )
    }


# ============================================================
# LAGGING WBS BRANCHES
# ============================================================

def lagging_wbs_branches(delayed_activities, top_n=TOP_WBS_BRANCHES):

    """
    Group the delayed activities by their WBS/activity branch name.

    Pure aggregation over SQL-supplied fields: the branch label and each
    delay come from the evidence layer, this only counts and ranks them.
    """

    if not delayed_activities:
        return []

    branches = {}

    for activity in delayed_activities:

        # business_rules.md §3: the WBS is ONLY
        # activity_master_csv.activity_group_description. It is not
        # wbs.activity_master.Activity, and it is not the activity code —
        # substituting either would report a non-WBS as a WBS. A task
        # whose mapping is absent is a real row of the breakdown, so it
        # is kept and labelled as unmapped rather than dropped.
        label = activity.get("activity_group_description")

        label = " ".join(str(label).split()) if label else "(unmapped)"

        delay = to_number(activity.get("end_variance_days")) or 0

        entry = branches.setdefault(
            label,
            {"branch": label, "delayed_task_count": 0, "max_delay_days": 0}
        )

        entry["delayed_task_count"] += 1
        entry["max_delay_days"] = max(entry["max_delay_days"], int(delay))

    ranked = sorted(
        branches.values(),
        key=lambda entry: (entry["max_delay_days"], entry["delayed_task_count"]),
        reverse=True
    )

    return ranked[:top_n]
