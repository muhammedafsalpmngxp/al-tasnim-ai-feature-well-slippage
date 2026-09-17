import os
import json

from pathlib import Path

import pyodbc

from dotenv import load_dotenv


load_dotenv()


ACTIVE_DB_FILE = Path(__file__).resolve().parent / "active_db.json"


def get_active_db_name():
    """Return the DB name to connect to: a UI-set override if present, else .env."""

    if ACTIVE_DB_FILE.exists():

        try:
            data = json.loads(ACTIVE_DB_FILE.read_text(encoding="utf-8"))
            name = data.get("db_name")

            if name:
                return name

        except (OSError, ValueError):
            pass

    return os.getenv("DB_NAME")


def set_active_db_name(db_name):
    """Persist a UI-selected DB name so future connections use it."""

    ACTIVE_DB_FILE.write_text(
        json.dumps({"db_name": db_name}),
        encoding="utf-8"
    )


def get_connection():

    server = os.getenv("DB_SERVER")
    database = get_active_db_name()
    username = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    driver = os.getenv(
        "DB_DRIVER",
        "ODBC Driver 17 for SQL Server"
    )
    timeout = int(os.getenv("DB_CONNECTION_TIMEOUT", "30"))

    missing = []

    if not server:
        missing.append("DB_SERVER")

    if not database:
        missing.append("DB_NAME")

    if not username:
        missing.append("DB_USER")

    if not password:
        missing.append("DB_PASSWORD")

    if missing:

        raise ValueError(
            "Missing database environment variables: "
            + ", ".join(missing)
        )

    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
        f"Connection Timeout={timeout};"
    )

    return pyodbc.connect(
        connection_string
    )
