"""
Which authoritative-SQL column describes which milestone gate.

This is a MAPPING TABLE, not a rule set. Every expected date, actual
date, delay and status named here is computed by
backend/sql/well_evidence.sql. Nothing in this project may recompute
them — the UI JSON and the AI evidence JSON both read them through here,
so the two can never disagree.
"""

MILESTONE_GATES = (
    {
        "key": "rig_on",
        "name": "Rig-on",
        "expected": "ex_rig_on_date",
        "actual": "rig_on_date",
        "delay_days": "rig_on_delay_days",
        "status": "rig_on_status",
        "variance_days": None
    },
    {
        "key": "rig_off",
        "name": "Rig-off",
        "expected": "ex_rig_off_date",
        "actual": "rig_off_date",
        "delay_days": "rig_off_delay_days",
        "status": "rig_off_status",
        "variance_days": None
    },
    {
        "key": "pegging",
        "name": "Pegging",
        "expected": "pegging_deadline",
        "actual": "pegged_date",
        "delay_days": "pegging_delay_days",
        "status": "pegging_status",
        # Signed variance is kept as evidence: a well pegged early has a
        # negative variance while its delay_days reads 0.
        "variance_days": "pegging_variance_days"
    },
    {
        "key": "flaf",
        "name": "FLAF",
        "expected": "flaf_deadline",
        "actual": "flaf_issue_date",
        "delay_days": "flaf_delay_days",
        "status": "flaf_status",
        "variance_days": "flaf_variance_days"
    },
    {
        "key": "construction",
        "name": "Construction",
        "expected": "construction_deadline",
        # The construction gate is "did rig-on happen by the deadline",
        # so rig_on_date is its actual - see section 2 of the SQL.
        "actual": "rig_on_date",
        "delay_days": "construction_lag_days",
        "status": "construction_status",
        "variance_days": None
    },
    {
        "key": "hookup",
        "name": "Hook-up",
        "expected": "hookup_deadline",
        "actual": "eng_completion_date",
        "delay_days": "hookup_delay_days",
        "status": "hookup_status",
        "variance_days": None
    }
)


# The four gate statuses the dashboard's Milestones panel shows, in the
# SQL's own column names.
MILESTONE_STATUS_COLUMNS = (
    "pegging_status",
    "flaf_status",
    "construction_status",
    "hookup_status"
)


# SQL status values that mean "this gate has slipped". Used only to count
# how many gates slipped (the risk score's breadth term) — never to
# decide whether an individual gate is late, which the SQL already says.
SLIPPED_MILESTONE_STATUSES = frozenset({
    "MISSED",
    "DELAYED",
    "OVERDUE",
    "HOOKUP_DEADLINE_PASSED",
    "HOOKUP_DEADLINE_FORECAST_PASSED"
})


def gate_by_key(key):

    for gate in MILESTONE_GATES:
        if gate["key"] == key:
            return gate

    return None
