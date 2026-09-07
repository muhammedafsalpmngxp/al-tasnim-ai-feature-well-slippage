import os

import pyodbc

from dotenv import load_dotenv


load_dotenv()


def get_connection():

    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_NAME")
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
