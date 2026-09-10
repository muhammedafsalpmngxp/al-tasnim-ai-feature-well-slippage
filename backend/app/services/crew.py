"""
CREW / SUPERVISOR / EMPLOYEE ROSTER (execution + grouping).

Runs backend/sql/well_crew.sql and folds its flat crew x employee rows
into one entry per crew.

This module GROUPS and DE-DUPLICATES. It does not calculate, infer or
invent anything: every id, code and name here is a value the SQL
returned. A crew with no resolved code, no supervisor or no employees
keeps its NULLs so the dashboard can say "not recorded" rather than
showing a filled-in guess.
"""

from pathlib import Path

from app.services.serialization import clean_value, normalize_text, to_number


BASE_DIR = Path(__file__).resolve().parents[2]

CREW_SQL_FILE = BASE_DIR / "sql" / "well_crew.sql"


def _read_rows(connection, well_id: int):

    if not CREW_SQL_FILE.exists():

        raise FileNotFoundError(
            f"Well crew SQL file not found: {CREW_SQL_FILE}"
        )

    query = CREW_SQL_FILE.read_text(encoding="utf-8")

    cursor = connection.cursor()

    try:

        cursor.execute(query, well_id)

        if cursor.description is None:
            return []

        columns = [column[0] for column in cursor.description]

        return [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

    finally:
        cursor.close()


def get_well_crews(connection, well_id: int):

    """
    Crews recorded against one well, each with its supervisor and its
    employees.

    Returns:
        [
            {
                "crew_id":         <int>,
                "crew_code":       <str|None>,
                "supervisor_id":   <int|None>,
                "supervisor_name": <str|None>,
                "employees":       [{"employee_id":…, "employee_name":…}, …]
            },
            ...
        ]
    """

    crews = {}

    for row in _read_rows(connection, well_id):

        crew_id = to_number(clean_value(row.get("crew_id")))

        crew = crews.get(crew_id)

        if crew is None:

            crew = {
                "crew_id": crew_id,
                "crew_code": normalize_text(clean_value(row.get("crew_code"))),
                "supervisor_id": to_number(
                    clean_value(row.get("supervisor_id"))
                ),
                "supervisor_name": normalize_text(
                    clean_value(row.get("supervisor_name"))
                ),
                "employees": []
            }

            crews[crew_id] = crew

        employee_id = to_number(clean_value(row.get("employee_id")))
        employee_name = normalize_text(clean_value(row.get("employee_name")))

        # A crew with no membership row still returns one all-NULL
        # employee row from the LEFT JOIN — that is "no employees
        # recorded", not an anonymous employee.
        if employee_id is None and employee_name is None:
            continue

        employee = {
            "employee_id": employee_id,
            "employee_name": employee_name
        }

        if employee not in crew["employees"]:
            crew["employees"].append(employee)

    # SQL ordered the rows; dict preserves that insertion order.
    return list(crews.values())
