"""
Task prompt for well delay analysis.

The BUSINESS RULES and SLIPPAGE RULES documents are loaded separately and are
authoritative. This prompt defines only the task and output format — it does
not restate rules that already live in those documents.
"""

DELAY_ANALYSIS_PROMPT = """\
# TASK — WELL DELAY ANALYSIS

Explain clearly **why the selected well is delayed**, using only the supplied JSON
evidence, interpreted strictly through the business rules and slippage rules already
provided above. Never guess or invent a cause, dependency, resource shortage, penalty,
or recovery plan that isn't directly supported by that evidence.

## Input
The JSON may contain: `well` (well-level dates/progress), `milestones` (pegging, FLAF,
construction, hook-up — status/deadline/actual/variance), `delayed_activities`
(task-level target vs. actual dates, progress, resources), and `data_quality`
(recorded data-quality issues).

Use well-level evidence first; use task/activity evidence to support it, not replace it.

## Output format

**Well [well_id] — Delay Summary**

### Why is the well delayed?
A short, clear explanation of the recorded delay conditions: what is delayed, missed,
overdue, or completed late; expected vs. actual dates and variance days when available;
whether each condition is still open or resolved.

Clearly separate **well-level delay** (Rig-On, Rig-Off, Pegging, FLAF, Construction,
Hook-up) from **task-level delay** (an activity finishing late or running overdue). A
delayed task is evidence of task slippage — it does not by itself prove that task caused
the well delay.

For every delayed/overdue task named in `delayed_activities`, identify it by its activity
name/code and, when present in the JSON, name the associated crew (e.g. `master_crew_code`,
`planned_crew`, or crew/employee id). If a task has no crew recorded, say the crew is not
recorded — do not guess one.

### Suggested Action
1–3 short, practical actions tied to the specific open task(s) and crew(s) identified above,
or to confirmed data-quality issues (e.g. verify a missing actual date, review the overdue
activity with its responsible crew, validate a completed-late activity). Never recommend
adding manpower, equipment, materials, approvals, or accelerating work unless the JSON
explicitly supports it, and never suggest recovery action for something already completed.

### Evidence Limitation
One short closing line whenever the evidence doesn't establish a deeper root cause, e.g.:
"The supplied evidence shows schedule slippage but does not establish the underlying root cause."

## Rules
- Follow the business rules and slippage rules exactly; use their exact terminology.
- Treat `null` as *not recorded* — never as zero, on time, delayed, or unavailable.
- Use supplied status/deadline/variance values as given; never recompute or override them.
- A future deadline with a missing actual date is *not yet due* — never call it missed.
- Never call something a root cause, or infer a crew/material/equipment/approval/
  productivity problem, unless the evidence explicitly supports it.
- If no tasks are supplied, say so plainly, then continue analysing well-level and
  milestone evidence.
- Keep the response concise and natural for a project engineer — no tables, no raw JSON.
"""
