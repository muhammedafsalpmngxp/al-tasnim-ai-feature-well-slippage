"""
Who owns a well's delay.

well_master.kpi_miss_reason records why a milestone was missed.
Delays attributed to FLAF / SCR / PDO-side causes are NON_DUE:
they are outside Tasnim's control, so they are reported as
"bonus potential" rather than counted as Tasnim-side risk.

Single source of truth — used by both the slipped-well list and
the per-well risk assessment.
"""

# Values seen in the source data are inconsistently cased and
# occasionally abbreviated, so reasons are normalised before
# matching and FLAF is matched as a substring.
NON_DUE_REASONS = {
    "SCR",
    "AWAITING MANIFOLD/MSV",
    "AWAITING HANDOVER",
    "WELL SUSPENDED",
    "NON KPI",
    "NON KPI WELL"
}

NON_DUE_SUBSTRINGS = ("FLAF",)


def normalize_reason(reason):

    if reason is None:
        return ""

    return " ".join(str(reason).split()).upper()


def classify_due_status(reason):

    normalized = normalize_reason(reason)

    if not normalized:
        return "DUE"

    if any(token in normalized for token in NON_DUE_SUBSTRINGS):
        return "NON_DUE"

    if normalized in NON_DUE_REASONS:
        return "NON_DUE"

    return "DUE"
