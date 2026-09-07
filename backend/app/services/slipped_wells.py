from pathlib import Path

import pandas as pd


# ============================================================
# LOAD SQL
# ============================================================

SQL_FILE = (
    Path(__file__)
    .resolve()
    .parents[2]
    / "sql"
    / "slipped_wells.sql"
)


def get_slipped_wells(connection):

    query = SQL_FILE.read_text(
        encoding="utf-8"
    )

    df = pd.read_sql(
        query,
        connection
    )

    return df