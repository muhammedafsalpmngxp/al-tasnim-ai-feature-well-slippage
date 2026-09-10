# Well Delay AI (Al-Tasnim)

Well-slippage monitoring and risk scoring for drilling operations. The backend
flags wells whose rig-on/rig-off dates have slipped past their expected dates,
produces a deterministic SQL "evidence layer" for a single well's task-level
schedule status, and turns that evidence into a per-well risk assessment:
a 0–100 risk score, expected delay in days, and the lagging WBS branches.
The frontend is a React dashboard for browsing slipped wells and inspecting
one well's risk detail.

## Project structure

```
.
├── backend/                   FastAPI service
│   ├── .env                   Database credentials (not committed)
│   ├── main.py                FastAPI app entrypoint (+ CORS for the React dev server)
│   ├── requirements.txt       Backend dependencies
│   ├── script.py              Standalone SQL Server schema/data inventory tool
│   ├── database_inventory.txt Output of script.py (not committed)
│   ├── app/
│   │   ├── api/               Route handlers (wells, investigation, insights)
│   │   ├── database/          DB connection helper (+ datetimeoffset decoder)
│   │   ├── services/
│   │   │   ├── evidence.py        runs the authoritative SQL, returns raw evidence
│   │   │   ├── milestones.py      which SQL column describes which gate
│   │   │   ├── ui_json.py         raw evidence -> dashboard JSON
│   │   │   ├── ai_evidence.py     raw evidence -> compact LLM evidence
│   │   │   ├── risk.py            composite risk score (no date arithmetic)
│   │   │   ├── attribution.py     due / non-due mapping
│   │   │   ├── serialization.py   JSON-safety formatting helpers
│   │   │   ├── investigation.py   pipeline orchestration + debug persistence
│   │   │   └── llm.py             Groq narration
│   │   └── responses/         investigation.json + evidence_raw/ai (not committed)
│   └── sql/
│       ├── well_evidence.sql      AUTHORITATIVE evidence layer (single source of truth)
│       ├── slipped_wells.sql      fleet-wide slippage detection
│       ├── well_summary.sql       headline counts
│       └── well_project_ids.sql   all project IDs for a well
│
├── run.py                     Dev runner: starts backend + frontend together
│
├── frontend/                   React dashboard (Vite)
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   ├── .env.example            VITE_API_URL
│   └── src/
│       ├── App.jsx             Page orchestration + data loading
│       ├── api.js              Backend fetch wrappers
│       ├── components/         SummaryCards, WellSelect, WellDetail
│       └── styles.css
│
└── .gitignore
```

## Prerequisites

- Python 3.11+
- Node.js 18+ (for the React frontend)
- Microsoft ODBC Driver 17 or 18 for SQL Server (used by `pyodbc`)
- Network access to the SQL Server instance holding the `AlTasnimBI` database

## Setup

1. Create and activate a virtual environment at the project root:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   source .venv/bin/activate   # macOS/Linux
   ```

2. Install backend dependencies:

   ```bash
   pip install -r backend/requirements.txt
   ```

3. Install frontend dependencies:

   ```bash
   cd frontend
   npm install
   ```

4. Configure the backend database connection in `backend/.env`:

   ```
   DB_SERVER=your-server-host
   DB_PORT=1433
   DB_NAME=AlTasnimBI
   DB_USER=your-username
   DB_PASSWORD=your-password
   DB_DRIVER=ODBC Driver 17 for SQL Server
   DB_CONNECTION_TIMEOUT=30
   ```

## Running

**Both at once (recommended for local dev):**

```bash
python run.py
```

Starts the backend and frontend together, prefixes their logs (`[backend]` /
`[frontend]`), and stops both on Ctrl+C or if either one exits. Override the
backend bind address with `BACKEND_HOST` / `BACKEND_PORT`.

**Backend (FastAPI) on its own:**

```bash
cd backend
uvicorn main:app --reload
```

Runs on `http://127.0.0.1:8000` by default. Key endpoints:

- `GET /api/wells/summary` — well counts: total, live, completed, slipped
  (due), slipped (non-due), not slipped
- `GET /api/slipped-wells` — slipped wells with `delay_days`, most delayed first
- `GET /api/well/{well_id}/investigation` — risk assessment for one well
  (scenario, due status, risk score, expected delay, lagging WBS branches,
  delayed activities); also written to `backend/app/responses/investigation.json`
- `GET /api/insights/portfolio` — AI summary of the portfolio counts
- `GET /api/insights/well/{well_id}` — AI summary of one well's assessment

**Frontend (React dashboard):**

```bash
cd frontend
npm run dev
```

Opens on `http://localhost:5173`. If the backend is not running on
`http://127.0.0.1:8000`, copy `.env.example` to `.env` and set `VITE_API_URL`.

The backend allows the Vite dev-server origin via CORS. If the frontend is
served from a different origin, set `CORS_ALLOWED_ORIGINS` (comma-separated)
in `backend/.env`.

## Architecture: who is allowed to calculate what

```
DATABASE
  └─ backend/sql/well_evidence.sql      AUTHORITATIVE DETERMINISTIC EVIDENCE
       │                                 all milestone, delay, DQ, activity,
       │                                 WBS, quantity, productivity and
       │                                 classification logic lives HERE
       ├─ raw_evidence                   untouched SQL output, 2 result sets
       │    ├─ build_ui_json()           -> dashboard payload
       │    └─ build_ai_evidence()       -> compact facts for the model
       │                                    (4% the size of raw)
       └─ LLM  ->  {"summary": "..."}    EXPLANATION ONLY
```

**SQL calculates. Python structures. The LLM explains.** These
responsibilities are never reversed.

`well_evidence.sql` carries CTEs 1–15 byte-for-byte from the approved
source, so no business rule can drift. It returns two result sets — one
well-level row (always present, even for a well with no tasks) and one
row per current logical task with the full evidence projection. The
delayed-activity filter is applied downstream so a single query serves
both the full evidence view and the delayed view.

The only deliberate Python-side calculations, both documented in place:

| Value | Why not SQL |
|---|---|
| `risk.risk_score` | the SQL produces `ai_schedule_classification` and the two evidence levels, but no 0–100 composite |
| `risk.due_status` | due/non-due attribution from `kpi_miss_reason` ([attribution.py](backend/app/services/attribution.py)) |

Everything else the dashboard and the summary show — every date, delay,
variance, status and flag — is read straight out of the SQL result.
`risk.expected_delay_days` is not derived either: it is the SQL's own
delay column for whichever gate the scenario measures
(`construction_lag_days` before drilling, `hookup_delay_days` after), so
the figure on screen is the figure the SQL computed.

### What the model may not do

The prompt forbids, explicitly: calculating dates, day differences,
percentages or risk scores; deciding due/non-due or a milestone status;
inventing missing values; inferring a delay that is not present as a
`delay_days` above zero; inferring causality from remarks; inferring a
resource shortage from the existence of resource data; treating an
activity's delay as the well's delay; reinterpreting
`AHEAD_OF_SCHEDULE` as overdue; or contradicting the supplied
attribution.

Accountability is handled with particular care. The model was observed
**inverting** the enum — reading `NON_DUE` and writing "attributed to
Tasnim's responsibility". So the AI evidence no longer asks it to
interpret: `accountability.statement` is a ready-made sentence built in
Python from the authoritative verdict, and the prompt instructs the
model to reproduce its meaning rather than re-derive it.

### Well delay is not activity delay

These are separate measurements and the summary must keep them apart.
The AI evidence names the gate the well-level figure belongs to
(`risk.expected_delay_gate`) so the distinction is unambiguous:

> the hook-up milestone is 366 days overdue, while the most delayed
> activity is FLC1380 at 392 days

## Slippage criteria

Detection runs over **live wells only** (`eng_completion_date IS NULL`) — a
hooked-up well is out of Tasnim scope and cannot slip. A well is flagged if
**any** of the six tests below fires; each firing test is reported in the
well's `slip_reasons`, and `delay_days` is the **worst** lateness across all of
them. Defined in [backend/sql/slipped_wells.sql](backend/sql/slipped_wells.sql).

| # | Reason code | Test | Meaning |
|---|---|---|---|
| 1 | `RIG_ON` | `rig_on_date > ex_rig_on_date`, or `rig_on_date IS NULL AND ex_rig_on_date < today` | Rig-on late, or overdue and still not recorded |
| 2 | `RIG_OFF` | `rig_off_date > ex_rig_off_date`, or `rig_off_date IS NULL AND ex_rig_off_date < today` | Rig-off late, or overdue and still not recorded |
| 3 | `HOOKUP` | `rig_off_date` present AND `today > rig_off_date + 2 days` | Hook-up (Tasnim scope completion) overdue after drilling |
| 4 | `CONSTRUCTION` | `today > ex_rig_on_date − 1 day AND rig_on_date IS NULL` | Construction not finished by its rig-on−1-day deadline |
| 5 | `PEGGING` | `pegged_date > ex_rig_on_date − 60 days`, or NULL past that deadline | Pegging gate missed or late |
| 6 | `FLAF` | `flaf_issue_date > ex_rig_on_date − 90 days`, or NULL past that deadline | FLAF gate missed or late |

Tests 5 and 6 are the **early-warning** signals: they fire 60 and 90 days
before rig-on, which is what makes the dashboard predictive rather than
purely retrospective.

### NULL handling

Source data is incomplete, so every test is anchored on a column that is
reliably populated:

- `ex_rig_on_date` and `ex_rig_off_date` are 100% populated and serve as the
  baselines.
- A test needing an ACTUAL date only fires when that date exists — e.g. hook-up
  requires `rig_off_date`, so a missing rig-off can never look like a slip.
- `const_complete_date` (34% populated), `scr_date` (43%) and
  `tie_in_ready_date` (68%) are deliberately **not** used as slip tests: a NULL
  there means "not recorded" far more often than "late". Construction therefore
  uses the NULL-safe rule above instead of `const_complete_date`.

### Due vs non-due (bonus potential)

`well_master.kpi_miss_reason` attributes the delay. Reasons outside Tasnim's
control mark the well **NON_DUE** — reported as bonus potential rather than
counted as Tasnim-side risk. Mapping lives in
[backend/app/services/attribution.py](backend/app/services/attribution.py).

| Classification | `kpi_miss_reason` values |
|---|---|
| **NON_DUE** (bonus potential) | anything containing `FLAF`; `SCR`; `Awaiting Manifold/MSV`; `Awaiting Handover`; `Well Suspended`; `NON KPI` / `Non KPI well` |
| **DUE** (Tasnim scope) | everything else, including `Scope Change`, `Material Availability`, `Non Standard`, and wells with no reason recorded |

Matching is case- and whitespace-insensitive, since the source values are
inconsistently entered (`FLAF Delayed`, `FLAF DELAY`, `FLAF`).

### Data-quality flags

A flagged well also carries `has_data_issue`, raised when any of these hold:

- `dq_missing_baseline` — `ex_rig_on_date` or `ex_rig_off_date` is NULL, so a
  milestone cannot be evaluated at all.
- `dq_rig_off_before_rig_on` — rig-off recorded before rig-on.
- `dq_actual_far_before_plan` — an actual date more than 180 days *before* its
  baseline, meaning plan and actual were maintained against different
  schedules. This inflates computed lateness, so those figures are not
  trustworthy.

## Risk model

Each selected well is classified from `rig_on_date` / `rig_off_date` /
`eng_completion_date` and scored accordingly:

| Scenario | Condition | Deadline |
|---|---|---|
| Before drilling | no rig-on yet | `ex_rig_on_date − 1 day` — construction must finish the day before rig-on |
| After drilling | rig-off recorded, hook-up incomplete | `rig_off_date + 2 days` |
| Drilling in progress | rig-on done, no rig-off | Not scored — outside the current scope |
| Completed | eng. completion recorded | Excluded from all lists |

### Score composition

`risk_score` is a weighted blend of three normalised components, so no single
input can pin it at 100:

| Component | Weight | Basis |
|---|---|---|
| Lateness | 0.55 | Days past the deadline, via `days / (days + 90)` |
| Breadth | 0.25 | How many of the four milestones have slipped |
| Activity | 0.20 | Delayed-activity count and worst activity delay |

Lateness uses a **saturating curve rather than a linear ramp**. The original
linear version (`60 + days × 2`) hit its ceiling at ~20 days overdue, which put
**31% of wells at exactly 100** and left the score unable to distinguish a
30-day slip from a 300-day one. The curve reaches 0.5 at 90 days and keeps
rising without ever reaching 1, so ordering is preserved at any magnitude.
Measured across the live fleet, the change took after-drilling wells from 8 to
28 distinct score values, with none at 100.

When a well has no activity rows, the activity weight is **redistributed** over
the other two rather than scored as zero — missing evidence should not read as
an absence of risk. Wells that have not yet reached their deadline get a
separate anticipatory score capped at 40, so "due" and "not yet due" never look
alike.

Thresholds are named constants at the top of
[backend/app/services/risk.py](backend/app/services/risk.py) — tune them once
real outcomes are available to validate against.

## AI summaries

The dashboard narrates its own output through Groq. The model **computes
nothing**: the already-computed JSON is handed to it and it only explains what
is there, so the prose and the dashboard can never disagree. Every count,
percentage and day-count — including combined figures like "due + non-due" —
is calculated in Python and passed in; the prompt explicitly forbids the model
from deriving, adding or otherwise computing a number itself. Output is
deterministic (`temperature: 0`) and returned as `{"summary": "..."}` via
Groq's JSON mode, so the shape can't drift.

| Endpoint | Narrates |
|---|---|
| `GET /api/insights/portfolio` | Well counts and the due/non-due split, every recorded non-due cause, ranked |
| `GET /api/insights/well/{well_id}` | The well's stage; every slipped gate with its expected date, actual date and exact days late; accountability and `kpi_miss_reason`; `remarks`; the driving activity or WBS branch; the data-quality caveat if flagged |

Both are fetched separately from the figures they describe, so a slow or
unavailable model never blocks the dashboard.

### Expected vs. actual dates

Every gate (rig-on, rig-off, pegging, FLAF, hook-up) carries its expected
date, its actual date (or "not yet recorded"), and the exact number of days
late — computed once in
[`risk.py`](backend/app/services/risk.py) as `milestone_delays` and reused by
both the UI's Key Dates panel and the AI prompt, so the two can never disagree
on a day count. A gate only shows a "days late" chip when `delay_days > 0`.

### Due vs. non-due theming

The well-detail panel is themed by `risk.due_status`, not just badged: a red
top border and banner for **DUE** (Tasnim-owned) wells, amber for **NON_DUE**
(bonus potential) wells — in addition to the existing due/non-due colours on
the summary cards and the well-select dropdown groups.

### Project IDs

`well_master` carries one `project_id` per well, but `task_daily` rows for the
same well frequently reference a **different** one — separate scopes of work
(Flowline vs. Location, for example) are tracked as separate projects against
the same physical well. Most wells have exactly one project_id; some have two
or more.
[`well_project_ids.sql`](backend/sql/well_project_ids.sql) returns the union
of every `project_id` seen for the well across both tables, resolved to
`project_code` / `project_name` via `project.project_mstr` where a match
exists — a `project_id` with no match still returns its own row (fields
`null`) rather than being dropped. Shown in the well-detail panel as
**Projects (`N`)**, right above Key Dates.

### Highlighted database terms

Beyond the numeric highlighting (dates green, percentages blue, other numbers
red), the AI paragraph highlights **verbatim database content** — a recorded
`kpi_miss_reason`, an activity name/code, a WBS branch, a project code/name,
the `remarks` text — in purple italic, distinct from the numeric colours. The
term list is never fixed: [`llm.py`](backend/app/services/llm.py)'s
`well_highlight_terms()` / `portfolio_highlight_terms()` build it fresh from
whatever the current response's JSON actually contains, and the API returns it
as `highlight_terms` alongside `summary`. Raw status enums (`due_status`,
`scenario`, milestone statuses) are deliberately excluded — once the model
translates them into prose ("due", "missed"), they're ordinary English words,
and highlighting every occurrence would colour normal sentence structure
rather than actual database content.

Configuration in `.env`:

```
api_key=<your Groq API key>
GROQ_MODEL=openai/gpt-oss-120b
```

`GROQ_MODEL` is optional. Note that **`llama-3.3-70b-versatile` is not
available on the current Groq account** — the key returns `model_not_found`,
and the account exposes no Llama chat model. The default is
`openai/gpt-oss-120b`, the largest general-purpose model it does have;
`openai/gpt-oss-20b`, `qwen/qwen3.8-27b` and `groq/compound` are also
available. Check with:

```bash
curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $api_key"
```

Not yet implemented (needs schema confirmation first):

- `hoist_on_date` / `hoist_off_date` / `wellpad_handover_date` in the
  after-drilling due-date rule. The columns **do** exist but are ~1% and 0.1%
  populated respectively, and `well.wmr_conversion` (which also carries them,
  plus `expected_hoist_on_date`) is an empty table — so the rule uses
  `rig_off_date + 2 days` only.

**Database inventory tool (optional, backend-only):**

```bash
cd backend
python script.py
```

Connects to the database using the same `.env` credentials and writes a full
schema/sample-data dump to `backend/database_inventory.txt`. This file
contains real server/connection details and sample production data, so it is
git-ignored — do not commit it.

## Notes

- `backend/app/responses/investigation.json` is generated at runtime and is
  git-ignored.
- `backend/.env` and `backend/database_inventory.txt` contain sensitive
  connection details and are git-ignored.
