# Well Delay AI (Al-Tasnim)

Well-slippage monitoring for drilling operations. The backend flags wells whose
rig-on/rig-off dates have slipped past their expected dates, and produces a
deterministic SQL "evidence layer" for a single well's task-level schedule
status. The frontend is a Streamlit dashboard for browsing slipped wells and
triggering a per-well investigation.

LLM-based analysis on top of the investigation evidence is planned but not
yet implemented.

## Project structure

```
.
├── backend/                   FastAPI service
│   ├── .env                   Database credentials (not committed)
│   ├── main.py                FastAPI app entrypoint
│   ├── requirements.txt       Backend dependencies
│   ├── script.py              Standalone SQL Server schema/data inventory tool
│   ├── database_inventory.txt Output of script.py (not committed)
│   ├── app/
│   │   ├── api/               Route handlers (wells, investigation)
│   │   ├── database/          DB connection helper
│   │   ├── services/          Query execution + data cleaning
│   │   └── responses/         investigation.json output (not committed)
│   └── sql/                    Raw SQL used by the services
│
├── frontend/                   Streamlit dashboard
│   ├── dashboard.py
│   └── requirements.txt        Frontend dependencies
│
├── requirements.txt             Convenience file: installs backend + frontend
└── .gitignore
```

## Prerequisites

- Python 3.11+
- Microsoft ODBC Driver 17 or 18 for SQL Server (used by `pyodbc`)
- Network access to the SQL Server instance holding the `AlTasnimBI` database

## Setup

1. Create and activate a virtual environment at the project root:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   source .venv/bin/activate   # macOS/Linux
   ```

2. Install dependencies (backend + frontend):

   ```bash
   pip install -r requirements.txt
   ```

   Or install just one side:

   ```bash
   pip install -r backend/requirements.txt
   pip install -r frontend/requirements.txt
   ```

3. Configure the backend database connection in `backend/.env`:

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

**Backend (FastAPI):**

```bash
cd backend
uvicorn main:app --reload
```

Runs on `http://127.0.0.1:8000` by default. Key endpoints:

- `GET /api/slipped-wells` — list wells with slipped rig-on/rig-off dates
- `GET /api/well/{well_id}/investigation` — run the SQL evidence query for one
  well and write the result to `backend/app/responses/investigation.json`

**Frontend (Streamlit dashboard):**

```bash
cd frontend
streamlit run dashboard.py
```

Opens in your browser (default `http://localhost:8501`). If the backend is
not running on `http://127.0.0.1:8000`, set `API_URL` before launching:

```bash
API_URL=http://your-backend-host:8000 streamlit run dashboard.py
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
