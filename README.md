# Well Delay AI (Al-Tasnim)

Well-slippage monitoring and AI-assisted delay analysis for drilling operations.

The backend flags wells that have slipped on rig-on, rig-off, or hook-up, and produces a
deterministic SQL "evidence layer" — well milestones plus every task under the well — for a
single well. That evidence is then handed to an LLM (via Groq), constrained by an authoritative
business-rules document, to produce a short, evidence-cited explanation of why the well is
delayed. The frontend is a React dashboard for browsing slipped wells and running an
investigation.

## Architecture

```
React dashboard  →  FastAPI  →  SQL Server (deterministic evidence)
                         │
                         └──→  Groq LLM  (business rules + slippage rules + task prompt
                                          as the system message, investigation JSON as
                                          the user message)  →  delay-analysis description
```

The SQL layer computes every status/deadline/variance value. The LLM only explains the
recorded evidence — it is explicitly instructed not to invent a root cause, resource shortage,
or dependency that the evidence doesn't support.

## Project structure

```
.
├── backend/                        FastAPI service
│   ├── .env                        Credentials + LLM settings (not committed)
│   ├── main.py                     FastAPI app entrypoint, CORS
│   ├── requirements.txt            Backend dependencies
│   ├── database_inventory.txt      Schema/sample-data dump (not committed)
│   ├── app/
│   │   ├── api/
│   │   │   ├── wells.py            GET /api/slipped-wells
│   │   │   └── investigation.py    GET /api/well/{well_id}/investigation
│   │   ├── database/
│   │   │   └── connection.py       pyodbc connection from .env
│   │   ├── services/
│   │   │   ├── slipped_wells.py    Runs sql/slipped_wells.sql
│   │   │   ├── investigation.py    Runs sql/investigation.sql, builds well→activities→tasks JSON
│   │   │   └── llm.py              Assembles the system prompt, calls Groq
│   │   ├── prompts/
│   │   │   └── prompt.py           Task prompt (Python) for the delay analysis
│   │   └── responses/
│   │       └── investigation.json  Generated per investigation (not committed)
│   ├── prompts/
│   │   ├── business_rules.md       Authoritative PDO / Al Tasnim business rules
│   │   └── slippage.md             How slippage/status/variance fields are derived
│   └── sql/
│       ├── slipped_wells.sql       Rig-on / rig-off / hook-up / task slippage detection
│       └── investigation.sql       Per-well evidence: milestones + all tasks
│
├── frontend/                       React dashboard (Vite)
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx                React entrypoint
│       ├── App.jsx                 Page layout + data loading
│       ├── api.js                  Backend API calls
│       ├── utils.js                Date helpers
│       ├── index.css
│       └── components/
│           ├── KpiCards.jsx
│           ├── WellsTable.jsx      Slipped-well roster (click to select)
│           ├── WellDetail.jsx      Rig-on / rig-off / hook-up milestone cards
│           ├── InvestigationPanel.jsx  Ad-hoc "investigate a well" form + AI brief
│           └── AnalysisMarkdown.jsx    Renders the LLM's markdown-formatted analysis
│
├── others/                         Local scratch/experiments — untracked, not part of the app
├── requirements.txt                 Convenience file: installs backend deps
└── .gitignore
```

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm (for the React frontend)
- Microsoft ODBC Driver 17 or 18 for SQL Server (used by `pyodbc`)
- Network access to the SQL Server instance holding the `AlTasnimBI` database
- A [Groq](https://groq.com) API key, to enable the AI delay-analysis feature (optional —
  everything else works without it)

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
   DB_CONNECTION_TIMEOUT=30

   GROQ_API_KEY=your-groq-api-key
   LLM_MODEL=openai/gpt-oss-120b
   ```

   `GROK_KEY` is also accepted as an alias for `GROQ_API_KEY`, if that's what your `.env`
   already uses. If neither is set, or the file `backend/prompts/business_rules.md` or
   `backend/prompts/slippage.md` is missing, the investigation still runs and
   `investigation.json` is still written — only the AI-generated explanation is skipped, and
   the API response's `analysis_error` field says why.

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
  (`SLIPPED - RIG ON` / `SLIPPED - RIG OFF` / `SLIPPED - HOOK-UP` / `SLIPPED - TASK` /
  `NOT SLIPPED`), plus pegging/FLAF status and deadlines, and task-count summaries.
- `GET /api/well/{well_id}/investigation` — runs the full evidence query for one well, writes
  `backend/app/responses/investigation.json`, and returns `{ success, well_id, row_count,
  analysis, analysis_error, message }`. `row_count` is the number of task rows returned for the
  well (all tasks, not only delayed ones); `analysis` is the AI-generated delay explanation, or
  `null` with `analysis_error` set if the LLM call wasn't possible.

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
"Investigate a well" panel to run the evidence query and AI analysis for it, independent of
which well is selected in the roster. The AI's response is rendered as formatted text
(headings, lists, bold, inline code) by `AnalysisMarkdown.jsx`.

## AI delay analysis

Three documents are combined into one system prompt for every investigation
(`app/services/llm.py`):

1. **`backend/prompts/business_rules.md`** — authoritative PDO / Al Tasnim definitions: which
   column means what, milestone deadlines, ownership and penalty rules, and the rule that an
   early actual date is good news, never an anomaly.
2. **`backend/prompts/slippage.md`** — how every status, deadline, and variance field in the
   evidence is derived, and the evidence hierarchy the AI must follow (well-level evidence
   first, then activity/task, then supporting detail like crew/quantity/productivity).
3. **`backend/app/prompts/prompt.py`** — the task instructions and required response format.

The investigation JSON (well → activities → tasks) is sent as the user message. The model is
instructed to cite the evidence for every claim, never infer a root cause, resource shortage, or
cross-activity dependency that isn't explicitly supported, and to say plainly when the evidence
doesn't establish a deeper cause.

## Database inventory tool

A schema/sample-data inventory script exists in `others/script.py` (not part of the deployed
app). `others/` is untracked scratch/experiment content and isn't documented further here.

## Notes

- `backend/app/responses/investigation.json` is generated at runtime and is git-ignored.
- `backend/.env` and `backend/database_inventory.txt` contain sensitive connection details and
  are git-ignored.
- `frontend/node_modules/` and `frontend/dist/` are git-ignored.
- `others/` is untracked and not part of the shipped application.
