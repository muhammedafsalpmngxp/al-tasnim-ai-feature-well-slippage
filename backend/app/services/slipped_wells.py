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

    cursor = connection.cursor()

    try:
        cursor.execute(query)

        if cursor.description is None:
            raise ValueError(
                "slipped_wells.sql did not return a result set."
            )

        columns = [
            column[0]
            for column in cursor.description
        ]

        df = pd.DataFrame.from_records(
            cursor.fetchall(),
            columns=columns,
        )
    finally:
        cursor.close()

    return df