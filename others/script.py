import os
import json
import pyodbc
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()
# ============================================================
# CONFIGURATION
# ============================================================

DB_SERVER = os.getenv("DB_SERVER", "")
DB_PORT = os.getenv("DB_PORT", "")
DB_NAME = os.getenv("DB_NAME", "")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

OUTPUT_FILE = "database_inventory.txt"

# SQL Server ODBC Driver
ODBC_DRIVER = "ODBC Driver 18 for SQL Server"


# ============================================================
# VALIDATE CONFIG
# ============================================================

required = {
    "DB_SERVER": DB_SERVER,
    "DB_NAME": DB_NAME,
    "DB_USER": DB_USER,
    "DB_PASSWORD": DB_PASSWORD,
}

missing = [key for key, value in required.items() if not value]

if missing:
    raise RuntimeError(
        "Missing database configuration: "
        + ", ".join(missing)
    )


# ============================================================
# CONNECTION
# ============================================================

server = DB_SERVER

if DB_PORT:
    server = f"{DB_SERVER},{DB_PORT}"

connection_string = (
    f"DRIVER={{{ODBC_DRIVER}}};"
    f"SERVER={server};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USER};"
    f"PWD={DB_PASSWORD};"
    "TrustServerCertificate=yes;"
    "Encrypt=yes;"
)

print(f"Connecting to {server}/{DB_NAME}...")

conn = pyodbc.connect(
    connection_string,
    timeout=30
)

cursor = conn.cursor()

print("Connected successfully.")


# ============================================================
# HELPERS
# ============================================================

def safe_value(value):
    """
    Convert SQL values into text safely.
    """
    if value is None:
        return "NULL"

    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)

    return str(value)


def run_query(sql, params=None):
    cursor.execute(sql, params or [])
    columns = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    return columns, rows


def write_section(file, title):
    file.write("\n")
    file.write("=" * 100 + "\n")
    file.write(title + "\n")
    file.write("=" * 100 + "\n")


# ============================================================
# DATABASE INFORMATION
# ============================================================

database_info_sql = """
SELECT
    DB_NAME() AS database_name,
    SUSER_SNAME() AS current_login,
    USER_NAME() AS database_user,
    @@VERSION AS sql_server_version,
    SERVERPROPERTY('ProductVersion') AS product_version,
    SERVERPROPERTY('ProductLevel') AS product_level,
    SERVERPROPERTY('Edition') AS edition
"""

database_columns, database_rows = run_query(database_info_sql)


# ============================================================
# SCHEMAS
# ============================================================

schemas_sql = """
SELECT
    s.schema_id,
    s.name AS schema_name,
    dp.name AS owner_name
FROM sys.schemas AS s
LEFT JOIN sys.database_principals AS dp
    ON dp.principal_id = s.principal_id
ORDER BY s.name
"""

schema_columns, schema_rows = run_query(schemas_sql)


# ============================================================
# TABLES
# ============================================================

tables_sql = """
SELECT
    t.object_id,
    s.name AS schema_name,
    t.name AS table_name,
    t.create_date,
    t.modify_date
FROM sys.tables AS t
INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id
ORDER BY s.name, t.name
"""

table_columns, table_rows = run_query(tables_sql)


# ============================================================
# COLUMNS
# ============================================================

columns_sql = """
SELECT
    c.object_id,
    s.name AS schema_name,
    t.name AS table_name,
    c.column_id,
    c.name AS column_name,
    ty.name AS data_type,

    CASE
        WHEN ty.name IN (
            'varchar', 'char', 'varbinary', 'binary',
            'nvarchar', 'nchar'
        )
        THEN
            CASE
                WHEN c.max_length = -1 THEN 'MAX'
                WHEN ty.name IN ('nvarchar', 'nchar')
                    THEN CAST(c.max_length / 2 AS varchar(20))
                ELSE CAST(c.max_length AS varchar(20))
            END
        ELSE NULL
    END AS max_length,

    c.precision,
    c.scale,
    c.is_nullable,

    c.is_identity,
    c.is_computed,

    dc.definition AS default_definition,

    cc.definition AS computed_definition,

    c.collation_name

FROM sys.columns AS c

INNER JOIN sys.tables AS t
    ON t.object_id = c.object_id

INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id

INNER JOIN sys.types AS ty
    ON c.user_type_id = ty.user_type_id

LEFT JOIN sys.default_constraints AS dc
    ON dc.object_id = c.default_object_id

LEFT JOIN sys.computed_columns AS cc
    ON cc.object_id = c.object_id
    AND cc.column_id = c.column_id

ORDER BY
    s.name,
    t.name,
    c.column_id
"""

column_columns, column_rows = run_query(columns_sql)


# ============================================================
# PRIMARY KEYS
# ============================================================

primary_keys_sql = """
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    kc.name AS constraint_name,
    c.name AS column_name,
    ic.key_ordinal
FROM sys.key_constraints AS kc

INNER JOIN sys.tables AS t
    ON t.object_id = kc.parent_object_id

INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id

INNER JOIN sys.index_columns AS ic
    ON ic.object_id = kc.parent_object_id
    AND ic.index_id = kc.unique_index_id

INNER JOIN sys.columns AS c
    ON c.object_id = ic.object_id
    AND c.column_id = ic.column_id

WHERE kc.type = 'PK'

ORDER BY
    s.name,
    t.name,
    kc.name,
    ic.key_ordinal
"""

pk_columns, pk_rows = run_query(primary_keys_sql)


# ============================================================
# FOREIGN KEYS
# ============================================================

foreign_keys_sql = """
SELECT
    fk.object_id AS fk_object_id,

    OBJECT_SCHEMA_NAME(fk.parent_object_id) AS source_schema,
    OBJECT_NAME(fk.parent_object_id) AS source_table,
    pc.name AS source_column,

    OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS target_schema,
    OBJECT_NAME(fk.referenced_object_id) AS target_table,
    rc.name AS target_column,

    fk.name AS constraint_name,

    fk.delete_referential_action_desc AS delete_action,
    fk.update_referential_action_desc AS update_action,

    fkc.constraint_column_id

FROM sys.foreign_keys AS fk

INNER JOIN sys.foreign_key_columns AS fkc
    ON fkc.constraint_object_id = fk.object_id

INNER JOIN sys.columns AS pc
    ON pc.object_id = fkc.parent_object_id
    AND pc.column_id = fkc.parent_column_id

INNER JOIN sys.columns AS rc
    ON rc.object_id = fkc.referenced_object_id
    AND rc.column_id = fkc.referenced_column_id

ORDER BY
    source_schema,
    source_table,
    constraint_name,
    fkc.constraint_column_id
"""

fk_columns, fk_rows = run_query(foreign_keys_sql)


# ============================================================
# UNIQUE CONSTRAINTS
# ============================================================

unique_sql = """
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    kc.name AS constraint_name,
    c.name AS column_name,
    ic.key_ordinal
FROM sys.key_constraints AS kc

INNER JOIN sys.tables AS t
    ON t.object_id = kc.parent_object_id

INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id

INNER JOIN sys.index_columns AS ic
    ON ic.object_id = kc.parent_object_id
    AND ic.index_id = kc.unique_index_id

INNER JOIN sys.columns AS c
    ON c.object_id = ic.object_id
    AND c.column_id = ic.column_id

WHERE kc.type = 'UQ'

ORDER BY
    s.name,
    t.name,
    kc.name,
    ic.key_ordinal
"""

unique_columns, unique_rows = run_query(unique_sql)


# ============================================================
# CHECK CONSTRAINTS
# ============================================================

check_sql = """
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    cc.name AS constraint_name,
    cc.definition,
    cc.is_disabled,
    cc.is_not_trusted
FROM sys.check_constraints AS cc
INNER JOIN sys.tables AS t
    ON t.object_id = cc.parent_object_id
INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id
ORDER BY
    s.name,
    t.name,
    cc.name
"""

check_columns, check_rows = run_query(check_sql)


# ============================================================
# INDEXES
# ============================================================

indexes_sql = """
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    i.name AS index_name,
    i.type_desc AS index_type,
    i.is_unique,
    i.is_primary_key,
    i.is_unique_constraint,
    i.is_disabled,

    c.name AS column_name,
    ic.key_ordinal,
    ic.is_included_column,
    ic.is_descending_key

FROM sys.indexes AS i

INNER JOIN sys.tables AS t
    ON t.object_id = i.object_id

INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id

INNER JOIN sys.index_columns AS ic
    ON ic.object_id = i.object_id
    AND ic.index_id = i.index_id

INNER JOIN sys.columns AS c
    ON c.object_id = ic.object_id
    AND c.column_id = ic.column_id

WHERE
    i.index_id > 0

ORDER BY
    s.name,
    t.name,
    i.name,
    ic.key_ordinal,
    ic.index_column_id
"""

index_columns, index_rows = run_query(indexes_sql)


# ============================================================
# VIEWS
# ============================================================

views_sql = """
SELECT
    s.name AS schema_name,
    v.name AS view_name,
    v.create_date,
    v.modify_date,
    m.definition
FROM sys.views AS v
INNER JOIN sys.schemas AS s
    ON s.schema_id = v.schema_id
LEFT JOIN sys.sql_modules AS m
    ON m.object_id = v.object_id
ORDER BY
    s.name,
    v.name
"""

view_columns, view_rows = run_query(views_sql)


# ============================================================
# STORED PROCEDURES
# ============================================================

procedures_sql = """
SELECT
    s.name AS schema_name,
    p.name AS procedure_name,
    p.create_date,
    p.modify_date,
    m.definition
FROM sys.procedures AS p
INNER JOIN sys.schemas AS s
    ON s.schema_id = p.schema_id
LEFT JOIN sys.sql_modules AS m
    ON m.object_id = p.object_id
ORDER BY
    s.name,
    p.name
"""

procedure_columns, procedure_rows = run_query(procedures_sql)


# ============================================================
# FUNCTIONS
# ============================================================

functions_sql = """
SELECT
    s.name AS schema_name,
    o.name AS function_name,
    o.type_desc,
    o.create_date,
    o.modify_date,
    m.definition
FROM sys.objects AS o
INNER JOIN sys.schemas AS s
    ON s.schema_id = o.schema_id
LEFT JOIN sys.sql_modules AS m
    ON m.object_id = o.object_id
WHERE o.type IN ('FN', 'IF', 'TF', 'FS', 'FT')
ORDER BY
    s.name,
    o.name
"""

function_columns, function_rows = run_query(functions_sql)


# ============================================================
# TRIGGERS
# ============================================================

triggers_sql = """
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    tr.name AS trigger_name,
    tr.is_disabled,
    tr.is_instead_of_trigger,
    m.definition
FROM sys.triggers AS tr

INNER JOIN sys.tables AS t
    ON t.object_id = tr.parent_id

INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id

LEFT JOIN sys.sql_modules AS m
    ON m.object_id = tr.object_id

WHERE tr.parent_class = 1

ORDER BY
    s.name,
    t.name,
    tr.name
"""

trigger_columns, trigger_rows = run_query(triggers_sql)


# ============================================================
# TABLE ROW COUNTS
# ============================================================

row_count_sql = """
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    SUM(p.rows) AS row_count
FROM sys.tables AS t
INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id
INNER JOIN sys.partitions AS p
    ON p.object_id = t.object_id
    AND p.index_id IN (0, 1)
GROUP BY
    s.name,
    t.name
ORDER BY
    s.name,
    t.name
"""

row_count_columns, row_count_rows = run_query(row_count_sql)

row_counts = {}

for row in row_count_rows:
    row_counts[
        (str(row.schema_name), str(row.table_name))
    ] = row.row_count


# ============================================================
# WRITE REPORT
# ============================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as file:

    file.write("SQL SERVER DATABASE INVENTORY\n")
    file.write("=" * 100 + "\n")
    file.write(f"Generated: {datetime.now()}\n")
    file.write(f"Database: {DB_NAME}\n")
    file.write(f"Server: {server}\n")

    # --------------------------------------------------------
    # DATABASE INFO
    # --------------------------------------------------------

    write_section(file, "DATABASE INFORMATION")

    for row in database_rows:
        for column in database_columns:
            file.write(
                f"{column}: {safe_value(getattr(row, column))}\n"
            )

    # --------------------------------------------------------
    # SCHEMAS
    # --------------------------------------------------------

    write_section(file, "SCHEMAS")

    for row in schema_rows:
        file.write(
            f"Schema ID: {row.schema_id} | "
            f"Schema: {row.schema_name} | "
            f"Owner: {safe_value(row.owner_name)}\n"
        )

    # --------------------------------------------------------
    # TABLES
    # --------------------------------------------------------

    write_section(file, "TABLES")

    for row in table_rows:
        count = row_counts.get(
            (str(row.schema_name), str(row.table_name)),
            "UNKNOWN"
        )

        file.write(
            f"\n[{row.schema_name}].[{row.table_name}]\n"
        )

        file.write(
            f"Object ID: {row.object_id}\n"
        )

        file.write(
            f"Row Count: {count}\n"
        )

        file.write(
            f"Created: {row.create_date}\n"
        )

        file.write(
            f"Modified: {row.modify_date}\n"
        )

    # --------------------------------------------------------
    # COLUMNS
    # --------------------------------------------------------

    write_section(file, "COLUMNS / DATA TYPES")

    current_table = None

    for row in column_rows:

        table_key = (
            row.schema_name,
            row.table_name
        )

        if table_key != current_table:

            file.write(
                f"\n[{row.schema_name}].[{row.table_name}]\n"
            )

            current_table = table_key

        file.write(
            f"  {row.column_id}. {row.column_name} | "
            f"type={row.data_type}"
        )

        if row.max_length is not None:
            file.write(
                f" | max_length={row.max_length}"
            )

        if row.precision is not None:
            file.write(
                f" | precision={row.precision}"
            )

        if row.scale is not None:
            file.write(
                f" | scale={row.scale}"
            )

        file.write(
            f" | nullable={bool(row.is_nullable)}"
            f" | identity={bool(row.is_identity)}"
            f" | computed={bool(row.is_computed)}"
        )

        if row.default_definition:
            file.write(
                f" | default={row.default_definition}"
            )

        if row.computed_definition:
            file.write(
                f" | computed_definition={row.computed_definition}"
            )

        if row.collation_name:
            file.write(
                f" | collation={row.collation_name}"
            )

        file.write("\n")

    # --------------------------------------------------------
    # PRIMARY KEYS
    # --------------------------------------------------------

    write_section(file, "PRIMARY KEYS")

    for row in pk_rows:

        file.write(
            f"[{row.schema_name}].[{row.table_name}] | "
            f"PK={row.constraint_name} | "
            f"column={row.column_name} | "
            f"ordinal={row.key_ordinal}\n"
        )

    # --------------------------------------------------------
    # FOREIGN KEYS
    # --------------------------------------------------------

    write_section(file, "FOREIGN KEY RELATIONSHIPS")

    for row in fk_rows:

        file.write(
            f"[{row.source_schema}].[{row.source_table}]"
            f".[{row.source_column}]"
            f" -> "
            f"[{row.target_schema}].[{row.target_table}]"
            f".[{row.target_column}]"
            f" | FK={row.constraint_name}"
            f" | DELETE={row.delete_action}"
            f" | UPDATE={row.update_action}\n"
        )

    # --------------------------------------------------------
    # UNIQUE CONSTRAINTS
    # --------------------------------------------------------

    write_section(file, "UNIQUE CONSTRAINTS")

    for row in unique_rows:

        file.write(
            f"[{row.schema_name}].[{row.table_name}] | "
            f"constraint={row.constraint_name} | "
            f"column={row.column_name} | "
            f"ordinal={row.key_ordinal}\n"
        )

    # --------------------------------------------------------
    # CHECK CONSTRAINTS
    # --------------------------------------------------------

    write_section(file, "CHECK CONSTRAINTS")

    for row in check_rows:

        file.write(
            f"[{row.schema_name}].[{row.table_name}] | "
            f"constraint={row.constraint_name} | "
            f"definition={row.definition} | "
            f"disabled={row.is_disabled} | "
            f"not_trusted={row.is_not_trusted}\n"
        )

    # --------------------------------------------------------
    # INDEXES
    # --------------------------------------------------------

    write_section(file, "INDEXES")

    current_index = None

    for row in index_rows:

        index_key = (
            row.schema_name,
            row.table_name,
            row.index_name
        )

        if index_key != current_index:

            file.write(
                f"\n[{row.schema_name}].[{row.table_name}]"
                f" | INDEX={row.index_name}"
                f" | TYPE={row.index_type}"
                f" | UNIQUE={row.is_unique}"
                f" | PRIMARY_KEY={row.is_primary_key}"
                f" | UNIQUE_CONSTRAINT={row.is_unique_constraint}"
                f" | DISABLED={row.is_disabled}\n"
            )

            current_index = index_key

        file.write(
            f"    column={row.column_name}"
            f" | key_ordinal={row.key_ordinal}"
            f" | included={row.is_included_column}"
            f" | descending={row.is_descending_key}\n"
        )

    # --------------------------------------------------------
    # VIEWS
    # --------------------------------------------------------

    write_section(file, "VIEWS")

    for row in view_rows:

        file.write(
            f"\n[{row.schema_name}].[{row.view_name}]\n"
        )

        file.write(
            f"Created: {row.create_date}\n"
        )

        file.write(
            f"Modified: {row.modify_date}\n"
        )

        if row.definition:
            file.write(
                f"Definition:\n{row.definition}\n"
            )

    # --------------------------------------------------------
    # STORED PROCEDURES
    # --------------------------------------------------------

    write_section(file, "STORED PROCEDURES")

    for row in procedure_rows:

        file.write(
            f"\n[{row.schema_name}].[{row.procedure_name}]\n"
        )

        file.write(
            f"Created: {row.create_date}\n"
        )

        file.write(
            f"Modified: {row.modify_date}\n"
        )

        if row.definition:
            file.write(
                f"Definition:\n{row.definition}\n"
            )

    # --------------------------------------------------------
    # FUNCTIONS
    # --------------------------------------------------------

    write_section(file, "FUNCTIONS")

    for row in function_rows:

        file.write(
            f"\n[{row.schema_name}].[{row.function_name}]"
            f" | TYPE={row.type_desc}\n"
        )

        if row.definition:
            file.write(
                f"Definition:\n{row.definition}\n"
            )

    # --------------------------------------------------------
    # TRIGGERS
    # --------------------------------------------------------

    write_section(file, "TRIGGERS")

    for row in trigger_rows:

        file.write(
            f"\n[{row.schema_name}].[{row.table_name}]"
            f" | TRIGGER={row.trigger_name}"
            f" | DISABLED={row.is_disabled}"
            f" | INSTEAD_OF={row.is_instead_of_trigger}\n"
        )

        if row.definition:
            file.write(
                f"Definition:\n{row.definition}\n"
            )

    # --------------------------------------------------------
    # RANDOM SAMPLE DATA
    # --------------------------------------------------------

    write_section(
        file,
        "RANDOM SAMPLE DATA - 5 ROWS PER TABLE"
    )

    for row in table_rows:

        schema_name = row.schema_name
        table_name = row.table_name

        file.write("\n")
        file.write("-" * 100 + "\n")
        file.write(
            f"[{schema_name}].[{table_name}]"
        )
        file.write("\n")
        file.write("-" * 100 + "\n")

        try:

            sample_sql = f"""
                SELECT TOP 5 *
                FROM [{schema_name}].[{table_name}]
                ORDER BY NEWID()
            """

            sample_cursor = conn.cursor()
            sample_cursor.execute(sample_sql)

            sample_columns = [
                column[0]
                for column in sample_cursor.description
            ]

            sample_rows = sample_cursor.fetchall()

            if not sample_rows:
                file.write("NO ROWS\n")
                continue

            file.write(
                "Columns:\n"
            )

            file.write(
                " | ".join(sample_columns)
                + "\n"
            )

            file.write(
                "-" * 100 + "\n"
            )

            for sample_row in sample_rows:

                values = [
                    safe_value(value)
                    for value in sample_row
                ]

                file.write(
                    " | ".join(values)
                    + "\n"
                )

            sample_cursor.close()

        except Exception as exc:

            file.write(
                f"ERROR READING SAMPLE DATA: {exc}\n"
            )

    # --------------------------------------------------------
    # RELATIONSHIP SUMMARY
    # --------------------------------------------------------

    write_section(
        file,
        "RELATIONSHIP SUMMARY"
    )

    file.write(
        "The following relationships were discovered from "
        "SQL Server foreign-key metadata.\n\n"
    )

    for row in fk_rows:

        file.write(
            f"{row.source_schema}.{row.source_table}"
            f".{row.source_column}"
            f" -> "
            f"{row.target_schema}.{row.target_table}"
            f".{row.target_column}\n"
        )

    # --------------------------------------------------------
    # TABLES WITHOUT PRIMARY KEYS
    # --------------------------------------------------------

    write_section(
        file,
        "TABLES WITHOUT PRIMARY KEYS"
    )

    pk_tables = set()

    for row in pk_rows:

        pk_tables.add(
            (
                str(row.schema_name),
                str(row.table_name)
            )
        )

    for row in table_rows:

        table_key = (
            str(row.schema_name),
            str(row.table_name)
        )

        if table_key not in pk_tables:

            file.write(
                f"[{row.schema_name}].[{row.table_name}]\n"
            )

    # --------------------------------------------------------
    # TABLES WITHOUT FOREIGN KEYS
    # --------------------------------------------------------

    write_section(
        file,
        "TABLES WITHOUT FOREIGN KEYS"
    )

    fk_tables = set()

    for row in fk_rows:

        fk_tables.add(
            (
                str(row.source_schema),
                str(row.source_table)
            )
        )

    for row in table_rows:

        table_key = (
            str(row.schema_name),
            str(row.table_name)
        )

        if table_key not in fk_tables:

            file.write(
                f"[{row.schema_name}].[{row.table_name}]\n"
            )


# ============================================================
# CLEANUP
# ============================================================

cursor.close()
conn.close()

print()
print("=" * 70)
print("DATABASE INVENTORY COMPLETE")
print("=" * 70)
print(f"Output file: {OUTPUT_FILE}")