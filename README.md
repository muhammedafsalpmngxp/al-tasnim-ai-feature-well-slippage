# Well Delay AI (Al-Tasnim)

Well-slippage monitoring and AI-assisted delay analysis for drilling operations — with a
schema-agnostic SQL layer that can regenerate itself when the underlying database changes.

The backend flags wells that have slipped on rig-on, rig-off, pegging, FLAF, or hook-up, and
produces a deterministic SQL "evidence layer" — well milestones plus every task under the well —
for a single well. That evidence is handed to an LLM (via OpenAI), constrained by an
authoritative business-rules document, to produce a short, evidence-cited explanation of why the
well is delayed, including which tasks are delayed and which crew was assigned to each. The
frontend is a React dashboard for browsing slipped wells and running an investigation.

On top of that, the app can point itself at a **different** database from the UI: it introspects
the new schema, writes a compact schema + real-value-hints description of it, and — only when the
structure actually changed — runs a three-agent LangGraph pipeline that regenerates the app's own
SQL queries to match.

## Architecture

```
React dashboard  →  FastAPI  →  SQL Server (deterministic evidence)
                         │
                         └──→  OpenAI (OPENAI_MODEL)  (business rules + slippage rules +
                                          task prompt as the system message, investigation
                                          JSON as the user message)  →  delay-analysis description


Database Settings (UI)  →  POST /api/schema/refresh
                                │
                                ├──→  introspect live DB  →  schema.txt + hints.txt +
                                │                             structural fingerprint
                                │
                                └──→  fingerprint changed for a target? ──yes──→ SQL agent pipeline
                                          │                                          │
                                          no                                         ▼
                                          │                            generate (OpenAI, OPENAI_FAST_MODEL)
                                          ▼                                          │
                                   leave that target's                               ▼
                                   SQL file untouched                    verify (OpenAI) ──fail──┐
                                                                                │pass             │ retry, up to
                                                                                ▼                 │ SQL_AGENT_MAX_RETRIES
                                                                     validate (code, no LLM) ──fail┘
                                                                                │pass
                                                                                ▼
                                                                   back up old file, then write
                                                                   investigation.sql / slipped_wells.sql
```

The SQL layer computes every status/deadline/variance value. The LLM only explains the recorded
evidence — it is explicitly instructed not to invent a root cause, resource shortage, or
dependency that the evidence doesn't support, and never to guess a crew when none is recorded.

## Project structure

```
.
├── backend/                            FastAPI service
│   ├── .env                            Credentials + LLM settings (not committed)
│   ├── main.py                         FastAPI app entrypoint, CORS, router registration
│   ├── requirements.txt                Backend dependencies
│   ├── app/
│   │   ├── api/
│   │   │   ├── wells.py                GET /api/slipped-wells
│   │   │   ├── investigation.py        GET /api/well/{well_id}/investigation
│   │   │   ├── schema.py               GET/POST /api/db-config, POST /api/schema/refresh
│   │   │   └── sql_agent.py            POST /api/sql-agent/generate, GET /api/sql-agent/targets
│   │   ├── database/
│   │   │   └── connection.py           pyodbc connection; active DB name (.env or UI override)
│   │   ├── services/
│   │   │   ├── slipped_wells.py        Runs sql/slipped_wells.sql
│   │   │   ├── investigation.py        Runs sql/investigation.sql, builds well→activities→tasks JSON
│   │   │   ├── calculation.py          Runs sql/calculation.sql, derives dashboard KPI counts
│   │   │   ├── llm.py                  Shared OpenAI call + the delay-analysis answering agent
│   │   │   ├── console_log.py          Colored, per-stage terminal logging (rich) for the SQL pipeline
│   │   │   ├── schema_introspection.py Builds schema.txt / hints.txt / structural fingerprint
│   │   │   ├── sql_agent.py            SQL GENERATION agent (LLM) — pure function, one query per call
│   │   │   ├── sql_verifier_agent.py   SQL VERIFIER agent (LLM) — business-logic correctness check
│   │   │   ├── sql_validation_agent.py SQL VALIDATION agent (no LLM) — destructive-statement guard
│   │   │   └── sql_workflow.py         LangGraph orchestration: generate→verify→validate→write,
│   │   │                               retries, backups, fingerprint-triggered regeneration
│   │   ├── prompts/
│   │   │   └── prompt.py               Every agent's task prompt (delay analysis, SQL generation,
│   │   │                               SQL verification, SQL validation policy)
│   │   └── responses/
│   │       └── investigation.json      Generated per investigation (not committed)
│   ├── prompts/
│   │   ├── business_rules.md           Authoritative PDO / Al Tasnim business rules
│   │   ├── slippage.md                 How slippage/status/variance fields are derived
│   │   └── sql_examples.md             Few-shot SQL patterns the generation/verifier agents follow
│   ├── schema/                         Generated per DB (not committed): <db>_schema.txt,
│   │   │                               <db>_hints.txt, <db>_structure_fingerprint.txt,
│   │   │                               <db>_<target>_generated_from.txt
│   └── sql/
│       ├── slipped_wells.sql           Rig-on / rig-off / pegging / FLAF / hook-up slippage detection
│       ├── investigation.sql           Per-well evidence: milestones + all tasks
│       ├── calculation.sql             Dashboard KPI counts (total/live wells)
│       └── backups/                    Auto-created: previous SQL file, timestamped, before
│                                       each agent-driven overwrite (not committed)
│
├── frontend/                           React dashboard (Vite)
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx                    React entrypoint
│       ├── App.jsx                     Page layout, data loading, top-bar schema refresh
│       ├── api.js                      Backend API calls
│       ├── utils.js                    Date helpers
│       ├── index.css
│       └── components/
│           ├── KpiCards.jsx
│           ├── WellsTable.jsx          Slipped-well roster (click to select)
│           ├── WellDetail.jsx          Rig-on / rig-off / hook-up milestone cards
│           ├── InvestigationPanel.jsx  Ad-hoc "investigate a well" form + AI brief
│           ├── AnalysisMarkdown.jsx    Renders the LLM's markdown-formatted analysis
│           ├── DbSettingsPanel.jsx     Change the active database, trigger schema refresh
│           └── SqlRegenerationSummary.jsx  Shows what the SQL agent pipeline did per target
│
├── others/                             Local scratch/experiments — untracked, not part of the app
├── requirements.txt                    Convenience file: installs backend deps
└── .gitignore
```

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm (for the React frontend)
- Microsoft ODBC Driver 17 or 18 for SQL Server (used by `pyodbc`)
- Network access to the SQL Server instance holding the target database
- An [OpenAI](https://platform.openai.com) API key, to enable AI delay analysis and the SQL
  agent pipeline (optional — the dashboard and deterministic evidence queries work without it)

## Setup

**Backend:**

1. Create and activate a virtual environment at the project root:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   source .venv/bin/activate   # macOS/Linux
   ```

2. Install backend dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure `backend/.env`:

   ```
   DB_SERVER=your-server-host
   DB_PORT=1433
   DB_NAME=AlTasnimBI
   DB_USER=your-username
   DB_PASSWORD=your-password
   DB_DRIVER=ODBC Driver 17 for SQL Server
   DB_TRUST_SERVER_CERTIFICATE=yes
   DB_CONNECTION_TIMEOUT=30

   OPENAI_API_KEY=
   OPENAI_MODEL=gpt-4o-mini
   OPENAI_FAST_MODEL=gpt-4o-mini

   # Optional — SQL agent pipeline tuning, all have defaults:
   SQL_AGENT_MAX_RETRIES=3
   SQL_AGENT_TEMPERATURE=0.2
   SQL_VERIFIER_TEMPERATURE=0.1

   # Optional — shrink the introspected schema to only the schemas that matter:
   # SCHEMA_ALLOWED_SCHEMAS=well,dbo,ref,project
   # SCHEMA_EXCLUDED_TABLES=dbo.sysdiagrams
   # SCHEMA_EXCLUDED_COLUMNS=
   ```

   `DB_NAME` is the startup default; it can be changed at runtime from the dashboard's Database
   Settings panel without editing `.env` (see below) — the override is stored in
   `backend/app/database/active_db.json`, not committed.

   If `OPENAI_API_KEY` is missing, or `backend/prompts/business_rules.md` /
   `backend/prompts/slippage.md` is missing, the investigation still runs and
   `investigation.json` is still written — only the AI-generated explanation is skipped, and the
   API response's `analysis_error` field says why. The SQL agent pipeline fails the same way
   (reported per-target, without touching the existing SQL files) if it can't reach OpenAI.

**Frontend:**

```bash
cd frontend
npm install
```

## Running

**Backend (FastAPI):**

```bash
cd backend
uvicorn main:app --reload
```

Run it from inside `backend/` (not with `--app-dir backend` from the project root) —
`python-dotenv`'s frame-based lookup for `.env` doesn't reliably resolve when launched that way
from a different working directory.

Runs on `http://127.0.0.1:8000` by default. Key endpoints:

- `GET /api/slipped-wells` — wells currently slipped on rig-on, rig-off, or hook-up, or that
  have at least one delayed task. Each well carries `well_slippage_status`
  (`SLIPPED - RIG ON` / `SLIPPED - FLAF` / `SLIPPED - PEGGING` / `SLIPPED - RIG OFF` /
  `SLIPPED - HOOK-UP` / `NOT SLIPPED`), plus pegging/FLAF status and deadlines.
- `GET /api/well/{well_id}/investigation` — runs the full evidence query for one well, writes
  `backend/app/responses/investigation.json`, and returns `{ success, well_id, row_count,
  analysis, analysis_error, message }`.
- `GET /api/db-config` / `POST /api/db-config` — read or change the active database name.
- `POST /api/schema/refresh` — re-introspects the active database (writes `schema.txt` /
  `hints.txt` / a structural fingerprint), then automatically runs the SQL agent pipeline for any
  target (`investigation` or `slipped_wells`) whose schema fingerprint changed since it was last
  successfully generated. Can take a few minutes — see [SQL agent pipeline](#sql-agent-pipeline).
- `POST /api/sql-agent/generate` — manually trigger the same generate/verify/validate/write
  pipeline, optionally for specific targets (`{"targets": ["investigation"]}`; both by default).
- `GET /api/sql-agent/targets` — lists the valid SQL targets and what each one is for.

The backend allows cross-origin requests from `http://localhost:5173` (the Vite dev server) via
CORS middleware in `backend/main.py`.

**Frontend (React):**

```bash
cd frontend
npm run dev
```

Opens on `http://localhost:5173` by default. If the backend is not running on
`http://127.0.0.1:8000`, set `VITE_API_URL` before starting the dev server:

```bash
VITE_API_URL=http://your-backend-host:8000 npm run dev
```

The dashboard shows the slipped-well roster and a milestone detail view for whichever well is
selected. Investigating a well is a separate, ad-hoc action — enter any well ID in the
"Investigate a well" panel to run the evidence query and AI analysis for it. The top bar's
"⟳ Refresh Schema" button and the "⚙ Database" panel both trigger `POST /api/schema/refresh`;
the Database panel additionally lets you change which database is active before refreshing.

## AI delay analysis

Two documents plus a task prompt are combined into one system prompt for every investigation
(`app/services/llm.py`):

1. **`backend/prompts/business_rules.md`** — authoritative PDO / Al Tasnim definitions: which
   column means what, milestone deadlines, ownership and penalty rules, and the rule that an
   early actual date is good news, never an anomaly.
2. **`backend/prompts/slippage.md`** — how every status, deadline, and variance field in the
   evidence is derived, and the evidence hierarchy the AI must follow (well-level evidence
   first, then activity/task, then supporting detail like crew/quantity/productivity).
3. **`backend/app/prompts/prompt.py`** (`DELAY_ANALYSIS_PROMPT`) — the task instructions and
   required response format: a short well-level "why is it delayed" summary, followed by a
   mandatory, exhaustive line-by-line list of every delayed task and its assigned crew.

The investigation JSON (well → activities → tasks) is sent as the user message. The model is
instructed to cite the evidence for every claim, never infer a root cause, resource shortage, or
cross-activity dependency that isn't explicitly supported, never guess a crew that isn't
recorded, and to say plainly when the evidence doesn't establish a deeper cause.

## Schema-agnostic SQL: hints, fingerprints, and the agent pipeline

The app doesn't hardcode which database it talks to. Two pieces make that possible:

### Schema introspection (`schema_introspection.py`)

No LLM involved — this is pure database metadata read directly from `sys.*`/
`INFORMATION_SCHEMA` catalog views. Running `POST /api/schema/refresh` (or the dashboard's
"Refresh Schema" button) writes, per active database, into `backend/schema/`:

- **`<db>_schema.txt`** — every visible table, its columns (type, nullability, PK marker,
  correctly `[bracketed]` where the bare name would fail to parse — reserved keywords and
  non-identifier characters), declared foreign keys, and a warning on any table holding many
  rows per key (so a de-duplication step doesn't get skipped).
- **`<db>_hints.txt`** — one line per table: a small table's real rows verbatim (so a code and
  its description stay paired), or for a larger table, only the columns that turn out to hold a
  short list of distinct values (an id or free-text column is excluded by a cardinality check,
  not by guessing from its name).
- **`<db>_structure_fingerprint.txt`** — a hash of just the structural facts above (tables,
  columns, types, keys) — deliberately excluding row counts and sampled values, so a lookup
  table gaining one new value doesn't count as a schema change.

`SCHEMA_ALLOWED_SCHEMAS` / `SCHEMA_EXCLUDED_TABLES` / `SCHEMA_EXCLUDED_COLUMNS` (env vars, all
optional) narrow what gets included, and secret-looking columns (password/token/etc.) are always
excluded.

### SQL agent pipeline

Three independent agents (`sql_agent.py`, `sql_verifier_agent.py`, `sql_validation_agent.py`),
wired together by a LangGraph state machine in `sql_workflow.py`:

| Agent | File | LLM? | Job |
|---|---|---|---|
| Generation | `sql_agent.py` | yes (`OPENAI_FAST_MODEL`) | Writes one candidate query from schema + hints + business rules + slippage rules + `sql_examples.md` |
| Verifier | `sql_verifier_agent.py` | yes (`OPENAI_FAST_MODEL`) | Checks it for business-logic correctness — real columns, correct NULL/deadline handling, signed variance, required de-duplication |
| Validation | `sql_validation_agent.py` | no — plain code | Rejects anything containing `INSERT`/`UPDATE`/`DELETE`/DDL/temp tables/stacked statements, and enforces the exact `DECLARE @WellId` / `@Today` contract `investigation.sql` needs |

Generate → verify → validate, in that order; a failure at either check sends the query back to
generation with the specific rejection reason, up to `SQL_AGENT_MAX_RETRIES` attempts (shared
across both checks). Only once a query clears both gates is the existing SQL file backed up
(`backend/sql/backups/`) and atomically replaced. A run that exhausts its retries leaves the
current file untouched.

`generate_sql_if_schema_changed()` is what connects this to a schema refresh: each target
remembers the fingerprint its SQL was generated from (`<db>_<target>_generated_from.txt`), so
refreshing the schema only re-runs this (multi-call, multi-minute) pipeline for a target whose
structure actually changed — switching to a database with no prior successful generation always
counts as changed. Progress prints to the terminal via `console_log.py` (colored, per-stage
lines — LLM timing, generation, verify/validate verdicts, the final write).

`backend/prompts/sql_examples.md` is the few-shot reference both the generation and verifier
agents are shown: worked examples of the CASE-ladder milestone-status pattern, de-duplication via
`ROW_NUMBER()`, deriving a key from a coded string, and the required output contract per target —
not full files to copy verbatim, but the shapes and idioms to follow.

## Notes

- `backend/app/responses/investigation.json`, `backend/schema/`,
  `backend/app/database/active_db.json`, and `backend/sql/backups/` are generated at runtime and
  are git-ignored.
- `backend/.env` contains sensitive connection/API-key details and is git-ignored.
- `frontend/node_modules/` and `frontend/dist/` are git-ignored.
- `others/` is untracked and not part of the shipped application.
