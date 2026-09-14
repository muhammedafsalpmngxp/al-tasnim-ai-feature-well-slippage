"""
Task prompt for well delay analysis.

The BUSINESS RULES document is loaded separately and is authoritative.
"""

DELAY_ANALYSIS_PROMPT = """\
# TASK — WELL DELAY ANALYSIS

Analyse the selected well and explain clearly **why it is delayed** using ONLY the
information provided in the JSON. The BUSINESS RULES are authoritative and must
always be followed.

Do not guess or invent a root cause, dependency, resource shortage, penalty, or
recovery plan that is not supported by the supplied evidence.

## Input

The JSON may contain:

- `well` — basic well information, Rig-On/Rig-Off dates, completion date,
  progress, and other well-level information.
- `milestones` — pegging, FLAF, construction, and hook-up status, deadlines,
  actual dates, and delay/variance information.
- `delayed_activities` — task-level information for activities that are delayed
  or overdue, including target dates, actual dates, progress, and resources.
- `data_quality` — recorded data-quality problems.

Use the **well-level information first** to understand the overall situation.
Use task and activity information as supporting evidence.

## How to interpret the data

- `null` means the value is **not recorded**. It does not mean zero, completed,
  on time, delayed, or that a resource is unavailable.
- Use the supplied status, deadline, and variance fields as they are.
- Do not recalculate deadlines or delay values from the raw dates.
- Do not replace a supplied status with your own interpretation.

### Important deadline rule

A missing actual date does NOT automatically mean that the milestone or task was
missed.

For example:
- A future deadline + missing actual date = not yet due/open condition.
- A past deadline + missing actual date = missed/overdue only when the supplied
  status or evidence confirms it.
- Do not describe a future deadline as already missed or delayed.

### Construction rule

Use the supplied `construction_status` as the authoritative construction condition.

- `MISSED` → construction deadline was missed.
- `PENDING` → construction is not yet due.
- `RIG_ON_OCCURRED` → Rig-On has occurred; do not call the construction gate missed.
- A NULL `rig_on_date` only means the actual date is not recorded unless the
  supplied evidence states otherwise.

## OUTPUT

Use this format:

**Well [well_id] — Delay Summary**

### Why is the well delayed?

Give a short and clear explanation of the main recorded delay conditions.

For each important condition, explain:
- what is delayed, missed, overdue, or completed late;
- the expected date and actual date when available;
- the supplied delay/variance days when available;
- whether the condition is still open or already completed.

Clearly distinguish between:

- **Well-level delay** — such as a delayed Rig-On, Rig-Off, missed milestone,
  or overdue hook-up.
- **Task-level delay** — such as an activity that finished late or is currently
  overdue.

A delayed task is evidence of task slippage, but it does not automatically prove
that the task caused the entire well delay.

Do not call something a root cause unless the supplied evidence explicitly proves it.

### Suggested Action

Give **1–3 short and practical actions** based only on currently open delays or
confirmed data-quality issues.

Examples:
- verify or update a missing actual date;
- review an overdue open activity;
- validate a completed-late activity;
- review a confirmed data-quality issue.

Do not recommend adding manpower, equipment, materials, approvals, or accelerating
the work unless the supplied JSON explicitly provides evidence supporting that action.

Do not recommend recovery action for a milestone or task that is already completed.

### Evidence Limitation

End with one short sentence when the supplied evidence does not establish a deeper
root cause.

Example:
"The supplied evidence shows schedule slippage but does not establish the underlying root cause."

## Additional Rules

- Use only the supplied JSON and BUSINESS RULES.
- Use the exact business terminology from the BUSINESS RULES.
- Do not invent missing information.
- Do not treat schedule variance as proof of causation.
- Do not infer manpower, equipment, material, approval, or productivity problems
  from missing data.
- Do not infer that one activity delayed another unless the supplied evidence
  explicitly supports that relationship.
- `STATUS NOT AVAILABLE` means there is insufficient recorded information; it is
  not by itself proof of delay.
- If no task records are supplied, say:
  **"No tasks are mentioned for this well in the supplied investigation data."**
  Then continue analysing all available well-level and milestone information.
- Keep the response concise, natural, and easy for a project engineer to understand.
- Focus only on **why the well is delayed and what should be checked or done next**.
- Do not produce tables or raw JSON.
"""