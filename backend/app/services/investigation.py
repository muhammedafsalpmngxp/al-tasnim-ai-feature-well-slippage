from pathlib import Path
import json
import logging
import math
import re
from tempfile import NamedTemporaryFile


logger = logging.getLogger(__name__)


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

SQL_FILE = BASE_DIR / "sql" / "investigation.sql"
JSON_DIR = BASE_DIR / "app" / "responses"
JSON_FILE = JSON_DIR / "investigation.json"


# ============================================================
# LOAD INVESTIGATION SQL
# ============================================================

def load_investigation_sql() -> str:
    if not SQL_FILE.exists():
        raise FileNotFoundError(
            f"Investigation SQL file not found: {SQL_FILE}"
        )

    query = SQL_FILE.read_text(encoding="utf-8")

    if not query.strip():
        raise ValueError("Investigation SQL file is empty.")

    return query


def prepare_investigation_sql(query: str, well_id: int) -> str:
    """
    Use the selected well_id at runtime.

    investigation.sql contains:
        DECLARE @WellId INT = ...;

    The value is replaced for the selected well.
    """

    if not isinstance(well_id, int) or well_id <= 0:
        raise ValueError("well_id must be a positive integer.")

    pattern = (
        r"DECLARE\s+@WellId\s+INT\s*=\s*"
        r"[^;]+;"
    )

    replacement = f"DECLARE @WellId INT = {well_id};"

    updated_query, count = re.subn(
        pattern,
        replacement,
        query,
        count=1,
        flags=re.IGNORECASE,
    )

    if count == 0:
        raise ValueError(
            "investigation.sql must contain "
            "'DECLARE @WellId INT = ...;'"
        )

    return updated_query


# ============================================================
# CONVERT SQL SERVER VALUES TO JSON-SAFE VALUES
# ============================================================

def clean_value(value):
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()

    if isinstance(value, bool):
        return value

    if hasattr(value, "__float__") and not isinstance(value, str):
        try:
            number = float(value)

            if math.isnan(number) or math.isinf(number):
                return None

            return number
        except (TypeError, ValueError):
            pass

    return value


# ============================================================
# EXECUTE INVESTIGATION SQL
# ============================================================

def get_investigation_data(connection, well_id: int):
    query = prepare_investigation_sql(
        load_investigation_sql(),
        well_id,
    )

    cursor = connection.cursor()

    try:
        # READ-ONLY investigation SQL.
        cursor.execute(query)

        if cursor.description is None:
            raise ValueError(
                "investigation.sql did not return a result set."
            )

        columns = [
            column[0]
            for column in cursor.description
        ]

        rows = cursor.fetchall()

        records = []

        for row in rows:
            records.append(
                {
                    column: clean_value(row[index])
                    for index, column in enumerate(columns)
                }
            )

        return records

    finally:
        cursor.close()


# ============================================================
# BUILD JSON
#
# SQL is the source of truth for the returned columns.
# Python only creates the useful hierarchy:
#
# well
#   -> activities
#       -> tasks
#
# No duplicate column lists are maintained here.
# No data-quality fields are added.
# No WBS master fields are added.
# ============================================================

def build_investigation_response(
    records,
    well_id: int,
):
    if not records:
        return {
            "well": {
                "well_id": well_id,
                "activities": [],
            }
        }

    first = records[0]

    # Well-level values are repeated across task rows,
    # so take them from the first row.
    well = {
        "well_id": first.get("well_id", well_id),
        "project_id": first.get("project_id"),
        "project_code": first.get("project_code"),
        "project_name": first.get("project_name"),

        "ex_rig_on_date": first.get("ex_rig_on_date"),
        "rig_on_date": first.get("rig_on_date"),

        "ex_rig_off_date": first.get("ex_rig_off_date"),
        "rig_off_date": first.get("rig_off_date"),

        "eng_completion_date": first.get(
            "eng_completion_date"
        ),

        "well_progress_raw": first.get(
            "well_progress_raw"
        ),
        "flowline_const_progress": first.get(
            "flowline_const_progress"
        ),

        "milestones": {
            "pegged_date": first.get("pegged_date"),
            "pegging_deadline": first.get(
                "pegging_deadline"
            ),
            "pegging_status": first.get(
                "pegging_status"
            ),
            "pegging_variance_days": first.get(
                "pegging_variance_days"
            ),

            "flaf_issue_date": first.get(
                "flaf_issue_date"
            ),
            "flaf_deadline": first.get(
                "flaf_deadline"
            ),
            "flaf_status": first.get(
                "flaf_status"
            ),
            "flaf_variance_days": first.get(
                "flaf_variance_days"
            ),

            "construction_deadline": first.get(
                "construction_deadline"
            ),
            "construction_status": first.get(
                "construction_status"
            ),
            "construction_lag_days": first.get(
                "construction_lag_days"
            ),

            "hookup_deadline": first.get(
                "hookup_deadline"
            ),
            "hookup_status": first.get(
                "hookup_status"
            ),
        },

        "activities": [],
    }


    # ========================================================
    # GROUP ACTIVITY -> TASK
    # ========================================================

    activities = {}

    for record in records:

        activity_key = (
            record.get("activity_id"),
            record.get("activity_code"),
            record.get(
                "activity_group_description"
            ),
        )

        if activity_key not in activities:
            activities[activity_key] = {
                "activity_id": record.get(
                    "activity_id"
                ),
                "activity_code": record.get(
                    "activity_code"
                ),
                "activity_group_description": record.get(
                    "activity_group_description"
                ),
                "master_crew_code": record.get(
                    "master_crew_code"
                ),
                "tasks": [],
            }

        activities[activity_key]["tasks"].append(
            {
                "task_daily_id": record.get(
                    "task_daily_id"
                ),
                "task_code": record.get(
                    "task_code"
                ),

                "target_start": record.get(
                    "target_start"
                ),
                "target_end": record.get(
                    "target_end"
                ),
                "actual_start": record.get(
                    "actual_start"
                ),
                "actual_end": record.get(
                    "actual_end"
                ),

                "start_status": record.get(
                    "start_status"
                ),
                "start_variance_days": record.get(
                    "start_variance_days"
                ),

                "end_status": record.get(
                    "end_status"
                ),
                "end_variance_days": record.get(
                    "end_variance_days"
                ),

                "progress": record.get(
                    "progress"
                ),
                "progress_percent": record.get(
                    "progress_percent"
                ),
                "completed": record.get(
                    "completed"
                ),

                "execution_status": record.get(
                    "execution_status"
                ),
                "schedule_risk": record.get(
                    "schedule_risk"
                ),

                "planned_crew": record.get(
                    "planned_crew"
                ),
                "crew_type_id": record.get(
                    "crew_type_id"
                ),
                "crew_type_code": record.get(
                    "crew_type_code"
                ),
                "crew_type_name": record.get(
                    "crew_type_name"
                ),
                "crew_id": record.get(
                    "crew_id"
                ),
                "emp_id": record.get(
                    "emp_id"
                ),

                "quantity_source": record.get(
                    "quantity_source"
                ),
                "observed_quantity": record.get(
                    "observed_quantity"
                ),
                "calculated_remaining_quantity": record.get(
                    "calculated_remaining_quantity"
                ),

                "current_productivity_qty_per_hour": record.get(
                    "current_productivity_qty_per_hour"
                ),
                "productivity_source": record.get(
                    "productivity_source"
                ),
                "productivity_data_status": record.get(
                    "productivity_data_status"
                ),
            }
        )

    well["activities"] = list(
        activities.values()
    )

    return {
        "well": well
    }


# ============================================================
# WRITE / OVERWRITE investigation.json
# ============================================================

def update_investigation_json(
    records,
    well_id: int,
):
    response = build_investigation_response(
        records,
        well_id,
    )

    JSON_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Atomic replacement prevents a partially written JSON file.
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=JSON_DIR,
        prefix="investigation-",
        suffix=".tmp",
        delete=False,
    ) as file:

        json.dump(
            response,
            file,
            indent=4,
            ensure_ascii=False,
            allow_nan=False,
        )

        temporary_file = Path(file.name)

    temporary_file.replace(
        JSON_FILE
    )

    logger.info(
        "Investigation JSON updated: %s", JSON_FILE
    )

    return response
