# DAILY REPORT RULES — AL TASNIM DAILY MORNING BRIEF

Authoritative rules for classifying, grouping and presenting one day's `well.task_daily`
entries. Follow it exactly. Do not infer, modify, or invent a definition. If a question
needs a rule that is not stated below, say the rule is **not yet defined** — do not assume
one.

**This file is the daily-report-specific sibling of `business_rules.md`.** General
organisational rules that apply beyond a single day's report — PDO/Al Tasnim scope and
responsibility, well lifecycle dates, milestone deadlines, schedule variance, PMS weightage
— live in `business_rules.md` instead. Nothing here overrides or repeats those; a live well,
for instance, is still defined by `business_rules.md`'s well-completion rule (its §7), not
redefined here. This file covers only what is specific to classifying and displaying one
day's task entries: actual vs. planned, UOM, progress, mapping, and data quality.

## 1. Column dictionary

Use these exact names; never a synonym.

| Concept | Definition |
|---|---|
| Daily task source | `well.task_daily`, filtered to one `ActionOn` date |
| Daily actual quantity | `TRY_CONVERT(DECIMAL(18,4), JSON_VALUE(daily_data, '$.actual_quantity'))`, guarded by `ISJSON` |
| Planned quantity | `task_daily.planned` |
| Progress | `task_daily.progress`, reported exactly as stored |
| Activity id | `LEFT(task_code, NULLIF(CHARINDEX('-', task_code), 0) - 1)` |
| Activity code | `dbo.mapping_master.New_Activity_Code`, joined on `CAST(mapping_master.Activity_ID AS nvarchar(50)) = activity_id` |
| WBS | `activity_master_csv.activity_group_description` — only this |
| Crew | `activity_master_csv.crew_code` — only this |
| UOM | `ref.uom.uom_code`, joined on `task_daily.uom_id` |

`status_id`, `progress` and `flowline_const_status_id` are **not** used to decide whether a
well is live — that is `business_rules.md`'s rule (§7), not this file's. Task rows with
`well_id <= 1`, or with a non-numeric `well_id`, are excluded. `task_daily.data_qty` is
**never** read as the actual quantity, and `task_daily.required` is **not read at all** (§7,
below).

`daily_completed` and `ph_name` are read from the `daily_data` JSON (`$.completed`,
`$.ph_name`), falling back to the `daily_completed` / `daily_ph_name` columns only because
those columns are `NULL` throughout the table while the JSON carries the real values — the
same JSON the actual quantity comes from.

**Schema drift — `task_daily.well_id` is `varchar`, not `int`.** `well.well_master.well_id`
is still `int`; `task_daily.well_id` was migrated to `varchar` and a minority of rows hold
non-numeric junk (`'0000F'`, `'0000I'`, `'0000J'`, blank). A bare comparison or JOIN against
the int `well_master.well_id` throws `SQLSTATE 22018` and takes the whole report down with
it. Every use of `task_daily.well_id` in this codebase goes through `TRY_CONVERT(int,
td.well_id)`, which returns `NULL` for junk instead of raising; the `INNER JOIN` to live
wells then excludes it the same way it already excludes `well_id <= 1`. Enforced by a test
(`test_well_id_is_never_compared_or_joined_without_try_convert`) so this cannot regress.

## 2. Task code → activity → WBS → crew

`well.task_daily.task_code` encodes the activity. Resolve it through TWO lookups, in this
order. Never guess a WBS, and never use the activity id as one.

```
task_code                       e.g. 'FLME1180-30356'
└ text before the FIRST '-'  = activity_id           'FLME1180'
    → dbo.mapping_master.Activity_ID   (CAST to nvarchar — stored as TEXT)
       → .New_Activity_Code                           'FL-ME-ML08-03'
          → dbo.activity_master_csv.activity_code
             → .activity_group_description = WBS      'Straightline Welding incl. supports'
             → .crew_code                  = crew     'MWS0602'
```

- **`dbo.mapping_master` is the current source, not `dbo.activity_master_mapping`.** The old
  table is superseded and resolves only a minority of activity_ids seen in `task_daily`
  (measured ~30% overall, and 0% for some wells entirely). `dbo.mapping_master.New_Activity_Code`
  is the column that plays `activity_master_mapping.activity_code`'s former role, feeding
  `activity_master_csv` below. `mapping_master.Activity_ID` is stored as `TEXT`; `CAST` it to
  `nvarchar` before comparing.
- `mapping_master` has no equivalent of the old table's `project_type`, `composition_code` or
  `class_b_ptw` columns. Report those as not recorded — do not backfill them from the old,
  superseded table.
- The text before the FIRST '-' is ALWAYS `activity_id`; a task_code may hold more dashes
  (`FLME1180-34516-T02` is still `FLME1180`). Extract it NULL-safely:
  `LEFT(task_code, NULLIF(CHARINDEX('-', task_code), 0) - 1)`
- `task_code` is an INTERNAL key. Use it ONLY to derive `activity_id`; NEVER display it when
  the question asks about a well's ACTIVITIES — identify an activity by `activity_code`
  (from `mapping_master.New_Activity_Code`), and list them DISTINCT.
- WBS is ONLY `activity_master_csv.activity_group_description`. Crew is ONLY `.crew_code`.
- LEFT JOIN both hops whenever unmapped work must stay visible (the WBS shapes below) — an
  inner JOIN drops it silently and makes the unmapped tally read 0. The ACTIVITY LIST is the
  exception: it uses an inner JOIN, because an activity with no mapping row is not a listable
  activity.
- A repeating `activity_id` is CORRECT — one well runs the same activity many times. Never
  de-duplicate it away; choose the GRAIN the question asks for instead:

```sql
-- per ACTIVITY  ("what activities does this well have")  -> one row per activity, NO task_code
--   INNER JOIN here on purpose: an activity with no mapping row is NOT listed.
SELECT DISTINCT a.activity_id, mm.New_Activity_Code AS activity_code
FROM a JOIN dbo.mapping_master mm ON CAST(mm.Activity_ID AS nvarchar(50)) = a.activity_id

-- per TASK  (ONLY when the question asks for tasks)  -> one row per task_code
SELECT a.task_code, a.activity_id, mm.New_Activity_Code AS activity_code,
       amc.activity_group_description AS wbs, amc.crew_code

-- WBS BREAKDOWN  ("which WBS", "tasks per WBS")  -> one row per WBS
--   ISNULL is correct here: unmapped tasks are a real row of the breakdown.
SELECT ISNULL(amc.activity_group_description, '(unmapped)') AS wbs,
       COUNT(DISTINCT a.task_code) AS tasks
GROUP BY amc.activity_group_description

-- WBS COUNT  ("how many WBS")  -> the number, with the unmapped tally beside it
SELECT COUNT(DISTINCT amc.activity_group_description) AS wbs_count,
       COUNT(DISTINCT CASE WHEN amc.activity_group_description IS NULL
                           THEN a.task_code END)      AS unmapped_tasks
```

⚠ NEVER `COUNT(DISTINCT ISNULL(activity_group_description, '(unmapped)'))` — "(unmapped)" is
not a WBS but a task whose WBS is unknown, so it adds a phantom +1. One real well has 21 WBS
and 2 unmapped tasks; that expression reports 22. Give both figures: "21 WBS; 2 tasks not
mapped to one." Never count the per-TASK rows for a per-WBS question either — that same well
returns 90 task rows.

**Both lookup tables are de-duplicated to one row per key** inside the query. Without that,
the handful of `mapping_master` rows sharing an `activity_id` would fan out the daily rows
and inflate every total on the dashboard.

**`activity_uom` — connected as reference evidence, never as a substitute.**
`dbo.mapping_master` also carries a `UOM` column: the unit the activity master expects, as
opposed to `uom_code` (§5 below — the unit actually recorded on this daily row). Measured
against actual-entry rows table-wide, `uom_code` is missing on 26 of 11,277; all 26 have a
`mapping_master.UOM` value available. That value is surfaced as `activity_uom` — in the API,
the well/task detail views, and the Excel export — precisely because it fills a real
evidence gap. It is **never** used to fill in, group by, or convert a quantity: `uom_code`
stays the sole UOM for those purposes (§5), and `MISSING_UOM` (§6) still fires exactly as
before when `uom_code` is absent, regardless of whether `activity_uom` is available. The two
are also never compared for a "mismatch" flag: `mapping_master.UOM` values like `'No'` vs.
`ref.uom.uom_code` values like `'Nos'` look like naming-convention variants of the same
abbreviation rather than a real discrepancy, and no rule exists to tell the two apart — so
both values are shown side by side and left for a person to judge, rather than the system
guessing.

## 3. Daily row-grain resolution

`well.task_daily` holds several rows that share `(well_id, schedule_id, task_code,
ActionOn)`. They are different planning snapshots plus, usually, one actual-entry row.
Getting this wrong is the fastest way to a wrong number, so the strategy is explicit,
isolated in `sql/daily_tasks.sql`, and covered by tests.

**What the data actually looks like** (measured across the whole table, not assumed):

* 2,729 groups have more than one row;
* **zero** groups have more than one actual-entry row;
* multi-row groups differ in their `planned` value — they are planning snapshots.

**The strategy.** Partition by `(well_id, schedule_id, task_code, ActionOn)` and rank:

1. `is_actual_entry DESC` — an actual-entry row outranks a planning snapshot;
2. `updated_at DESC` — then the most recently updated row;
3. `id DESC` — final tie-break.

Keep rank 1. Carry `group_row_count` and `group_actual_entry_count` forward so the condition
stays visible rather than being silently collapsed:

* more than one row → `MULTIPLE_TASK_ROWS`;
* more than one actual entry → `DUPLICATE_ACTUAL_ENTRY`.

`DISTINCT` would merge genuinely different snapshots. `MAX(id)` alone could pick a planning
snapshot over the actual entry and lose a reported quantity. Summing every row would double
count. Ranking avoids all three.

State the arithmetic openly wherever a reduced count is shown — e.g. *"3 duplicate task rows
set aside by grain resolution (197 raw rows → 194 logical tasks)"* — so the reduction is
auditable, never a silent shrink.

`DUPLICATE_ACTUAL_ENTRY` currently never fires on this data. The handling exists anyway,
because the grain is a property of the data, not a guarantee.

## 4. Quantity status

The single classification of a daily entry's reported quantity against its planned
quantity. Classify once; never recompute or override it downstream (React and the LLM both
repeat it verbatim).

| Condition | Status |
|---|---|
| `actual = planned` | `ON_PLAN` |
| `actual > planned` | `ABOVE_PLAN` |
| `actual < planned` | `BELOW_PLAN` |
| `actual IS NULL` | `NO_ACTUAL` |
| `actual` present, `planned IS NULL` | `NOT_VALIDATED` |

**`ABOVE_PLAN` is not an error.** It states that the reported actual is above the planned
quantity, nothing more. `planned = 0` with `actual > 0` is likewise `ABOVE_PLAN` and not an
error. **No tolerance band exists** — a difference of `0.0001` is `BELOW_PLAN`, not "close
enough." No percentage variance is computed when planned is zero or missing.

**`NOT_VALIDATED` is deliberate, not a gap.** A row can carry an actual quantity with no
planned quantity to compare it against. Treating the missing planned as zero would invent a
rule and would report the task as a false `ABOVE_PLAN`; instead the condition is exposed as
unresolved (`NOT_VALIDATED`) and flagged `MISSING_PLANNED` (§6). `NO_ACTUAL` still wins over
`NOT_VALIDATED` when there is no reported actual at all — that judgement needs no
comparison.

These five values are also this report's top-level grouping in definition order — `ON_PLAN
→ ABOVE_PLAN → BELOW_PLAN → NO_ACTUAL → NOT_VALIDATED` — fixed regardless of the data, so
the same status is always in the same place from one day's report to the next.

## 5. UOM

`ref.uom.uom_code` is displayed as stored. **No conversion between units is defined**: Km ↔
M, Joint ↔ Joints and well ↔ Nos are all distinct units. Consequently:

* quantities are summed **only within a single UOM** — never across units, never converted
  to make a total fit;
* a group (however it is formed) reports a planned/actual total only when every task in it
  shares one unit; when it spans several, the total is withheld — **not reported as
  zero** — and the units involved are named instead;
* day-level totals report task and well counts but deliberately carry **no** quantity, for
  the same reason;
* an explanation scope that spans several UOM has its totals withheld the same way, with the
  reason stated in the evidence sent to the model.

`uom_code` is a `varchar` column holding `m²` and `m³` as single-byte characters; the
connection sets `DB_ANSI_CODEPAGE` (default `cp1252`) so those arrive intact.

`activity_uom` is reference evidence only — see §2. It is never used to group, convert, or
fill in a missing `uom_code`.

## 6. Mapping and data quality

`mapping_status` reports the first break in the §2 chain, and only the first — a task with
no `activity_code` is `UNMAPPED_ACTIVITY`, not four separate failures:

`MAPPED` · `UNMAPPED_ACTIVITY` · `UNMAPPED_WBS` · `UNMAPPED_DESCRIPTION` · `UNMAPPED_CREW`

Missing information stays missing at every stage — never a substituted value.

Data-quality conditions are tracked **separately from the operational numbers** and never
fold into a quantity or a status:

`UNMAPPED_ACTIVITY` · `UNMAPPED_WBS` · `UNMAPPED_DESCRIPTION` · `UNMAPPED_CREW` ·
`MISSING_UOM` · `INVALID_DAILY_JSON` · `UNPARSEABLE_ACTUAL_QUANTITY` ·
`DUPLICATE_ACTUAL_ENTRY` · `MULTIPLE_TASK_ROWS` · `MISSING_PLANNED` · `MALFORMED_TASK_CODE`

## 7. Not yet defined

Answer what you can and state plainly that the rule is undefined — never invent one:

* **Quantity tolerance.** None applied; any difference is classified exactly (§4).
* **Whether a quantity difference is an error.** It is not — `ABOVE_PLAN`/`BELOW_PLAN` are
  descriptive facts, never error states (§4).
* **UOM conversion.** None defined; units are never converted or summed across (§5).
* **Meaning of `task_daily.required`.** The column is not read anywhere in this version.
* **Unit of `task_daily.progress`.** Reported exactly as stored, never as a percentage.
  Observed values range from −0.05 to 66.7, so a 0–1 fraction cannot be assumed. Never
  describe it as a completion percentage.
* **Cause of a quantity difference.** Not recorded anywhere in this evidence. Never inferred.
* **Accountability / crew performance.** Not recorded. Never assigned from a quantity status
  or a data-quality flag.

(A well's or a construction phase's *actual completion date* is a well-lifecycle question,
not a daily-report one — see `business_rules.md` for that.)

## 8. Strict instructions

* These rules are authoritative for every question about a daily task's quantity status,
  UOM, activity/WBS/crew mapping, or data quality.
* Do not infer, modify, or invent a rule.
* If the database holds a value that conflicts with a rule here, **report the database
  value** and explain the rule's interpretation separately. Never silently change a database
  result.
