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
#
# well
# └── projects[]           grouped by (project_id, project_type)
#     └── wbs[]             grouped by (wbs_code, wbs_name)
#         └── activities[]  grouped by (activity_id, activity_code, activity)
#             └── tasks[]   one entry per delayed/at-risk task row
#
# Several of the fields below are not yet projected by
# investigation.sql's final SELECT (task_code, project_id, wbs_code,
# wbs_name, crew_type_id, crew_id, emp_id, data_employees,
# daily_employee_ids, daily_equipment_ids, quantity_source,
# observed_quantity, calculated_remaining_quantity,
# current_productivity_qty_per_hour, productivity_source,
# start_status, start_variance_days). Using .get() means those
# arrive as null today rather than raising — they will populate
# once the SQL projection is widened to include them.
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


def _task_from_record(record):

    return {

        "task_id": record.get("task_id"),
        "task_code": record.get("task_code"),

        "schedule": {
            "target_start": record.get("target_start"),
            "target_end": record.get("target_end"),
            "actual_start": record.get("actual_start"),
            "actual_end": record.get("actual_end"),
            "start_status": record.get("start_status"),
            "end_status": record.get("end_status"),
            "start_variance_days": record.get("start_variance_days"),
            "end_variance_days": record.get("delay_days")
        },

        "execution": {
            "progress_percent": record.get("progress_percent"),
            "completed": record.get("completed"),
            "execution_status": record.get("execution_status"),
            "schedule_risk": record.get("schedule_risk")
        },

        "crew": {

            # The SQL currently exposes only the merged value
            # (COALESCE(master_crew_code, planned_crew)) as "crew".
            # Placed under master_crew_code as the best available
            # approximation until the two are selected separately.
            "planned_crew": None,
            "master_crew_code": record.get("crew"),

            "crew_type_id": record.get("crew_type_id"),
            "crew_id": record.get("crew_id")
        },

        "resources": {
            "emp_id": record.get("emp_id"),
            "data_employees": record.get("data_employees"),
            "daily_employee_ids": record.get("daily_employee_ids"),
            "daily_equipment_ids": record.get("daily_equipment_ids")
        },

        "quantity": {
            "quantity_source": record.get("quantity_source"),
            "observed_quantity": record.get("observed_quantity"),
            "calculated_remaining_quantity":
                record.get("calculated_remaining_quantity")
        },

        "productivity": {
            "current_productivity_qty_per_hour":
                record.get("current_productivity_qty_per_hour"),
            "productivity_source": record.get("productivity_source"),
            "productivity_data_status": record.get("productivity_status")
        },

        "data_quality": {
            "has_data_quality_issue": record.get("has_data_quality_issue")
        }
    }


def _group_into_projects(records):

    """
    Fold the flat task rows into project -> wbs -> activity -> task.
    Dicts are used as ordered, de-duplicating buckets while grouping,
    then flattened into arrays for the final JSON.
    """

    projects = {}

    for record in records:

        project_key = (
            record.get("project_id"),
            record.get("project_type")
        )

        project = projects.setdefault(
            project_key,
            {
                "project_id": record.get("project_id"),
                "project_type": record.get("project_type"),
                "wbs": {}
            }
        )

        wbs_key = (
            record.get("wbs_code"),
            record.get("wbs_name")
        )

        wbs = project["wbs"].setdefault(
            wbs_key,
            {
                "wbs_code": record.get("wbs_code"),
                "wbs_name": record.get("wbs_name"),
                "activities": {}
            }
        )

        activity_key = (
            record.get("activity_id"),
            record.get("activity_code"),
            record.get("activity")
        )

        activity = wbs["activities"].setdefault(
            activity_key,
            {
                "activity_id": record.get("activity_id"),
                "activity_code": record.get("activity_code"),
                "activity": record.get("activity"),
                "tasks": []
            }
        )

        activity["tasks"].append(
            _task_from_record(record)
        )

    result = []

    for project in projects.values():

        project["wbs"] = list(project["wbs"].values())

        for wbs in project["wbs"]:

            wbs["activities"] = list(wbs["activities"].values())

        result.append(project)

    return result


def build_investigation_response(
    records,
    well_id: int
):

    """
    Build the well -> projects -> wbs -> activities -> tasks
    hierarchy. Well and milestone values repeat on every row, so
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

    well["milestones"] = {
        field: first_row.get(field)
        for field in MILESTONE_FIELDS
    }

    has_issue = first_row.get("has_data_quality_issue")

    well["data_quality"] = {

        "has_issue":
            bool(has_issue) if has_issue is not None else None,

        "schedule_evidence_level":
            first_row.get("schedule_evidence_level"),

        "data_evidence_level":
            first_row.get("data_evidence_level")
    }

    well["projects"] = _group_into_projects(records)

    return {
        "well": well
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
