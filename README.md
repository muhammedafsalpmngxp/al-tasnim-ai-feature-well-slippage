# Well Delay AI (Al-Tasnim)

Well-slippage monitoring for drilling operations. The backend flags wells whose
rig-on/rig-off dates have slipped past their expected dates, and produces a
deterministic SQL "evidence layer" for a single well's task-level schedule
status. The frontend is a React dashboard for browsing slipped wells and
triggering a per-well investigation.

LLM-based analysis on top of the investigation evidence is planned but not
yet implemented.

## Project structure

```
.
├── backend/                   FastAPI service
│   ├── .env                   Credentials + LLM settings (not committed)
│   ├── main.py                FastAPI app entrypoint
│   ├── requirements.txt       Backend dependencies
│   ├── script.py              Standalone SQL Server schema/data inventory tool
│   ├── database_inventory.txt Output of script.py (not committed)
│   ├── app/
│   │   ├── api/               Route handlers (wells, investigation)
│   │   ├── database/          DB connection helper
│   │   ├── services/          Query execution, data cleaning, LLM analysis
│   │   ├── prompts/
│   │   │   └── prompt.py      Task prompt for the delay explanation
│   │   └── responses/         investigation.json output (not committed)
│   ├── prompts/
│   │   └── business_rules.md  Authoritative PDO / Al Tasnim business rules
│   └── sql/                    Raw SQL used by the services
│
├── frontend/                   React dashboard (Vite)
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx            React entrypoint
│       ├── App.jsx             Page layout + data loading
│       ├── api.js              Backend API calls
│       ├── utils.js            Date helpers
│       ├── index.css
│       └── components/
│           ├── KpiCards.jsx
│           ├── WellsTable.jsx
│           ├── WellDetail.jsx
│           └── InvestigationPanel.jsx
│
├── requirements.txt             Convenience file: installs backend deps
└── .gitignore
```

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm (for the React frontend)
- Microsoft ODBC Driver 17 or 18 for SQL Server (used by `pyodbc`)
- Network access to the SQL Server instance holding the `AlTasnimBI` database

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

   GROK_KEY=your-groq-api-key
   LLM_MODEL=openai/gpt-oss-120b
   ```

   `GROK_KEY` and `LLM_MODEL` drive the delay analysis shown after checking a
   well. If they are missing the investigation still runs and the JSON is still
   written — only the written explanation is skipped.

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

Run it from inside `backend/` (not with `--app-dir backend` from the project
root) — `python-dotenv` resolves `.env` relative to the running process in a
way that doesn't reliably locate `backend/.env` when launched via `--app-dir`
from a different working directory.

Runs on `http://127.0.0.1:8000` by default. Key endpoints:

- `GET /api/slipped-wells` — list wells with slipped rig-on/rig-off dates
- `GET /api/well/{well_id}/investigation` — run the SQL evidence query for one
  well and write the result to `backend/app/responses/investigation.json`

The backend allows cross-origin requests from `http://localhost:5173` (the
Vite dev server) via CORS middleware in `backend/main.py`.

**Frontend (React):**

```bash
cd frontend
npm run dev
```

Opens on `http://localhost:5173` by default. If the backend is not running on
`http://127.0.0.1:8000`, set `VITE_API_URL` before starting the dev server
(e.g. in a `frontend/.env` file or inline):

```bash
VITE_API_URL=http://your-backend-host:8000 npm run dev
```

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
- `frontend/node_modules/` and `frontend/dist/` are git-ignored.
