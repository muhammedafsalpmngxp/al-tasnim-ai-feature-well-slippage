from pathlib import Path
import json
import math
import re
from tempfile import NamedTemporaryFile


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

SQL_FILE = BASE_DIR / "sql" / "investigation.sql"

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
    # Booleans must be preserved before the numeric branch:
    # bool defines __float__, so it would become 1.0 / 0.0.
    # --------------------------------------------------------

    if isinstance(value, bool):

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
# JSON SHAPE
# ============================================================

WELL_FIELDS = [
    "well_id",
    "ex_rig_on_date",
    "rig_on_date",
    "ex_rig_off_date",
    "rig_off_date",
    "pegged_date",
    "flaf_issue_date",
    "eng_completion_date",
    "well_progress",
    "flowline_progress"
]

MILESTONE_FIELDS = [
    "pegging_status",
    "flaf_status",
    "construction_status",
    "hookup_status"
]

ACTIVITY_FIELDS = [
    "task_id",
    "project_type",
    "activity_id",
    "activity_code",
    "activity",
    "crew",
    "progress_percent",
    "completed",
    "target_start",
    "target_end",
    "actual_start",
    "actual_end",
    "remaining_duration",
    "end_status",
    "delay_days",
    "execution_status",
    "schedule_risk",
    "target_achievability",
    "productivity_status",
    "resource_status"
]


def build_investigation_response(
    records,
    well_id: int
):

    """
    Group the flat query rows into well / milestone / activity
    sections. Well and milestone values repeat on every row, so
    the first row carries them.
    """

    first_row = records[0] if records else {}

    well = {
        field: first_row.get(field)
        for field in WELL_FIELDS
    }

    # The query returns nothing when a well has no delayed
    # activities, so keep the requested well_id addressable.
    well["well_id"] = first_row.get("well_id", well_id)

    milestones = {
        field: first_row.get(field)
        for field in MILESTONE_FIELDS
    }

    delayed_activities = [
        {
            field: record.get(field)
            for field in ACTIVITY_FIELDS
        }
        for record in records
    ]

    has_issue = first_row.get("has_data_quality_issue")

    data_quality = {

        "has_issue":
            bool(has_issue) if has_issue is not None else None,

        "schedule_evidence_level":
            first_row.get("schedule_evidence_level"),

        "data_evidence_level":
            first_row.get("data_evidence_level")
    }

    return {
        "well": well,
        "milestones": milestones,
        "delayed_activities": delayed_activities,
        "data_quality": data_quality
    }


# ============================================================
# UPDATE SINGLE JSON FILE
# ============================================================

def update_investigation_json(
    records,
    well_id: int
):

    # --------------------------------------------------------
    # JSON response
    # --------------------------------------------------------

    response = build_investigation_response(
        records,
        well_id
    )


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
        json.dump(response, file, indent=4, ensure_ascii=False, allow_nan=False)
        temporary_file = Path(file.name)

    temporary_file.replace(JSON_FILE)


    # --------------------------------------------------------
    # Log
    # --------------------------------------------------------

    print(
        f"Investigation JSON updated: {JSON_FILE}"
    )


    return response
