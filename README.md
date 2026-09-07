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
│   │   ├── api/               Route handlers (wells, investigation)
│   │   ├── database/          DB connection helper
│   │   ├── services/          Query execution, data cleaning, risk scoring
│   │   └── responses/         investigation.json output (not committed)
│   └── sql/                    Raw SQL used by the services
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
  top delayed tasks); also written to `backend/app/responses/investigation.json`

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

| Scenario | Condition | Rule |
|---|---|---|
| Before drilling | no rig-on yet | Construction must finish 1 day before the expected rig-on. Risk ramps over a 60-day window and spikes once that deadline passes. |
| Drilling in progress | rig-on done, no rig-off | Not scored — outside the current scope. |
| After drilling | rig-off recorded, hook-up incomplete | Due once today > rig-off + 2 days; risk grows with days overdue. |
| Completed | eng. completion recorded | Excluded from all lists. |

The thresholds are deterministic heuristics defined as named constants at the
top of `backend/app/services/risk.py` — tune them once real outcomes are
available to validate against.

Not yet implemented (needs schema confirmation first):

- `Hoist_On_Date` / `Hoist_Off_Date` / `Wellpad_Handover_Date` in the
  after-drilling due-date calculation — those columns do not exist yet, so the
  rule currently uses `rig_off_date + 2 days` only.
- Non-due exclusion for FLAF/SCR delays and PDO issues, and the resulting
  "bonus potential" bucket.

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
