AL-TASNIM WELL SLIPPAGE

Purpose
This document defines how well slippage is determined and how the investigation data maps from:
Well → Project → WBS/Activity → Task → Crew
The purpose of the slippage logic is to identify wells that are currently behind schedule and provide deterministic evidence for answering:
Why is this well delayed?
The SQL investigation layer should calculate schedule conditions. The LLM should explain those recorded conditions and must not invent causes.

Well-Level Slippage
A well is investigated only when:
eng_completion_date IS NULL
A completed well is excluded from the active slippage investigation.
The well-level schedule is primarily evaluated using:
Expected Rig-On
Actual Rig-On
Expected Rig-Off
Actual Rig-Off
Pegging
FLAF
Construction gate
Hook-up

Rig-On Slippage
Expected Rig-On
Source:
well.well_master.ex_rig_on_date
Actual Rig-On
Source:
well.well_master.rig_on_date
Slippage rule
Rig-On is considered delayed when:
actual Rig-On > expected Rig-On
or:
actual Rig-On IS NULL
AND
expected Rig-On < today
Interpretation:
Actual > Expected
↓
Rig-On delayed
Actual is NULL
Expected date has passed
↓
Rig-On overdue
A missing actual date by itself does not prove delay when the expected date is still in the future.

Rig-Off Slippage
Expected Rig-Off
Source:
well.well_master.ex_rig_off_date
Actual Rig-Off
Source:
well.well_master.rig_off_date
Slippage rule
Rig-Off is considered delayed when:
actual Rig-Off > expected Rig-Off
or:
actual Rig-Off IS NULL
AND
expected Rig-Off < today
ex_rig_off_date is a planning/master date.
rig_off_date is the actual date.
They must not be confused.

Pegging Slippage
Source
Actual pegging date:
well.well_master.pegged_date
Deadline
Pegging deadline is:
expected Rig-On - 60 days
SQL calculation:
DATEADD(day, -60, ex_rig_on_date)
Status
pegged_date < deadline
→ AHEAD_OF_SCHEDULE
pegged_date = deadline
→ ON_SCHEDULE
pegged_date > deadline
→ DELAYED
pegged_date IS NULL
AND today > deadline
→ MISSED
pegged_date IS NULL
AND today <= deadline
→ PENDING
Variance
For a completed pegging:
pegging variance = pegged_date - pegging_deadline
Positive value:
late
Negative value:
ahead of schedule

FLAF Slippage
Source
Actual FLAF issue date:
well.well_master.flaf_issue_date
Deadline
FLAF deadline is:
expected Rig-On - 90 days
SQL calculation:
DATEADD(day, -90, ex_rig_on_date)
Status
flaf_issue_date < deadline
→ AHEAD_OF_SCHEDULE
flaf_issue_date = deadline
→ ON_SCHEDULE
flaf_issue_date > deadline
→ DELAYED
flaf_issue_date IS NULL
AND today > deadline
→ MISSED
flaf_issue_date IS NULL
AND today <= deadline
→ PENDING
Variance
flaf variance = flaf_issue_date - flaf_deadline
Positive:
late
Negative:
ahead of schedule

Construction Slippage
Construction is treated as a Rig-On gate.
It is not an independent construction-completion calculation.
Construction deadline
expected Rig-On - 1 day
SQL calculation:
DATEADD(day, -1, ex_rig_on_date)
Construction status
When:
today > construction deadline
AND
rig_on_date IS NULL
then:
MISSED
When:
rig_on_date IS NULL
AND
today <= construction deadline
then:
PENDING
When Rig-On has occurred:
RIG_ON_OCCURRED
Construction lag
When the construction gate is missed:
construction lag =
today - construction deadline
Important:
RIG_ON_OCCURRED means the construction gate has been passed by occurrence of Rig-On. It does not prove that every construction activity was completed on time.

Hook-Up Slippage
A hook-up deadline depends on Rig-Off.
When actual Rig-Off exists
hook-up deadline =
actual Rig-Off + 2 days
When actual Rig-Off does not exist
hook-up deadline =
expected Rig-Off + 2 days
The actual Rig-Off date takes precedence.
Hook-up status
When well completion exists:
eng_completion_date IS NOT NULL
→ COMPLETED
When actual Rig-Off exists and:
today > actual Rig-Off + 2 days
then:
HOOKUP_DEADLINE_PASSED
When actual Rig-Off does not exist and expected Rig-Off exists and:
today > expected Rig-Off + 2 days
then:
HOOKUP_DEADLINE_FORECAST_PASSED
Otherwise:
NOT_YET_DUE

Task-Level Slippage
Task data comes from:
well.task_daily
task_code must come from:
well.task_daily.task_code
Only the current logical task record should be used for an investigation.
The current row is selected by ranking task history using:
ActionOn DESC
updated_at DESC
id DESC
for each:
well_id + task_code

Task Start Slippage
Task target start:
task_daily.target_start
Actual start:
task_daily.actual_start
If the actual start is earlier than the target:
STARTED_AHEAD_OF_SCHEDULE
If equal:
STARTED_ON_SCHEDULE
If later:
START_DELAYED
If actual start is missing and the target date has passed:
NOT_STARTED_START_SLIPPING
If actual start is missing but the target date has not passed:
NOT_STARTED_ON_SCHEDULE
Start variance
When actual start exists:
start variance =
actual_start - target_start
When actual start is missing and target has already passed:
start variance =
today - target_start
Positive values represent slippage.

Task End Slippage
Task target end:
task_daily.target_end
Actual end:
task_daily.actual_end
Completed late
actual_end > target_end
→ COMPLETED_LATE
Completed on time
actual_end = target_end
→ COMPLETED_ON_SCHEDULE
Completed early
actual_end < target_end
→ COMPLETED_EARLY_ACCELERATED
Open and overdue
actual_end IS NULL
AND today > target_end
→ OVERDUE_CURRENT_TASK_LAGGING
Open but not late
actual_end IS NULL
AND today < target_end
→ IN_PROGRESS_NOT_LATE
Due today
actual_end IS NULL
AND today = target_end
→ DUE_TODAY
End variance
When actual end exists:
end variance =
actual_end - target_end
When actual end is missing and target has passed:
end variance =
today - target_end
Positive values represent slippage.

Task Execution Status
Execution status is derived from actual dates.
actual_end IS NOT NULL
→ COMPLETED
actual_start IS NULL
AND target_start exists
AND today < target_start
→ NOT_STARTED
actual_start IS NULL
AND target_start exists
AND today >= target_start
→ NOT_STARTED_LATE
actual_start IS NOT NULL
AND actual_end IS NULL
→ IN_PROGRESS

Task Schedule Risk
A task is:
RED_DELAYED
when:
actual_end IS NULL
AND today > target_end
or:
actual_end > target_end
A task is:
AMBER_START_SLIPPING
when:
actual_start IS NULL
AND today > target_start
A task is:
AMBER_START_DELAYED
when:
actual_start > target_start
Otherwise:
GREEN_OR_ON_SCHEDULE

Well Slippage vs Task Slippage
These are different concepts.
Well-level slippage
Examples:
Rig-On delayed
Rig-Off delayed
Pegging missed/delayed
FLAF missed/delayed
Construction gate missed
Hook-up deadline passed
Task-level slippage
Examples:
Task finished late
Task is currently overdue
Task has a delayed start
A delayed task is evidence that the task is slipping.
It does not automatically prove that the task caused the entire well delay.

Activity Mapping
The activity ID is obtained from the task code.
Example:
LCPC1040-37857
↓
LCPC1040
The activity ID is the portion of task_code before the first -.
Source:
well.task_daily.task_code
Then:
activity_id
↓
dbo.mapping_master.Activity_ID
From mapping_master, the relevant activity information is:
New_Activity_Code
New_Crew_code
These become:
activity_code
master_crew_code
The old:
dbo.activity_master_mapping
table is not used.

Activity / WBS Description
For the investigation JSON, the activity/WBS descriptive value is:
activity_group_description
Source:
dbo.activity_master_csv.activity_group_description
It is associated using:
activity_code
Therefore the investigation can represent the work as:
Activity ID
Activity Code
Activity Group Description
Master Crew
No separate WBS hierarchy is required in the investigation JSON.

Crew Mapping
There are two different crew concepts.
Master Activity Crew
Source:
dbo.mapping_master.New_Crew_code
Mapped using:
activity_id
Output:
master_crew_code
This represents the master crew associated with the activity.
Task-Level Crew
Source:
well.task_daily
Fields:
planned_crew
crew_type_id
crew_id
emp_id
These represent the actual task/resource information recorded against the task.
They should not be merged into one field.

Complete Well → Project → WBS/Activity → Task → Crew Map
The current investigation relationship is:
WELL
│
│ well_id
↓
well.well_master
│
├── project_id
│
├── ex_rig_on_date
│
├── rig_on_date
│
├── ex_rig_off_date
│
├── rig_off_date
│
├── pegged_date
│
└── flaf_issue_date
│
↓
well.task_daily
│
├── task_code
├── target_start
├── target_end
├── actual_start
├── actual_end
├── progress
├── completed
├── planned_crew
├── crew_type_id
├── crew_id
└── emp_id
│
↓
Activity ID
(text before '-')
│
↓
dbo.mapping_master
│
├── Activity_ID
├── New_Activity_Code
└── New_Crew_code
│
├── activity_code
└── master_crew_code
│
↓
dbo.activity_master_csv
│
└── activity_group_description

Project Mapping
The project associated with the well comes from:
well.well_master.project_id
The current investigation SQL can also use:
project.project_mstr.project_id
to identify the project master record.
The well's project and the task's recorded project_id are separate source values and should not be silently treated as identical.

Evidence Used to Explain Delay
For the LLM, the strongest evidence should be considered in this order:
Level 1 — Well-level
Rig-On
Rig-Off
Pegging
FLAF
Construction
Hook-up
Level 2 — Activity/task
Activity
Task
Target date
Actual date
Variance
Progress
Execution status
Schedule risk
Level 3 — Supporting evidence
Crew
Quantity
Productivity
Supporting evidence must not automatically be interpreted as causation.

Example
For a well with:
FLAF status = DELAYED
FLAF variance = 30 days
and:
Activity = Pad Construction
Task = LCPC1040-37857
Target End = 26-Aug-2026
Actual End = NULL
End Status = OVERDUE_CURRENT_TASK_LAGGING
End Variance = 17 days
Progress = 30%
Execution Status = IN_PROGRESS
Schedule Risk = RED_DELAYED
the deterministic evidence says:

FLAF is delayed by 30 days.

Pad Construction task is overdue by 17 days.

The task is still in progress at 30%.
The evidence does not, by itself, establish:
crew shortage
material shortage
equipment shortage
approval delay
productivity problem
dependency problem
unless those causes are explicitly supported by additional evidence.

Rules for the AI
The AI must:
Use the supplied SQL status and variance values.
Use well-level delay evidence first.
Use activity/task data as supporting evidence.
Distinguish well-level delay from task-level slippage.
Never claim a delayed task caused the well delay unless causation is explicitly supported.
Never infer crew shortage from missing crew data.
Never infer material/equipment/approval problems from missing values.
Treat NULL as not recorded, not automatically delayed.
Treat future deadlines as not yet due.
Use actual Rig-On/Rig-Off dates when available.
Treat ex_rig_on_date and ex_rig_off_date as expected/master dates.
Avoid treating HOOKUP_DEADLINE_PASSED or task delay as proof of a deeper root cause.
The investigation SQL is the deterministic calculation layer. The LLM is the explanation layer.