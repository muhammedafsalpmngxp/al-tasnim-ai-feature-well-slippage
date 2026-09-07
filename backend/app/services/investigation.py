from pathlib import Path
import json
import math
import re
from tempfile import NamedTemporaryFile

import pandas as pd


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

SQL_FILE = BASE_DIR / "sql" / "investigation.sql"

MILESTONES_SQL_FILE = BASE_DIR / "sql" / "well_milestones.sql"

JSON_DIR = BASE_DIR / "app" / "responses"

JSON_FILE = JSON_DIR / "investigation.json"


# ============================================================
# READ INVESTIGATION SQL
# ============================================================

def load_investigation_sql():

    if not SQL_FILE.exists():

        raise FileNotFoundError(
            f"Investigation SQL file not found: {SQL_FILE}"
        )

    query = SQL_FILE.read_text(
        encoding="utf-8"
    )

    if not query.strip():

        raise ValueError(
            "Investigation SQL file is empty."
        )

    return query


# ============================================================
# PREPARE SQL FOR SELECTED WELL
# ============================================================

def prepare_investigation_sql(query):

    """
    Replace the hardcoded @WellId value with
    a parameter placeholder.

    Example:

        DECLARE @WellId INT = 33151;

    becomes:

        DECLARE @WellId INT = ?;
    """

    pattern = (
        r"DECLARE\s+@WellId\s+INT\s*=\s*"
        r"[^;]+;"
    )

    replacement = (
        "DECLARE @WellId INT = ?;"
    )

    updated_query, count = re.subn(
        pattern,
        replacement,
        query,
        count=1,
        flags=re.IGNORECASE
    )

    if count == 0:

        raise ValueError(
            "Could not find "
            "'DECLARE @WellId INT = ...;' "
            "in investigation.sql"
        )

    return updated_query


# ============================================================
# CLEAN DATABASE VALUES FOR JSON
# ============================================================

def clean_value(value):

    if value is None:
        return None

    if isinstance(value, dict):
        return {str(key): clean_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [clean_value(item) for item in value]

    # --------------------------------------------------------
    # datetime / date / time / datetimeoffset-like objects
    # --------------------------------------------------------

    if hasattr(value, "isoformat"):

        return value.isoformat()

    # --------------------------------------------------------
    # Bytes
    # --------------------------------------------------------

    if isinstance(value, bytes):

        try:

            return value.decode("utf-8")

        except UnicodeDecodeError:

            try:

                return value.decode("utf-16")

            except UnicodeDecodeError:

                return value.hex()

    # --------------------------------------------------------
    # Integers stay integers — IDs must not become 14.0
    # --------------------------------------------------------

    if isinstance(value, (bool, int)):

        return value

    # --------------------------------------------------------
    # Decimal and similar numeric objects
    # --------------------------------------------------------

    if hasattr(value, "__float__") and not isinstance(value, str):

        try:

            numeric_value = float(value)

            if math.isnan(numeric_value):

                return None

            if math.isinf(numeric_value):

                return None

            return numeric_value

        except (TypeError, ValueError):

            pass

    # --------------------------------------------------------
    # Normal JSON-compatible values
    # --------------------------------------------------------

    return value


# ============================================================
# DEBUG RESULT COLUMN TYPES
# ============================================================

def print_result_columns(cursor):

    """
    Print column index, name and ODBC type.

    Useful for identifying unsupported SQL Server
    datetimeoffset columns.
    """

    print()
    print("=" * 80)
    print("INVESTIGATION RESULT COLUMNS")
    print("=" * 80)

    for index, column in enumerate(cursor.description):

        column_name = column[0]
        column_type = column[1]

        print(
            f"Column {index} | "
            f"Name: {column_name} | "
            f"ODBC Type: {column_type}"
        )

    print("=" * 80)
    print()


# ============================================================
# EXECUTE INVESTIGATION SQL
# ============================================================

def get_investigation_data(
    connection,
    well_id: int
):

    # --------------------------------------------------------
    # Load SQL
    # --------------------------------------------------------

    original_query = load_investigation_sql()


    # --------------------------------------------------------
    # Replace @WellId declaration
    # --------------------------------------------------------

    query = prepare_investigation_sql(
        original_query
    )


    # --------------------------------------------------------
    # Print useful information
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print(
        f"Starting investigation for Well {well_id}"
    )
    print("=" * 80)

    print(
        f"Running investigation SQL for Well ID: {well_id}"
    )


    # --------------------------------------------------------
    # Create cursor
    # --------------------------------------------------------

    cursor = connection.cursor()


    try:

        # ----------------------------------------------------
        # Execute READ-ONLY SQL
        # ----------------------------------------------------

        cursor.execute(
            query,
            well_id
        )


        print(
            "Investigation SQL executed successfully."
        )


        # ----------------------------------------------------
        # Check result set
        # ----------------------------------------------------

        if cursor.description is None:

            raise ValueError(
                "Investigation SQL did not return a result set."
            )


        # ----------------------------------------------------
        # DEBUG COLUMN INFORMATION
        # ----------------------------------------------------

        print_result_columns(cursor)


        # ----------------------------------------------------
        # Get column names
        # ----------------------------------------------------

        columns = [
            column[0]
            for column in cursor.description
        ]


        # ----------------------------------------------------
        # Fetch result
        # ----------------------------------------------------

        print(
            "Fetching investigation result..."
        )

        rows = cursor.fetchall()


        print(
            f"Database fetch completed. "
            f"Rows fetched: {len(rows)}"
        )


        # ----------------------------------------------------
        # Convert rows to dictionaries
        # ----------------------------------------------------

        records = []

        for row in rows:

            record = {}

            for index, column in enumerate(columns):

                record[column] = clean_value(
                    row[index]
                )

            records.append(record)


        # ----------------------------------------------------
        # Final result
        # ----------------------------------------------------

        print(
            f"Investigation query returned "
            f"{len(records)} rows for Well {well_id}"
        )

        return records


    finally:

        cursor.close()


# ============================================================
# WELL MILESTONE HEADER (authoritative, task-independent)
# ============================================================

class WellNotFoundError(Exception):
    """Raised when a well_id has no live (non-completed) record."""


def get_well_milestones(
    connection,
    well_id: int
):

    if not MILESTONES_SQL_FILE.exists():

        raise FileNotFoundError(
            f"Well milestones SQL file not found: {MILESTONES_SQL_FILE}"
        )

    query = MILESTONES_SQL_FILE.read_text(
        encoding="utf-8"
    )

    cursor = connection.cursor()

    try:

        cursor.execute(
            query,
            well_id
        )

        if cursor.description is None:

            raise ValueError(
                "Well milestones SQL did not return a result set."
            )

        columns = [
            column[0]
            for column in cursor.description
        ]

        row = cursor.fetchone()

        if row is None:

            raise WellNotFoundError(
                f"Well {well_id} was not found or is already completed."
            )

        return {
            column: row[index]
            for index, column in enumerate(columns)
        }

    finally:

        cursor.close()


# ============================================================
# WELL RISK ASSESSMENT (orchestrator)
# ============================================================

def get_well_risk_assessment(
    connection,
    well_id: int
):

    from app.services.risk import build_well_risk_summary

    well_row = get_well_milestones(
        connection,
        well_id
    )

    records = get_investigation_data(
        connection,
        well_id
    )

    task_df = pd.DataFrame(records)

    return build_well_risk_summary(
        well_row,
        task_df
    )


# ============================================================
# UPDATE SINGLE JSON FILE
# ============================================================

def update_investigation_json(
    summary
):

    # --------------------------------------------------------
    # Write / overwrite same JSON file
    # --------------------------------------------------------

    JSON_DIR.mkdir(parents=True, exist_ok=True)

    # Write then replace so readers never see a partial JSON file.
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=JSON_DIR,
        prefix="investigation-",
        suffix=".tmp",
        delete=False
    ) as file:
        json.dump(summary, file, indent=4, ensure_ascii=False, allow_nan=False)
        temporary_file = Path(file.name)

    temporary_file.replace(JSON_FILE)


    # --------------------------------------------------------
    # Log
    # --------------------------------------------------------

    print(
        f"Investigation JSON updated: {JSON_FILE}"
    )


    return summary
