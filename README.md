# Al Tasnim — Daily Morning Brief & Daily Entry Validation

An operational dashboard over the Al Tasnim well-construction database. It shows what
live wells did on a given day, validates each daily entry's reported quantity against
its planned quantity, and lets an operator drill from a single summary figure all the
way down to the individual database records behind it.

```
Daily Summary (one row per well) → Well → Daily Tasks → AI Explanation
```

The dashboard's front page is a flat list, one row per live well, sorted busiest first:
well ID, its main activity (plus how many others), task count, and its non-zero status
counts (`On Plan`, `Above Plan`, `Below Plan`, `No Actual`, `Not Validated`). An earlier
version organised the day by validation status, then work category, then activity, before
ever reaching a well; that hierarchy was accurate but took several clicks to answer the
question the brief exists to answer first: *what did each well do, and how did it come
out?* The backend still computes and serves that grouped hierarchy (`/api/daily/summary`,
§5, §8) — nothing about the classification changed — the well-first list is a front-end
presentation choice on top of the same evidence. Clicking a row opens that well's full
detail; "AI summary" is a second, independent control on each row that expands an
explanation of that well's day in place, without navigating away.

The architecture has one rule that everything else follows:

```
                    SOURCE OF TRUTH
                         │
                         ▼
                     SQL Server
                         │
                         ▼
               SQL / Python evidence layer
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
         Dashboard              LLM input
              │                     │
              ▼                     ▼
       Deterministic UI        Explanation only
```

**SQL and Python calculate. React displays and interacts. The LLM explains.**
The LLM never queries the database, never calculates a value and never overrides a
classification.

---

## 1. Quick start

### Both together

```bash
python run.py
```

Starts FastAPI and the React dev server in one terminal, streaming both with an
`[api]` / `[ui]` prefix. Ctrl+C stops both, and if either exits on its own the other
is stopped too, so you never end up with a half-running stack.

| Flag | Effect |
|---|---|
| *(none)* | both, with backend autoreload |
| `--backend` | FastAPI only |
| `--frontend` | React only |
| `--install` | `npm install` first, then start |
| `--no-reload` | no backend autoreload — steadier for a demo |
| `--build` | build the frontend and serve the production build via Vite preview |

Host and port come from `backend/.env` (`API_HOST`, `API_PORT`) and `frontend/.env`
(`VITE_PORT`); nothing is hardcoded in the launcher. It refuses to start if a port is
already taken, and tells you which one. It also prefers the project's `.venv`
interpreter, so `python run.py` works from any shell.

The sections below are the equivalent manual steps.

### Backend

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements.txt
cp .env.example .env                                 # then fill it in
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API docs: <http://127.0.0.1:8000/docs> · Health: <http://127.0.0.1:8000/api/health>

Requires the Microsoft ODBC Driver for SQL Server (the driver name goes in `DB_DRIVER`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api` to `VITE_API_PROXY_TARGET`, so no backend URL is baked
into the React build.

### Tests

```bash
cd backend
python -m pytest
```

116 tests. The deterministic tests run offline; the tests in `tests/test_live_wells_db.py`
and `tests/test_wells_live_db.py` run against SQL Server and skip themselves when it is
unreachable.

---

## 2. Project layout

```
project-root/
├── README.md                    ← this file
├── run.py                       ← dev launcher: starts backend + frontend together
├── llm_usage_tracker.py         ← independent LLM token-expense logger (§10) -- reads only backend/.env
├── llm_usage_log.xlsx           ← its output: one row per real LLM call, a live totals row always last
├── test_llm_usage_tracker.py    ← its own tests -- run standalone: pytest test_llm_usage_tracker.py
├── backend/
│   ├── .env                     ← environment-specific values (never committed)
│   ├── .env.example
│   ├── business_rules.md        ← general/organisational rules (PDO, Al Tasnim, well lifecycle)
│   ├── daily_report_rules.md    ← daily-report-specific rules (quantity status, UOM, mapping)
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py              FastAPI app, request logging, error handling
│   │   ├── api/                 routes + shared dependencies
│   │   ├── services/            all business processing
│   │   ├── repositories/        all database access
│   │   ├── schemas/             API request/response contracts
│   │   ├── models/              internal domain objects
│   │   ├── config/              settings + read-only database access
│   │   └── utils/               SQL loader, logging
│   ├── sql/                     daily_tasks · daily_detail · daily_summary · well_milestones
│   └── tests/
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── .env.example
    └── src/
        ├── components/          DayStrip · WellList · StatusCount ·
        │                        WellDetail · MilestoneBanner (MilestonesPage) ·
        │                        ExplainPanel · common
        ├── pages/DailyMorningBrief/
        ├── services/api.js      the only place the UI calls the backend
        ├── hooks/
        └── styles/
```

---

## 3. Definitions this application uses

All of these come from one of two rules files, never invented: `backend/business_rules.md`
(general — PDO/Al Tasnim scope, well lifecycle, milestones) or `backend/daily_report_rules.md`
(specific to classifying and grouping one day's `task_daily` entries — quantity status, UOM,
progress, activity/WBS/crew mapping). The two are kept apart so a change to how a daily task
is classified never has to touch, or risk touching, a well-lifecycle rule that has nothing to
do with it, and vice versa.

| Concept | Definition used | Source |
|---|---|---|
| **Live well** | `well.well_master.eng_completion_date IS NULL` | business_rules.md §7 |
| **Completed well** | `well.well_master.eng_completion_date IS NOT NULL` | business_rules.md §7 |
| **Daily task source** | `well.task_daily`, filtered to one `ActionOn` date | daily_report_rules.md §1 |
| **Daily actual quantity** | `TRY_CONVERT(DECIMAL(18,4), JSON_VALUE(daily_data, '$.actual_quantity'))`, guarded by `ISJSON` | daily_report_rules.md §1 |
| **Planned quantity** | `task_daily.planned` | daily_report_rules.md §1 |
| **Progress** | `task_daily.progress`, reported exactly as stored | daily_report_rules.md §1 |
| **Activity id** | `LEFT(task_code, NULLIF(CHARINDEX('-', task_code), 0) - 1)` | daily_report_rules.md §2 |
| **Activity code** | `dbo.mapping_master.New_Activity_Code`, joined on `CAST(mapping_master.Activity_ID AS nvarchar(50)) = activity_id` | daily_report_rules.md §2 |
| **WBS** | `activity_master_csv.activity_group_description` — only this | daily_report_rules.md §2 |
| **Crew** | `activity_master_csv.crew_code` — only this | daily_report_rules.md §2 |
| **UOM** | `ref.uom.uom_code`, joined on `task_daily.uom_id` | daily_report_rules.md §1 |

`status_id`, `progress` and `flowline_const_status_id` are **not** used to decide whether a
well is live. Task rows with `well_id <= 1`, or with a non-numeric `well_id`, are excluded.
`task_daily.data_qty` is never read as the actual quantity, and `task_daily.required` is not
read at all (see §9).

**Schema drift, discovered while fixing a crash:** `well.task_daily.well_id` is now stored as
`varchar`, not `int` — it used to be `int` (`well.well_master.well_id` still is). A minority of
rows hold non-numeric junk in it (`'0000F'`, `'0000I'`, `'0000J'`, and blank). A bare comparison
or JOIN against the int `well_master.well_id` throws `SQLSTATE 22018` and takes the whole report
down with it. Every use of `task_daily.well_id` in this codebase goes through
`TRY_CONVERT(int, td.well_id)`, which returns `NULL` for junk instead of raising — the `INNER
JOIN` to live wells then excludes it the same way it already excludes `well_id <= 1`. This is
enforced by a test (`test_well_id_is_never_compared_or_joined_without_try_convert`) so a future
edit can't reintroduce the crash.

---

## 4. Daily row-grain resolution

`well.task_daily` holds several rows that share `(well_id, schedule_id, task_code, ActionOn)`.
They are different planning snapshots plus, usually, one actual-entry row. Getting this
wrong is the fastest way to a wrong number, so the strategy is explicit, isolated in
`sql/daily_tasks.sql`, and covered by tests.

**What the data actually looks like** (measured across the whole table, not assumed):

* 2,729 groups have more than one row;
* **zero** groups have more than one actual-entry row;
* multi-row groups differ in their `planned` value — they are planning snapshots.

**The strategy.** Partition by `(well_id, schedule_id, task_code, ActionOn)` and rank:

1. `is_actual_entry DESC` — an actual-entry row outranks a planning snapshot;
2. `updated_at DESC` — then the most recently updated row;
3. `id DESC` — final tie-break.

Keep rank 1. Carry `group_row_count` and `group_actual_entry_count` forward so the
condition stays visible rather than being silently collapsed:

* more than one row → `MULTIPLE_TASK_ROWS`;
* more than one actual entry → `DUPLICATE_ACTUAL_ENTRY`.

`DISTINCT` would merge genuinely different snapshots. `MAX(id)` alone could pick a
planning snapshot over the actual entry and lose a reported quantity. Summing every row
would double count. Ranking avoids all three.

The dashboard states the arithmetic openly — e.g. *"3 duplicate task rows set aside by
grain resolution (197 raw rows → 194 logical tasks)"* — so the reduction is auditable.

`DUPLICATE_ACTUAL_ENTRY` currently never fires on this data. The handling exists anyway,
because the grain is a property of the data and not a guarantee.

---

## 5. Quantity status

Classified once, in `app/services/validation_service.py`. React never recomputes it and
the LLM is instructed to repeat it verbatim.

| Condition | Status |
|---|---|
| `actual = planned` | `ON_PLAN` |
| `actual > planned` | `ABOVE_PLAN` |
| `actual < planned` | `BELOW_PLAN` |
| `actual IS NULL` | `NO_ACTUAL` |
| `actual` present, `planned IS NULL` | `NOT_VALIDATED` |

**These five are also the dashboard's top-level grouping** — summary → status → WBS →
activity — and the order above is the order they appear in, every day, whatever the data.
It comes from `QuantityStatus` definition order in `app/models/daily.py`; the API emits
sections in it and React does not re-sort them, so an operator always finds Below Plan in
the same place. A status with no tasks has no section; the day totals still report it as a
zero.

Every task carries a status, so — unlike the UOM hierarchy this replaced — nothing can fall
out of the grouping into a "not recorded" bucket at the top level. And because every task
under a status section shares that status, the WBS and activity levels beneath carry a task
count and no status breakdown: there is nothing left to break down.

**`ABOVE_PLAN` is not an error.** It states that the reported actual is above the planned
quantity, nothing more. `planned = 0` with `actual > 0` is likewise `ABOVE_PLAN` and not an
error. No tolerance band is applied, because none is defined — a difference of 0.0001 is
`BELOW_PLAN`, not "close enough". No percentage variance is computed when planned is zero
or missing.

`NOT_VALIDATED` is an addition, and it is deliberate. One row in the table has an actual
quantity but no planned quantity. Treating the missing planned as zero would invent a rule
and would report the task as a false `ABOVE_PLAN`; there is no planned quantity to compare
against, so the condition is exposed as unresolved and flagged `MISSING_PLANNED` instead.

---

## 6. UOM

`ref.uom.uom_code` is displayed as stored. **No conversion between units is implemented**,
because none is defined: Km ↔ M, Joint ↔ Joints and well ↔ Nos are all treated as distinct
units. Consequently:

* quantities are summed **only within a single UOM**;
* a summary group reports `planned_quantity` / `actual_quantity` only when every task in it
  shares one unit. When it spans several, both totals are `null`, `quantities_summable` is
  `false`, and `uom_codes` names the units involved — the UI shows
  *"3 units (Joint, Nos, no) — not totalled"* and the Excel export writes
  *"mixed (…)"* in its UOM column. **A withheld total is not a zero**, and both surfaces say
  so rather than leaving a blank to be misread;
* day-level totals report task and well counts but deliberately carry **no** quantity;
* when an explanation scope spans several UOM, the evidence payload withholds the totals
  and says why.

UOM was the top level of the grouping hierarchy in an earlier version, which guaranteed no
group ever spanned two units. Grouping by validation status instead (§5) means a status
section *can* span units — so the withholding rule above, which the per-well roll-up and the
evidence payload already applied, now runs at every level of the summary. Nothing is
converted to make a total fit, anywhere.

`uom_code` is a `varchar` column holding m² and m³ as single-byte characters. The
connection sets `DB_ANSI_CODEPAGE` (default `cp1252`) so those arrive intact rather than
as replacement characters.

**`activity_uom` — connected as reference evidence, never as a substitute.** `dbo.mapping_master`
also carries a `UOM` column: the unit the activity master expects, as opposed to `uom_code`
(the unit actually recorded on this daily row). Measured against actual-entry rows table-wide,
`uom_code` is missing on 26 of 11,277; all 26 have a `mapping_master.UOM` value available. That
value is surfaced as `activity_uom` — in the API, the well/task detail views, and the Excel
export — precisely because it fills a real evidence gap. It is **never** used to fill in, group
by, or convert a quantity: `uom_code` stays the sole UOM for those purposes, and `MISSING_UOM`
still fires exactly as before when `uom_code` is absent, regardless of whether `activity_uom` is
available. The two are also never compared for a "mismatch" flag: `mapping_master.UOM` values
like `'No'` vs. `ref.uom.uom_code` values like `'Nos'` look like naming-convention variants of
the same abbreviation rather than a real discrepancy, and no rule exists to tell the two apart —
so both values are shown side by side and left for a person to judge, rather than the system
guessing.

---

## 7. Mapping and data quality

The chain `task_code → activity_id → activity_code → description / WBS / crew` is resolved
with `LEFT JOIN` at every hop, so unmapped work stays visible. `mapping_status` reports the
first break in the chain: `MAPPED`, `UNMAPPED_ACTIVITY`, `UNMAPPED_WBS`,
`UNMAPPED_DESCRIPTION` or `UNMAPPED_CREW`. Missing information stays missing — the UI prints
"Not mapped", never a substitute.

Both lookup tables are de-duplicated to one row per key inside the query. Without that, the
handful of `mapping_master` rows sharing an `activity_id` would fan out the daily rows and
inflate every total on the dashboard.

**`dbo.mapping_master` replaced `dbo.activity_master_mapping`** as the first hop — the old table
is superseded and, measured against the actual data, resolves only ~30% of the activity ids seen
in `task_daily`, and on one sample date resolved **0 of 130** tasks to a WBS at all (its
`activity_code` values no longer line up with `activity_master_csv`). `mapping_master` resolves
~46% of activity ids and 93 of the same 130 tasks to a WBS. `mapping_master.Activity_ID` is
stored as `TEXT` and is `CAST` to `nvarchar` before comparing. `mapping_master` also carries its
own `New_Crew_code`, `project_type`-equivalent and similar columns that are **not** used here —
crew stays `activity_master_csv.crew_code` only, per business rule, never backfilled from the
newer table just because it happens to have a similarly-named column.

Data-quality conditions are tracked **separately from the operational numbers** and never
folded into a quantity:

`UNMAPPED_ACTIVITY` · `UNMAPPED_WBS` · `UNMAPPED_DESCRIPTION` · `UNMAPPED_CREW` ·
`MISSING_UOM` · `INVALID_DAILY_JSON` · `UNPARSEABLE_ACTUAL_QUANTITY` ·
`DUPLICATE_ACTUAL_ENTRY` · `MULTIPLE_TASK_ROWS` · `MISSING_PLANNED` · `MALFORMED_TASK_CODE`

---

## 8. API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Database reachability + LLM configuration. No secrets. |
| `GET /api/daily/summary?date=` | Dataset A — grouped Status → WBS → Activity (`status_groups`), plus `view_mode` |
| `GET /api/daily/details?date=` | Dataset B — every logical daily task |
| `GET /api/daily/group-details?date=&status=&wbs=&activity_code=&uom=&refresh=` | The rows behind one figure — called with no filter at all, also the whole day's per-well rollup behind the main dashboard's well list |
| `GET /api/daily/well/{well_id}?date=` | Every task one well ran that day |
| `GET /api/daily/dates?limit=` | Recent dates that carry daily entries |
| `GET /api/daily/export?date=` | `daily_morning_brief_YYYY-MM-DD.xlsx` |
| `POST /api/daily/explain` | Evidence + LLM explanation for a named scope |
| `GET /api/daily/milestones?window_days=` | Live wells approaching (or past) a pegging/FLAF/rig-on/rig-off deadline — see §15 |

The date defaults to the current date and is always bound as a parameter. An empty string
for `wbs` or `uom` selects the explicit "not recorded" group, so tasks missing a WBS or a
UOM stay reachable instead of disappearing from the drill-down. `uom` is no longer part of
the summary hierarchy but remains an optional filter, so a single unit stays reachable.

`POST /api/daily/explain` takes a **scope**, not figures. The client says *which* group,
status or well it wants explained; the backend re-derives the evidence itself. The client
cannot supply the numbers to be explained. Its response is served from cache when nothing
about the underlying evidence has changed since the last identical request — see §10.

`refresh=true` on `/summary` or `/group-details` bypasses the day's dataset cache **and**
purges any cached AI explanations for that date, so both endpoints must agree on the same
report date's freshness at once: reloading the well list without also invalidating a
just-explained well's cached text (or the reverse) would leave the two visibly out of step.

---

## 9. Unresolved business questions

Neither rules file defines the following. None of them have been guessed at, and each is
surfaced rather than silently resolved. All but one are `daily_report_rules.md` §7 questions
— specific to classifying a daily task, not to the well-lifecycle rules in `business_rules.md`:

| Question | How the application behaves | Source |
|---|---|---|
| **Quantity tolerance** | None applied. Any difference is classified exactly. | daily_report_rules.md §7 |
| **Is a quantity difference an error?** | No. `ABOVE_PLAN`/`BELOW_PLAN` are descriptive; nothing is called an error. | daily_report_rules.md §7 |
| **UOM conversion** | None. Units are never converted or summed across. | daily_report_rules.md §7 |
| **Meaning of `task_daily.required`** | The column is not read anywhere in this version. | daily_report_rules.md §7 |
| **Unit of `task_daily.progress`** | Reported exactly as stored, never as a percentage. Observed values range from −0.05 to 66.7, so a 0–1 fraction cannot be assumed. The LLM is explicitly forbidden from describing it as a completion percentage. | daily_report_rules.md §7 |
| **Cause of a quantity difference** | Not recorded. Never inferred, and the LLM is told so. | daily_report_rules.md §7 |
| **Accountability / crew performance** | Not recorded. Never assigned. | daily_report_rules.md §7 |
| **`planned IS NULL` with an actual** | Exposed as `NOT_VALIDATED` + `MISSING_PLANNED`. | daily_report_rules.md §4/§7 |
| **Construction actual completion date** | No column is approved as one, so none is substituted. | business_rules.md §10 |

Two further implementation notes, both consequences of what the data contains:

* **`daily_completed` and `ph_name`** are read from the `daily_data` JSON (`$.completed`,
  `$.ph_name`), falling back to the `daily_completed` / `daily_ph_name` columns. Those
  columns are NULL throughout the table, while the JSON carries the values — the JSON is
  the same source the actual quantity comes from.
* **Well count and task count are different measures.** One well can run several tasks in
  the same group on the same day, so `well_count` counts distinct wells while the status
  counts count tasks. Both are labelled as such everywhere they appear.

---

## 10. LLM boundary

The LLM may summarise the supplied evidence, describe which wells are on, above or below
plan, describe missing actual entries, and make the day easier to read.

It must not calculate totals, percentages, dates or variances; create risk scores; decide
business status; invent causes or missing data; assign blame; create business rules;
override a SQL/Python classification; reinterpret a UOM; or assume *why* an actual differs
from a plan. The system instruction states all of this, and the evidence payload carries the
undefined constraints (`quantity_tolerance`, `uom_conversion`, `progress_unit`,
`cause_of_difference`, `responsibility`) alongside the data so the model is told, in band,
what it may not infer.

**A broad scope's example tasks represent the whole scope, not whichever activity sorts
first.** Caught live against real data: a day with 46 wells produced an explanation naming
only 2-3 of them, even though its summary counts already covered all 46. The cause was the
task sample (§ below) being a plain prefix of `daily_detail.sql`'s row order — `(uom_code,
wbs, activity_code, well_id)` — which clusters on whichever activity sorts first, sometimes
just a couple of wells out of dozens in scope; the same raw order also mixed different
`quantity_status` values together with no structure, making it easy for the model's prose to
blend an `ON_PLAN` task's description into a `BELOW_PLAN` one's. `EvidenceService._representative_sample`
fixes both at once: status is the outer axis, so a handful of examples already touches every
status present before any status gets a second well, and well is the inner axis within each
status, so those examples are not all the same one or two wells. Verified against the same
real day afterward: the example tasks named three different wells, one for each of three
different statuses, in one pass. The system instruction was also strengthened to say plainly
that the summary figures cover the whole scope while the task list is only a sample, so a
multi-well scope is never described as if it were about only the wells shown as examples.
Because this changes what an old cached answer *should* say, `LLMService._PROMPT_VERSION` is
mixed into the cache key (§ below) — every answer cached under the old sampling became
unreachable the moment this shipped, with no need to clear the cache file by hand.

**Failure is contained.** If the LLM is unconfigured, unreachable, still rate-limited after
retrying, or returns an unreadable response, the endpoint returns `available: false` with a
plain reason and the evidence, and the panel reads:

> **AI explanation unavailable.** The underlying daily task data is still available and
> unchanged.

No explanation is ever fabricated, and nothing else on the dashboard depends on the LLM.

**Transient provider failures are retried, not surfaced immediately.** Measured against the
live Groq endpoint: a `429` (rate limited) and, intermittently, a `413` both occurred for a
request that succeeded moments later with the identical payload — upstream flakiness, not a
hard, repeatable limit. `LLMService._post_with_retry` retries `408`/`413`/`429`/`5xx` up to
twice more with a short backoff (honouring a provider `Retry-After` header, capped at 3
seconds) before giving up; a non-transient error (e.g. `401`) still fails on the first
attempt. This converts a momentary provider hiccup into a few extra seconds of "Generating an
explanation…" instead of a user-visible failure. A `413` that survives every retry no longer
surfaces as a raw HTTP status either: `LLMService.explain` reports it as "This selection has
too much data for the AI to summarise at once."

**Evidence size is capped per scope, not by one fixed number.** `EvidenceService` used to
include the same 40 sample tasks regardless of what was being explained; a busy day's "day"
scope (hundreds of tasks, just fewer of them shown as examples) was observed failing with a
real, repeatable `413` at that size. The per-task sample is now scope-aware
(`_TASK_EVIDENCE_LIMIT_BY_SCOPE` in `evidence_service.py`): `task` sends the one task, `well`
sends up to 30, and every broader scope (`day` and anything not narrowed to a well or task)
sends 10 — the summary counts already cover every task regardless, so a broad scope never
needed all of them listed individually. `EXPLAIN_MAX_WELLS` remains an operator-configurable
ceiling above all of these.

**The explanation renders next to what it explains, never only at the top of the page.**
Each well row in `WellList.jsx` and each task panel in `WellDetail.jsx` own their own
explain-toggle state and mount `ExplainPanel` inline, next to the well or task it describes.
Only "Explain this view" (day/well aggregate scope, in `DailyMorningBrief.jsx`) uses the
single page-level panel, because that request genuinely describes the whole view rather than
one well or task.

**No model name is shown to the operator.** The health status line says "AI explanation
available" rather than naming a model or provider: which LLM answers the request is an
operational/billing detail, not something the classification depends on, so nothing in the
panel names it either. `GET /api/health` still reports the configured model for anyone who
needs it (ops, `/docs`); the dashboard itself just doesn't surface it.

**Style: flowing prose, not bullets.** The system instruction asks for two to four short
paragraphs, the way a person would explain it out loud, and explicitly forbids markdown
formatting -- headings, bullet lists, tables, bold -- with one deliberate exception: every
literal value copied from the evidence (a well ID, task code, quantity, unit, date or status)
is wrapped in backticks. `MarkdownLite` renders that backtick span in italics, coloured with
the same `--num` teal the rest of the app already uses for a database-sourced figure
(`.explain__value`), so a value taken straight from the record visually separates from the
model's own sentence around it. Models format their answers even when asked not to, so the
renderer still tolerates the occasional stray bullet or heading rather than breaking on it,
and joins any prose the model wraps across several lines back into one paragraph. It never
renders raw HTML the model returns, so model output cannot inject markup into the page.

**Identical evidence is answered from cache, not asked of the LLM again.** Pressing "AI
summary" a second time for the same well, or reopening "Explain this view" for the same day,
when nothing underneath it has changed costs no additional tokens. `LLMService` keys a cache
on the evidence's own content hash (`_evidence_hash` — a SHA-256 of the canonical JSON)
rather than on the request's scope and filters: two requests resolve to the same cached text
only when the figures they describe are byte-identical, so a real change in the underlying
data is never served a stale answer, with no separate "is this still valid" check required.
Only a *successful* explanation is ever cached — a transient provider failure is retried on
the next identical request, never remembered as permanent. `ExplainResponse.cached` reports
which happened; the panel shows it as a colour, not a word — green (`.explain--fresh`, tinted
with the same `--on-plan` token used everywhere else in the app) for a call just made to the
LLM, red (`.explain--cached`, `--danger`) for an earlier answer reused. A "cached" text label
was tried first and judged to be one more thing to read on a screen meant to be skimmed; a
colour already carries meaning throughout this dashboard (status pills, day-strip figures),
so this reuses that convention instead of introducing a new kind of label. Neither tone is
shown while loading or when the explanation is unavailable — there is nothing generated or
reused yet to signal.

**An open explanation always describes one specific date; changing the date closes it.**
Reworded from "should the operator have to notice and close it themselves" to "no": the
top-level "Explain this view" panel closes itself the moment `reportDate` changes (a
`useEffect` in `DailyMorningBrief.jsx`, the same way the drill-down path already resets), and
every well row's own inline panel closes with it — `WellList.jsx` keys its row list on
`reportDate`, so a date change unmounts and recreates every row, discarding each one's local
"is my AI summary open" state rather than leaving it sitting open and describing a date the
operator has since navigated away from. A well's own detail page closes the same way already,
for the same underlying reason: `selectDate` resets the drill-down path, which unmounts it.

**The cache survives a restart — this was the second bug caught while building it.** An
earlier version kept the cache in memory only, so a dev auto-reload, a redeploy, or simply
stopping and re-running the app threw every cached explanation away; the *very first* request
after any restart always paid for a fresh call, indistinguishable from a genuinely new
question, even for a well explained a minute before the restart. Every change is now written
straight through to `backend/.cache/explain_cache.json` (`EXPLAIN_CACHE_FILE`), and
`LLMService`'s constructor loads whatever is already there — so a freshly started process
starts warm. Verified by stopping and restarting the dev server three times in a row against
the same explained well: the log line `Explanation cache warmed from …: 1 date(s), 1 entry`
appeared on each restart, `POST /api/daily/explain` for that well returned `"cached": true`
on the very first request every time, and `llm_usage_log.xlsx` (below) gained no new row
across any of the three restarts. Content-hashing is still what makes this *correct*, not
just cheap: a real data change still produces a different hash and is never served a stale
answer, no matter how many restarts sit between the two requests.

A "Refresh" additionally purges every cached explanation for that report date outright
(`LLMService.invalidate_date`, called from both `/api/daily/summary` and `/api/daily/group-details`
whenever `refresh=true`), so a deliberate refresh always gets a fresh explanation on the next
request even in the rare case where the reloaded data comes back byte-identical to before —
correctness here does not depend on guessing whether a refresh actually changed anything.

Two requests racing on the exact same *not-yet-cached* evidence — two browser tabs open on
the same well, or (as also caught live while verifying this) React's development-mode
double-effect firing a request twice for one click — do not both reach the LLM either: the
first to arrive holds a per-key lock (`_ExplainCache.key_lock`) for the duration of the call,
so the second waits, then finds the answer already cached rather than generating its own,
differently-worded one at a non-deterministic temperature. `EXPLAIN_CACHE_MAX_ENTRIES`
(default 500) bounds memory with oldest-first eviction across all dates combined; it is a
memory limit only; content-hashing is what already guarantees a stale answer is never served,
independent of this number.

**The provider and model are configuration, never code.** `LLM_PROVIDER` (`openai` or
`groq` — both speak the same chat-completions protocol) and `LLM_MODEL` in `backend/.env`
decide which service actually answers; `LLMService` reads them fresh from settings on every
call rather than hardcoding either. The default configuration is `openai` /
`gpt-4o-mini`; switching providers or models is a `.env` edit, never a code change.

### Token-expense log — deliberately independent of this application

Every real call to the LLM (never a cached one — see above) is also recorded by
`llm_usage_tracker.py`, a small script at the **project root**, outside both `backend/` and
`frontend/`. It appends one row to `llm_usage_log.xlsx` (created on first use, also at the
project root): timestamp, provider, model, how long the call took, its input/output token
counts, and — when the provider reports it — how much of the input was served from the
provider's own prompt cache (OpenAI's `usage.prompt_tokens_details.cached_tokens`, typically
billed at a discount; blank, not zero, when a provider doesn't report this breakdown at all).

**A live totals row always sits directly beneath the data**, never appended after it: its
first cell reads `TOTAL calls: N` (a real `COUNTA` formula, not a number typed in once), and
every numeric column carries a real `SUM` formula over exactly the data rows above it —
Duration, Input Tokens, Output Tokens, Input Cache Tokens. A new row is *inserted* directly
above the existing totals row, which is what keeps the totals row pinned to the bottom and
its SUM ranges correct as the log grows: `sheet.insert_rows()` at the totals row's own
position pushes it down by one, the new data goes where it was, and the totals row is then
rewritten one row lower with its ranges extended to include the new row. Opening the file in
Excel always shows a correct running total, with no manual work and no stale formula left
behind by an earlier version of the row count.

That file is deliberately **independent of the rest of this project**: it imports nothing
from `backend/` or `frontend/`, and the *only* file it reads is `backend/.env` (its own tiny
parser, not the backend's settings module), from which it takes the current provider and
model. Everything else it records — token counts, duration — is supplied as plain arguments
by whichever code just made a real call, since those are facts about one specific request
that no file could know in advance. `LLMService.explain` loads it by file path (not a normal
package import, to keep the dependency one-directional: the app reaches out to the tracker,
the tracker never reaches back in) and calls it once, right after a successful response,
never for a cache hit. A missing or broken tracker file disables logging, quietly, without
affecting a single explanation — this is expense bookkeeping, not a feature the dashboard
depends on.

**A real, fixed leak, caught while wiring this in.** The first end-to-end test showed the
log gaining three rows with `Duration (s)` of `0` and blank token counts before a single real
row — the test suite itself was writing to the *real* project-root log file, because
`llm_service.py`'s usage-tracker hook fires after any successful response, mocked or not, and
one existing test (`test_evidence_carries_classifications_never_raw_sql`) posted to
`/api/daily/explain` through the shared `LLMService` singleton without mocking `.explain()` —
meaning it could also have reached the real, now-genuinely-configured OpenAI endpoint and
spent real tokens on every test run, silently. Fixed two ways: that one test now stubs
`.explain()`, consistent with this suite's own stated principle of running entirely offline
(`backend/tests/conftest.py`), and a new autouse fixture (`_isolate_llm_side_effects`)
redirects the shared `LLMService` singleton's cache file to a throwaway path and disables
usage logging for every test, so no future test — mocked or not — can leave a trace in either
real project file again.

---

## 11. Read-only guarantee

This feature only reads. The guarantee is enforced in three places:

1. connections are opened `readonly=True` with autocommit, so no transaction is left open;
2. every statement passes `assert_read_only()`, which requires a `SELECT`/`WITH` statement
   and rejects `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `ALTER`, `DROP`, `TRUNCATE`,
   `CREATE`, `EXEC`, `GRANT`, `BACKUP` and stacked statements — while correctly ignoring
   those words inside comments and string literals;
3. tests assert both that the shipped queries pass the guard and that each write statement
   is rejected.

The Excel export is assembled in memory and the LLM never touches the database, so neither
writes back.

**Logged secrets are redacted, and the redaction is tested against the actual key shape in
use.** No credential is deliberately logged anywhere in this application; `SecretRedactingFilter`
(`app/utils/logging_config.py`) is a second line of defence in case one reaches a log record
by accident. An earlier version of its patterns only matched a hyphen-separated key
(`gsk-...`/`sk-...`) and only redacted as far as the word `Bearer` in an `Authorization: Bearer
<token>` header, leaving the actual token — the shape this app's own Groq key is in
(`gsk_...`, underscore) and the shape its own `httpx` client sends — unredacted in either
case. `tests/test_logging_redaction.py` locks in the fix: every credential shape this app can
actually produce (env-style assignment, a bare key, an `Authorization` header as a raw string
or a quoted dict repr, connection-string `PWD=`/`UID=`) is asserted redacted, and a handful of
ordinary operational log lines (`sql.daily_detail executed in …`, `req … -> 200 OK …`) are
asserted untouched, so the filter cannot silently regress into either failure mode again.

**No authentication is implemented at the application layer.** Every endpoint answers
without a login or an API key: this is a read-only reporting layer, and the assumption is
that network placement (an internal segment, a VPN, a reverse proxy in front) is what
restricts who can reach it. Nothing here should be exposed directly to an untrusted network
without such a layer in front of it.

---

## 12. Performance

* One day costs **two queries**, both filtered in SQL by report date and live wells.
* The resolved day is held in a short TTL cache (`DAILY_CACHE_TTL_SECONDS`), so every
  drill-down level — group, status, well, task — is served from it. There is **no query per
  well**; a test asserts this.
* Quantities cross the wire as exact decimal strings, so no float rounding is introduced
  between SQL Server and the browser.
* Aborted `fetch` requests mean a rapid date change can never leave stale data on screen.

**Recommended index — not applied.** The schema is never altered by this application. A
day's query currently scans `well.task_daily` (≈110k rows, ~1–1.5 s). If that becomes a
problem, the DBA may consider:

```sql
CREATE NONCLUSTERED INDEX IX_task_daily_ActionOn
    ON well.task_daily (ActionOn)
    INCLUDE (schedule_id, task_code, well_id, planned, progress, uom_id, crew_id,
             crew_type_id, daily_data, updated_at);
```

`well_id` is left out of the index key because it is now `varchar` and every query reads it
through `TRY_CONVERT(int, td.well_id)` (see §3) — a plain index on the raw column would not be
used by that expression. A computed, persisted column such as
`well_id_num AS TRY_CONVERT(int, well_id) PERSISTED`, indexed in its place, would let the
optimizer seek on it instead of scanning; that is a schema change and is left for the DBA to
evaluate, not applied here.

This is a recommendation for review, not a change to run automatically.

---

## 13. Configuration

Nothing environment-specific is hardcoded. Server, database, credentials, driver, ports,
LLM provider/key/model/endpoint, the grouped-vs-detail threshold, the cache TTL, the evidence
size limit, the explanation cache size and its persisted file location all come from
`backend/.env` (template: `backend/.env.example`). `llm_usage_tracker.py` (project root) is
the one exception worth calling out explicitly: it reads `backend/.env` too, for the current
provider and model, but through its own tiny parser rather than this settings module — see
§10.

The React app receives **no** backend secret: it calls a relative `/api` path through the
dev proxy, or `VITE_API_BASE_URL` in production.

Credentials are never logged. Beyond simply not logging them, a redaction filter on the
logging handler scrubs anything resembling a password, connection string or API key, and
database errors are logged by SQLSTATE rather than by driver message.

`USE_MOCK_DATA` defaults to `false` and must stay there. There is no fake data anywhere in
this application: when the database is unreachable the dashboard shows a database-error
state, and when a date genuinely has no records it shows an empty state. The two are
visibly different, because they mean different things to an operator.

---

## 14. Verified behaviour

Checked against the live `AlTasnimBI` database while building:

* **2026-08-01** — 197 raw rows resolved to 194 logical tasks across 67 live wells;
  143 `ON_PLAN`, 17 `BELOW_PLAN`, 5 `ABOVE_PLAN`, 29 `NO_ACTUAL`; 13 tasks unmapped.
  Grouped dataset, with the data-quality banner reporting the 3 superseded rows separately.
* **Traceability** — a card reading "13 tasks" under On Plan drills to exactly 13 tasks
  across 7 wells. A test asserts this for *every* count at *every* level — status, work
  category and activity — not just one.
* **Status grouping on 2026-08-01** — 224 tasks in 4 sections (170 On Plan, 6 Above Plan,
  17 Below Plan, 31 No Actual); Not Validated had none, so it had no section while the day
  totals still showed its zero. The On Plan section spans 10 units of measure, so its own
  totals are withheld and read *"10 units (Joint, Ls, M, +7) — not totalled"*, while every
  work category under it stays within one unit and reports its totals normally.
* **2026-09-11** — a single task, so `view_mode` came back `"detail"` (threshold 25) and
  `SummaryResponse.tasks` carried that one task directly.
* **Multi-dash task codes** — `FLME1165-10239-T014` resolves to activity `FLME1165`.
* **LLM down** — with an unreachable endpoint, the dashboard rendered in full and the panel
  reported the explanation as unavailable, with no fabricated text.
* **Excel** — a 3-sheet workbook (Daily Detail, Summary, Data Quality) named
  `daily_morning_brief_2026-08-01.xlsx`.
* **Schema drift caught and fixed** — `well.task_daily.well_id` drifted from `int` to `varchar`
  with 215 non-numeric rows (e.g. `'0000F'`); a bare comparison against it crashed every report
  with `SQLSTATE 22018`. Fixed with `TRY_CONVERT`, guarded by a test.
  `dbo.activity_master_mapping` was superseded by `dbo.mapping_master`: WBS resolution on a
  sample date went from 0/130 tasks to 93/130 after the swap.
* **`activity_uom` connection** — 26 of 11,277 actual-entry rows table-wide have no `uom_code`
  of their own; all 26 have a `mapping_master.UOM` reference value, now surfaced in the API,
  the well/task detail views and the Excel export without touching `MISSING_UOM` or grouping.
* **Theme toggle** — dark (default, unchanged look) and light, persisted per browser via
  `localStorage`, switching a `data-theme` attribute that every colour in the stylesheet is
  already expressed as a variable against.
* **AI explanation style** — the system instruction and renderer were changed from short
  bullet points to two-to-four-paragraph prose; verified by re-running the explain endpoint
  against a live evidence payload.
* **Crew personnel resolution** — `task_daily.crew_id`/`.crew_type_id` matched `ref.crew`/
  `ref.crew_type` for 100% of the rows that carried them (1,787/1,787 and 2,839/2,839 measured
  over 30 days of `well.task_daily`), giving a real supervisor and roster per task rather than
  just the WBS crew code.
* **Well milestones on 2026-09-14** — 1,216 outstanding (not-yet-reached) milestones across
  live wells; 42 within the 7-day priority window, 292 already overdue. A well already past
  `eng_completion_date` never appears in either list.
* **LLM retry recovers a real, reproducible failure** — a busy day's "Explain this view" (116
  tasks) was observed failing consistently with `HTTP 413` from Groq on the first attempt;
  with the retry-with-backoff added to `LLMService`, the same request succeeded on a
  subsequent attempt without any user-visible error.
* **A real, repeatable `413` on the day scope, fixed at the source** — a later live report
  (2026-08-01, 224 tasks, day scope, "all daily work") failed with `HTTP 413` even after every
  retry: the fixed 40-task evidence sample was too large for that scope regardless of
  attempts. Capping the sample per scope (`day` → 10 tasks, well → 30, task → 1) resolved it;
  re-run against the same live day, the day-scope explanation succeeded on the first attempt.
* **Well-first dashboard redesign, verified live** — the front page was changed from a
  status→WBS→activity drill-down to one row per well (`WellList.jsx`). Checked against
  2026-08-01 (224 tasks, 79 wells): the well list, sort order (busiest first), inline "AI
  summary" per row, and drill-through to `WellDetail` all matched the backend's per-well
  rollup exactly; a `validateDOMNesting` warning caught during this check (a status pill
  `<button>` nested inside the row's own `<button>`) was fixed by making the row container a
  `role="button"` `<div>` instead, confirmed absent afterward at both desktop and 375px mobile
  width, in both themes.
* **A real cache-stampede race, caught live and fixed** — verifying the explanation cache by
  hand in a browser, the very first "AI summary" click for a well returned text marked
  `cached: true` that did not match what a moment's re-read of the panel showed moments
  earlier. React's development-mode double-effect had fired two near-simultaneous requests
  for the same not-yet-cached well; both missed the empty cache and both called the LLM
  (visible as two `LLM explanation generated` log lines for one click), and whichever finished
  last overwrote the cache — a real token-doubling bug, not a display glitch. Fixed with a
  per-(date, evidence-hash) lock around the "still a miss? then call the LLM" step
  (`_ExplainCache.key_lock`): re-run against the same well afterward, exactly one
  `LLM explanation generated` line appeared per click, confirmed at the server log, and a
  concurrency test (two threads deliberately raced against a blocking fake `explain()`) fails
  without the lock and passes with it.
* **The well list did not actually refresh** — a gap introduced by the well-first redesign
  (§ below): the main dashboard's well list depended only on the report date, not on the
  "Refresh" button's token, so clicking Refresh updated the day totals and milestones but left
  the well list itself showing the previous load. Fixed by threading the same refresh signal
  through it and adding `refresh` support to `/api/daily/group-details`; confirmed via the
  network log that a Refresh click now issues `group-details?...&refresh=true`, matching the
  `summary` call it already accompanied.
* **Provider switched from Groq to OpenAI, live** — `backend/.env` changed to `LLM_PROVIDER=openai`,
  `LLM_MODEL=gpt-4o-mini`, no code change required. Confirmed at `/api/health` and the
  startup log (`'llm_provider': 'openai', 'llm_model': 'gpt-4o-mini'`), and with a real
  "AI summary" click against the live evidence for well 30365, which returned a genuine
  gpt-4o-mini explanation with the backtick-highlighted values still rendering correctly.
* **The explanation cache surviving a restart, proven across three real restarts** — before
  persistence, only the *second* request within one running process was ever served from
  cache; a restart (the dev server's own auto-reload, or a plain re-run) reset it to zero.
  Stopped and restarted the dev server three times in a row after explaining well 30365 once:
  each restart's log showed `Explanation cache warmed from …: 1 date(s), 1 entry`, and
  `POST /api/daily/explain` for that well returned `"cached": true` immediately every time —
  the very first request after each restart, not the second. `llm_usage_log.xlsx` gained
  exactly one row for the whole exercise (the one real call, before the first restart), never
  three, confirming zero additional LLM spend across all three restarts.
* **A real token-expense leak in the test suite, caught and fixed while wiring in usage
  logging** — the first test run after adding `llm_usage_tracker.py` produced three rows in
  the real project-root `llm_usage_log.xlsx` with `Duration (s)` of `0` and blank token
  counts, before the one genuine row. Traced to one existing test posting to
  `/api/daily/explain` through the real, shared `LLMService` singleton without mocking
  `.explain()` — meaning it could reach the real, now-genuinely-configured OpenAI endpoint and
  spend real tokens on every test run. Fixed by stubbing that one test's `.explain()` call
  (it only ever asserted on the evidence, never the generated text) and adding an autouse
  fixture that redirects the shared singleton's cache file to a throwaway path and disables
  usage logging for every test; re-ran the full suite afterward and confirmed neither
  `backend/.cache/explain_cache.json` nor `llm_usage_log.xlsx` existed at all once the run
  finished.
* **The usage log's live totals row, migration, and "never raises" contract** — verified
  against the actual project-root file with a genuinely old row already in it (no
  `Input Cache Tokens` column, no totals row): calling `log_usage` once migrated that row in
  place (the new column blank for it, since that data was never captured), added the new
  row, and appended a totals row covering both. A second real call (a different well, through
  the live app) grew the totals row's ranges from `A2:A2` to `A2:A3` correctly, with the new
  row inserted *above* the totals row rather than after it. `test_llm_usage_tracker.py`
  (12 tests, run standalone, isolated to a `tmp_path` file in every case) locks in the
  migration, the range growth, and that a write to an unwritable location returns `False`
  rather than raising — the tracker's whole contract is that a bookkeeping failure can never
  take an explanation down with it.
* **A day's example tasks representing the whole day, not the first well in SQL order** —
  reported live: a day with 46 wells kept reading as if it were about one well. Reproduced
  against the real day (2026-07-30, 75 wells, 270 tasks): the old sampling's example tasks
  named only wells that happened to sort first by `(uom_code, wbs, activity_code, well_id)`.
  After `EvidenceService._representative_sample`, the same day's examples named three
  different wells — 36273, 30365, 32517 — one for each of `ON_PLAN`, `BELOW_PLAN` and
  `ABOVE_PLAN` respectively, in a single explanation. 8 new tests
  (`test_evidence_sampling.py`) assert status diversity, well diversity, determinism, and that
  a well with many tasks never crowds out every other well from a fixed-size sample.
* **Colour instead of a "cached" word, and the panel closing itself on a date change** — both
  verified live. A fresh call showed `class="explain explain--fresh"` with a computed
  background of `rgba(26, 138, 61, 0.1)` (the `--on-plan` green); closing and reopening the
  same well's summary showed `explain--cached` with `rgba(196, 41, 26, 0.09)` (`--danger`
  red) instead, with no code-visible text label either time. Then, with a well's summary open,
  changing the report date was confirmed (via `find`, which returned no match for "Hide AI
  summary" afterward) to close it — both the top-level panel and every open per-well row.

---

## 15. Crew personnel (task → crew → supervisor → employees)

`activity_master_csv.crew_code` (daily_report_rules.md §2) stays the sole, authoritative WBS
crew label for a task and is never touched by this feature. Separately, `task_daily.crew_id`
and `.crew_type_id` identify the *specific crew instance* that actually ran the task, and
resolve cleanly (measured: 100% match rate where present) to:

```
task_daily.crew_id  → ref.crew.crew_id
                         ├─ ref.crew.supervisor_id → ref.employee.id   (the crew's supervisor)
                         └─ bridge.crew_employee.crew_id → ref.employee.id  (the crew's roster)
task_daily.crew_type_id → ref.crew_type.crew_type_id  (the crew's discipline/type name)
```

This is resolved once, in `crew_personnel` (a CTE in `sql/daily_tasks.sql`, joined by
`crew_id` — a scalar join, so it never fans out the task grain), and carried on every
`TaskOut` as `crew_type_name`, `crew_instance_code`, `crew_supervisor` and `crew_employees`.
It is additive evidence, exactly like `activity_uom` in §6: shown alongside `crew_code`,
never in place of it, and absent (not guessed at) whenever a task carries no `crew_id` or the
crew instance has no supervisor/roster on file. The UI renders it as a chain — Well → WBS →
Activity → Crew type → Supervisor → Employees — on both the task card and well detail views.

## 16. Well lifecycle priority window

A live well (`eng_completion_date IS NULL`) that is approaching, or has already missed, one
of the four dated milestones in business_rules.md §2/§3 — pegging sheet, FLAF, rig-on,
rig-off — is surfaced as a priority alert, independent of whichever report date the Daily
Morning Brief is currently showing (it is evaluated against today).

`sql/well_milestones.sql` is raw evidence only: one row per milestone that has not yet been
reached (its actual-date column is still `NULL`) and whose deadline is computable (its source
date is not `NULL`). It decides nothing about what counts as "near". That threshold —
`MILESTONE_PRIORITY_WINDOW_DAYS`, default 7 — is owned by `app/services/milestone_service.py`
exactly the way `DETAIL_VIEW_TASK_THRESHOLD` is: business_rules.md defines the deadlines
themselves but not how many days of advance notice counts as a priority, so it stays a
configurable presentation setting rather than an invented business rule.

Outstanding milestones split into two lists, never merged:

* **`upcoming`** — `0 <= days_remaining <= window_days`, soonest first. This is the
  "priority window" a well enters as it nears a deadline.
* **`overdue`** — `days_remaining < 0`, most-recently-missed first, capped at
  `MILESTONE_OVERDUE_DISPLAY_LIMIT` (default 20) with the true count in `overdue_count`.

They are kept apart because business_rules.md §3 already treats a missed deadline as a
standing condition, and on this data the overdue backlog runs into the hundreds (292 measured
on 2026-09-14) against a much smaller upcoming list (42 within 7 days) — folding them together
would bury the wells that are still approaching their deadline.

**The main dashboard never shows the list itself, only two numbers.** An early version put
the full `upcoming` list directly on the main dashboard as an expandable banner; with 40+
rows it made the first screen feel cluttered. A later version replaced that with a single
compact clickable banner row. Both numbers now live in `DayStrip.jsx`, the same one-line strip
that reports the day's task count — "N tasks today · M upcoming milestones · K overdue" —
so the day's headline figures and the well-lifecycle figures read as one summary instead of
two separate widgets stacked on top of each other. Selecting either milestone figure drills
into `MilestonesPage`, a dedicated level in the same `current.type` drill-down state that
`DailyMorningBrief.jsx` already uses for well/task, reached via the normal breadcrumb/back
navigation. That page lists `upcoming` openly and `overdue` behind a collapsed toggle;
clicking any alert expands the well's full set of lifecycle dates in place, with a link into
that well's daily tasks for the currently selected report date.

The underlying `well.well_master` scan is cached with the same TTL discipline as the daily
dataset (`DAILY_CACHE_TTL_SECONDS`), so repeated banner/page loads do not repeat the full scan.

---

## 17. Presentation conventions

Rules that apply everywhere a well's or a task's figures are shown, not just in one
component:

* **The front page stays a list of main points; full detail lives one click away.**
  `WellList.jsx` shows one row per well — its busiest activity (plus how many others), task
  count, and only the non-zero status counts — never the tasks themselves. Nothing is hidden
  by this: every count on the row is the same figure the backend returns for that well, and
  the row's click target opens every one of that well's tasks on `WellDetail.jsx`. A well with
  many tasks is not a special case; every well works the same way, so there is no separate
  threshold to configure or reason about here (contrast `DETAIL_VIEW_TASK_THRESHOLD`, §12/§13,
  which is a backend decision about a different question — grouped vs. individual dataset
  shape — and is independent of this).
* **Planned, Actual and Progress are always grouped as one unit.** `QuantityTrio`
  (`frontend/src/components/common/index.jsx`) renders the three together in a single boxed
  row; `WellDetail.jsx`'s per-task panel uses it instead of listing the three as separate rows
  among unrelated fields.
* **A numeric value is always coloured distinctly from labels and prose**, via the shared
  `.num` CSS class / `Num` component (`--num` CSS variable — teal, both themes). This is
  deliberately separate from the existing semantic status colours (on-plan green, below-plan
  amber, above-plan blue, danger red, not-validated purple, and the milestone
  upcoming/overdue amber/red): a plain count or quantity gets the generic numeric colour, and
  a value that already carries a status/urgency meaning keeps that colour instead — the status
  pill on a well row, for instance, keeps its status colour rather than switching to teal.
