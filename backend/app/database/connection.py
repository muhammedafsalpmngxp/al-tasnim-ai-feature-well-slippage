import os
import struct
from datetime import datetime, timedelta, timezone

import pyodbc

from dotenv import load_dotenv


load_dotenv()


# SQL_SS_TIMESTAMPOFFSET — pyodbc has no built-in handler, so reading a
# `datetimeoffset` column raises "ODBC SQL type -155 is not yet supported".
# The full evidence projection selects such columns (task_daily.time_stamp),
# so decode the 20-byte struct the driver hands back.
SQL_SS_TIMESTAMPOFFSET = -155


def _decode_datetimeoffset(value):

    if value is None:
        return None

    (
        year, month, day, hour, minute, second,
        nanoseconds, offset_hours, offset_minutes
    ) = struct.unpack("<6hI2h", value)

    return datetime(
        year, month, day, hour, minute, second,
        nanoseconds // 1000,
        timezone(timedelta(hours=offset_hours, minutes=offset_minutes))
    )


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

    connection = pyodbc.connect(
        connection_string
    )

    connection.add_output_converter(
        SQL_SS_TIMESTAMPOFFSET,
        _decode_datetimeoffset
    )

    return connection
