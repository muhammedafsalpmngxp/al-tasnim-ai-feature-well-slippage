# AL-TASNIM WELL SLIPPAGE

## Purpose
This document explains how well slippage is identified and how the AI should reason about delays for a well. The underlying SQL calculates schedule status and variance as hard facts. The AI's job is to explain those facts in plain language — never to invent a cause that isn't backed by evidence.

## When a Well Is Reviewed
A well is only investigated while it has **not yet reached engineering completion**. Once a well is fully completed, it drops out of active slippage tracking.

## Key Schedule Milestones (Well Level)
Every well moves through a sequence of milestones. Each one is compared against its expected date to see if it's on track, delayed, or overdue:

- **Rig-On** — the rig arriving on site. Delayed if it arrived later than expected, or hasn't arrived yet and the expected date has already passed.
- **Rig-Off** — the rig leaving site. Same logic as Rig-On: late actual date, or no actual date past its expected date, means delayed.
- **Pegging** — site survey/marking, due 60 days before expected Rig-On. Can be ahead of schedule, on schedule, delayed, missed (deadline passed with nothing recorded), or pending (deadline still ahead).
- **FLAF** (For-Land-Access/Foundation approval) — due 90 days before expected Rig-On. Same five statuses as Pegging.
- **Construction Gate** — a checkpoint that must clear 1 day before expected Rig-On. It's considered cleared once Rig-On actually happens; otherwise it's pending or missed depending on whether the deadline has passed. Note: clearing this gate only means Rig-On occurred — it doesn't guarantee every construction task underneath was finished on time.
- **Hook-Up** — connecting the well after Rig-Off, due 2 days after Rig-Off (actual Rig-Off date if known, otherwise expected). Statuses: completed, deadline passed, forecast deadline passed, or not yet due.

**Important nuance:** a missing actual date is not proof of delay by itself — it only becomes a problem once its expected/deadline date has already passed. A future deadline is simply "not due yet."

## Task-Level Slippage
Underneath the well, individual **tasks** (units of work, e.g. a construction activity) each have their own target start/end dates and actual start/end dates. Only the most recent record for a task is used.

- **Start**: compared actual vs. target start → ahead of schedule, on schedule, delayed, not started but still on time, or not started and slipping (target date passed with no start).
- **End**: compared actual vs. target end → completed late, on time, or early; if still open, either overdue, in progress and not yet late, or due today.
- **Execution status**: simply whether the task is not started, in progress, or completed, based on which actual dates exist.
- **Schedule risk flag**: a simple traffic-light summary — red (delayed), amber (start slipping or already late starting), or green (on schedule).

A delayed task is evidence that *that task* is slipping — it does not by itself prove the delayed task is *why the whole well* is behind.

## How Work Is Organized
For context when explaining a delay, the data follows this chain:

**Well → Project → Activity/Task → Crew**

- A well belongs to a project.
- A well's tasks each belong to an activity (identified from the task's code), which has a human-readable description and an assigned master crew.
- Separately, each task also records its own actual crew/resource details (who actually worked it), which is distinct from the activity's assigned master crew — these two crew concepts should not be merged or confused.
- The well's project and a task's own recorded project reference are related but not guaranteed to be identical, so they shouldn't be assumed interchangeable.

## Evidence Priority for Explaining a Delay
When explaining why a well is delayed, weigh evidence in this order:

1. **Well-level milestones** (Rig-On, Rig-Off, Pegging, FLAF, Construction, Hook-Up) — the strongest, most direct evidence.
2. **Activity/task detail** (which activity, which task, target vs. actual, variance, progress, status, risk flag) — supporting evidence that adds specificity.
3. **Crew, quantity, and productivity data** — contextual detail only; never treat this as proof of causation on its own.

### Example
If FLAF is delayed by 30 days, and the Pad Construction task is overdue by 17 days and only 30% complete, the AI can say:
- FLAF is delayed by 30 days.
- The Pad Construction task is overdue by 17 days and still in progress.

But it must **not** conclude from this alone that there's a crew shortage, material shortage, equipment issue, approval delay, or productivity problem — those causes require their own explicit supporting evidence.

## Rules for the AI
- Use the supplied status and variance values as given — don't recompute or guess them.
- Lead with well-level delay evidence; use task-level data to support, not replace it.
- Keep well-level delay and task-level slippage conceptually separate.
- Never claim a delayed task caused the overall well delay unless that link is explicitly supported by evidence.
- Never infer a crew, material, equipment, or approval problem just because that data is missing — missing means "not recorded," not "delayed."
- Treat deadlines that haven't arrived yet as "not due," not as a problem.
- Prefer actual dates over expected/master dates whenever an actual date is available.
- Don't treat "gate cleared" or "task delayed" statuses as proof of a deeper root cause on their own.
