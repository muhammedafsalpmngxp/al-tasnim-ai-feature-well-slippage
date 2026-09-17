"""
Build a compact, LLM-friendly description of the live database.

schema.txt — structure only: tables, columns (+ type/nullable/PK marker), declared foreign
             keys, and a warning on tables that hold many rows per key. Nothing is guessed:
             a name match between two columns is not proof of a real relationship, and a
             wrong guess here would be invisible to review, unlike a rule in
             business_rules.md / slippage.md that a person actually reads and can correct.

hints.txt  — real coded values read out of the small lookup tables, so a SQL-writing agent
             filters, joins and decodes on values that actually exist instead of inventing
             them.

structure_fingerprint.txt — a hash of the structure schema.txt describes (see
             compute_structural_fingerprint). app/services/sql_workflow.py compares this
             against the fingerprint the current SQL files were generated from, to decide
             whether regenerating them is actually warranted.

No LLM is involved: all three files come straight from the database's own metadata and
data.
"""

import hashlib
import logging
import os
import re
import time

from pathlib import Path

from app.services.console_log import log_stage


logger = logging.getLogger(__name__)

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"

SCHEMA_FILE = SCHEMA_DIR / "schema.txt"
HINTS_FILE = SCHEMA_DIR / "hints.txt"
FINGERPRINT_FILE = SCHEMA_DIR / "structure_fingerprint.txt"

# Substrings that mark a column as secret — never written to either file, in any table.
SECRET_COLUMN_MARKERS = (
    "password", "secret", "token", "pwd", "apikey", "api_key", "credential", "private_key",
)

# T-SQL reserved keywords (SQL Server). A column whose NAME is one of these MUST be
# [bracketed] or the query fails to parse — and the error is misleading: SQL Server reports
# "Incorrect syntax near the keyword ..." rather than "Invalid column name", so it reads as
# if the column doesn't exist when it does. well.task_daily.plan is exactly this case.
_TSQL_RESERVED = frozenset("""
ADD ALL ALTER AND ANY AS ASC AUTHORIZATION BACKUP BEGIN BETWEEN BREAK BROWSE BULK BY CASCADE CASE
CHECK CHECKPOINT CLOSE CLUSTERED COALESCE COLLATE COLUMN COMMIT COMPUTE CONSTRAINT CONTAINS
CONTAINSTABLE CONTINUE CONVERT CREATE CROSS CURRENT CURRENT_DATE CURRENT_TIME CURRENT_TIMESTAMP
CURRENT_USER CURSOR DATABASE DBCC DEALLOCATE DECLARE DEFAULT DELETE DENY DESC DISK DISTINCT
DISTRIBUTED DOUBLE DROP DUMP ELSE END ERRLVL ESCAPE EXCEPT EXEC EXECUTE EXISTS EXIT EXTERNAL FETCH
FILE FILLFACTOR FOR FOREIGN FREETEXT FREETEXTTABLE FROM FULL FUNCTION GOTO GRANT GROUP HAVING
HOLDLOCK IDENTITY IDENTITY_INSERT IDENTITYCOL IF IN INDEX INNER INSERT INTERSECT INTO IS JOIN KEY
KILL LEFT LIKE LINENO LOAD MERGE NATIONAL NOCHECK NONCLUSTERED NOT NULL NULLIF OF OFF OFFSETS ON
OPEN OPENDATASOURCE OPENQUERY OPENROWSET OPENXML OPTION OR ORDER OUTER OVER PERCENT PIVOT PLAN
PRECISION PRIMARY PRINT PROC PROCEDURE PUBLIC RAISERROR READ READTEXT RECONFIGURE REFERENCES
REPLICATION RESTORE RESTRICT RETURN REVERT REVOKE RIGHT ROLLBACK ROWCOUNT ROWGUIDCOL RULE SAVE
SCHEMA SECURITYAUDIT SELECT SESSION_USER SET SETUSER SHUTDOWN SOME STATISTICS SYSTEM_USER TABLE
TABLESAMPLE TEXTSIZE THEN TO TOP TRAN TRANSACTION TRIGGER TRUNCATE TRY_CONVERT TSEQUAL UNION
UNIQUE UNPIVOT UPDATE UPDATETEXT USE USER VALUES VARYING VIEW WAITFOR WHEN WHERE WHILE WITH
WRITETEXT
""".split())

# A bare (unbracketed) T-SQL identifier is a letter/underscore then letters/digits/underscore/$/#.
# Anything else must be bracketed too — this database has columns like "Form Number" and
# "No of FTR Items Identified", which fail with the SAME misleading error as `plan`.
_BARE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")


def quote_column(column_name):
    """The form a SQL-writing agent must copy: [bracketed] whenever the bare name won't parse.

    Applied to the column DECLARATION lines only. FK lines stay bare so they remain easy to
    parse with a plain word pattern.
    """

    if column_name.upper() in _TSQL_RESERVED or not _BARE_IDENTIFIER.match(column_name):
        return f"[{column_name}]"

    return column_name


# ── Optional scope filters, read from the environment ──────────────────────────────
# All empty by default (no filtering). Which tables matter is per-database knowledge, so
# it is configured, never hardcoded here:
#
#   SCHEMA_ALLOWED_SCHEMAS   keep only these schemas, e.g. "well,dbo,ref,project"
#   SCHEMA_INCLUDED_TABLES   keep ONLY these tables — the tightest filter, and the one
#                            that most directly helps the SQL agents, e.g.
#                            "well.well_master,well.task_daily,project.project_mstr"
#   SCHEMA_EXCLUDED_TABLES   drop these tables (wins over the include list)
#   SCHEMA_EXCLUDED_COLUMNS  drop these columns from whatever survives
#
# They compose: schemas narrow first, then the include allowlist, then the exclusions
# carve out exceptions.

def _env_set(variable_name):
    raw = os.getenv(variable_name, "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _is_secret(column_name):
    lower = column_name.lower()
    return any(marker in lower for marker in SECRET_COLUMN_MARKERS)


def _is_excluded_table(schema_name, table_name, excluded_tables):
    """Matches "schema.table" (exact) or a bare "table" name in every allowed schema."""

    if not excluded_tables:
        return False

    return (
        f"{schema_name}.{table_name}".lower() in excluded_tables
        or table_name.lower() in excluded_tables
    )


def _is_included_table(schema_name, table_name, included_tables):
    """True when SCHEMA_INCLUDED_TABLES is unset (no allowlist) or this table is on it.

    An allowlist is the strongest way to shrink what the SQL agents have to read: most
    of a BI database is irrelevant to well delays, and every irrelevant table is context
    the generation and verification agents must wade through on every single call. Set
    SCHEMA_INCLUDED_TABLES to the handful of tables the queries actually need and the
    schema/hints files collapse to just those.

    Matches "schema.table" (exact) or a bare "table" name in any allowed schema, the
    same way the exclusion lists do. Exclusions still win: a table on both lists stays
    hidden, so a single EXCLUDED entry can carve an exception out of a broad allowlist.
    """

    if not included_tables:
        return True

    return (
        f"{schema_name}.{table_name}".lower() in included_tables
        or table_name.lower() in included_tables
    )


def _is_excluded_column(schema_name, table_name, column_name, excluded_columns):
    """Matches "schema.table.column", "table.column", or a bare "column" name everywhere.

    A hidden column is also stripped from the primary keys and from any foreign key that
    touches it, so the schema never points an agent at a column it cannot see.
    """

    if not excluded_columns:
        return False

    return (
        f"{schema_name}.{table_name}.{column_name}".lower() in excluded_columns
        or f"{table_name}.{column_name}".lower() in excluded_columns
        or column_name.lower() in excluded_columns
    )


COLUMNS_SQL = """
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
"""

PRIMARY_KEYS_SQL = """
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    c.name AS column_name
FROM sys.key_constraints AS kc
INNER JOIN sys.tables AS t ON t.object_id = kc.parent_object_id
INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
INNER JOIN sys.index_columns AS ic
    ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id
INNER JOIN sys.columns AS c
    ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE kc.type = 'PK'
"""

FOREIGN_KEYS_SQL = """
SELECT
    OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS source_schema,
    OBJECT_NAME(fkc.parent_object_id) AS source_table,
    pc.name AS source_column,
    OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS target_schema,
    OBJECT_NAME(fkc.referenced_object_id) AS target_table,
    rc.name AS target_column
FROM sys.foreign_key_columns AS fkc
INNER JOIN sys.columns AS pc
    ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
INNER JOIN sys.columns AS rc
    ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
"""

# Approximate row counts straight from the catalogue — one query, no table is scanned, so this
# stays instant however large the data gets. Lets a big table be skipped for value sampling
# WITHOUT being queried at all.
#
# sys.partitions, NOT sys.dm_db_partition_stats: the DMV needs VIEW DATABASE PERFORMANCE STATE,
# which this server's BI login does not have, and without counts nothing can be recognised as a
# lookup list.
ROW_COUNTS_SQL = """
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    SUM(p.rows) AS row_count
FROM sys.tables AS t
INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
INNER JOIN sys.partitions AS p
    ON p.object_id = t.object_id AND p.index_id IN (0, 1)
GROUP BY s.name, t.name
"""


def _fetch_columns(
    cursor,
    allowed_schemas,
    excluded_tables,
    excluded_columns,
    included_tables=None,
):
    """schema.table -> [(column_name, data_type, max_length, nullable), ...]

    Everything downstream (primary keys, foreign keys, duplicate-key detection, value
    hints, the fingerprint) is filtered against the tables this returns, so restricting
    here restricts the whole output — no other function needs to know about the filters.
    """

    cursor.execute(COLUMNS_SQL)
    tables = {}

    for sch, tbl, _position, col, dtype, maxlen, nullable in cursor.fetchall():

        if allowed_schemas and sch.lower() not in allowed_schemas:
            continue

        if not _is_included_table(sch, tbl, included_tables):
            continue

        if _is_secret(col):
            continue

        if _is_excluded_table(sch, tbl, excluded_tables):
            continue

        if _is_excluded_column(sch, tbl, col, excluded_columns):
            continue

        tables.setdefault(f"{sch}.{tbl}", []).append(
            (col, dtype, maxlen, nullable == "YES")
        )

    return tables


def _fetch_primary_keys(cursor, visible, excluded_columns):
    """schema.table -> set of primary-key column names, restricted to visible tables."""

    cursor.execute(PRIMARY_KEYS_SQL)
    primary_keys = {}

    for sch, tbl, col in cursor.fetchall():
        table = f"{sch}.{tbl}"

        if table not in visible:
            continue

        if _is_excluded_column(sch, tbl, col, excluded_columns):
            continue

        primary_keys.setdefault(table, set()).add(col)

    return primary_keys


def _fetch_foreign_keys(cursor, visible, excluded_columns):
    """schema.table -> ["col -> schema.table.col", ...]. Both ends must be visible."""

    cursor.execute(FOREIGN_KEYS_SQL)
    foreign_keys = {}

    for fs, ft, fc, ts, tt, tc in cursor.fetchall():
        source = f"{fs}.{ft}"
        target = f"{ts}.{tt}"

        # Either end being hidden makes the relationship unusable — a join nobody can write.
        if source not in visible or target not in visible:
            continue

        if _is_excluded_column(fs, ft, fc, excluded_columns):
            continue

        if _is_excluded_column(ts, tt, tc, excluded_columns):
            continue

        foreign_keys.setdefault(source, []).append(f"{fc} -> {target}.{tc}")

    return foreign_keys


def _fetch_row_counts(cursor, visible):
    """schema.table -> approximate row count. Empty dict if the login lacks the permission."""

    try:
        cursor.execute(ROW_COUNTS_SQL)

    except Exception as exc:
        logger.info("schema: row counts unavailable (%s)", exc)
        return {}

    return {
        f"{sch}.{tbl}": (count or 0)
        for sch, tbl, count in cursor.fetchall()
        if f"{sch}.{tbl}" in visible
    }


# Below this many rows a repeated key cannot distort an answer enough to be worth a scan.
_DUP_CHECK_MIN_ROWS = 100


def _detect_duplicate_keys(cursor, tables, primary_keys, row_counts):
    """table -> the key column that repeats, for tables holding many rows per entity.

    Measured from the live data, not assumed: a table with more rows than distinct key values
    must be de-duplicated before per-entity questions, and forgetting that is the single most
    damaging SQL mistake in this kind of database. well.task_daily is exactly this shape.
    """

    duplicates = {}

    for table, columns in tables.items():
        key_columns = primary_keys.get(table, set())

        # A single-column primary key is unique by definition — the database enforces it, so
        # scanning to confirm would tell us nothing. Only tables where the entity key is a
        # guess (no primary key, or a composite one) need a scan.
        if len(key_columns) == 1:
            continue

        known_rows = row_counts.get(table)

        if known_rows is not None and known_rows < _DUP_CHECK_MIN_ROWS:
            continue

        names = [name for name, *_ in columns]
        candidates = sorted(key_columns) or [n for n in names if n.lower().endswith("id")]

        if not candidates:
            continue

        key = candidates[0]
        schema_name, _, table_name = table.partition(".")

        try:
            cursor.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT [{key}]) "
                f"FROM [{schema_name}].[{table_name}]"
            )
            total, distinct = cursor.fetchone()

        except Exception:
            # A table we cannot count must not break introspection.
            continue

        if total and distinct and total > distinct:
            duplicates[table] = key

    return duplicates


# ── Sample data ────────────────────────────────────────────────────────────────────
# A declared type says a column is nvarchar(50); it does not say whether that column holds
# 'YES', a date written as text, or nothing at all. Reading the first few rows and showing
# each column's actual values answers the question the type cannot.
#
# Sampled per TABLE (one query) but rendered per COLUMN, on the column's own line. Showing
# whole rows instead would be unbounded — this database has tables of 100+ columns, and
# five of those rows would swamp the structure the file exists to describe.
#
# NULLs are printed rather than skipped: a column that is empty in every sampled row is
# telling you something, and hiding it would read as "no sample available".

SAMPLE_ROW_COUNT = max(0, int(os.getenv("SCHEMA_SAMPLE_ROWS", "5")))
_SAMPLE_VALUE_MAX_CHARS = 30


def _shorten(text):
    if len(text) <= _SAMPLE_VALUE_MAX_CHARS:
        return text

    return text[: _SAMPLE_VALUE_MAX_CHARS - 1] + "…"


def _fetch_sample_rows(cursor, tables):
    """table -> {column: [first N values]}. Best effort: a table that cannot be read is
    simply left without samples rather than failing the refresh."""

    if not SAMPLE_ROW_COUNT:
        return {}

    samples = {}

    for table, columns in tables.items():
        schema_name, _, table_name = table.partition(".")
        names = [name for name, *_ in columns]
        column_sql = ", ".join(f"[{name}]" for name in names)

        try:
            cursor.execute(
                f"SELECT TOP {SAMPLE_ROW_COUNT} {column_sql} "
                f"FROM [{schema_name}].[{table_name}]"
            )
            rows = cursor.fetchall()

        except Exception:
            continue

        if not rows:
            continue

        by_column = {}

        for index, name in enumerate(names):
            values = [
                "(null)" if row[index] is None else _shorten(_clean_value(row[index]))
                for row in rows
            ]
            by_column[name] = values

        samples[table] = by_column

    return samples


def _render_schema(tables, primary_keys, foreign_keys, duplicate_keys, samples=None):

    samples = samples or {}
    lines = []

    for table, columns in tables.items():
        lines.append(f"TABLE {table}")
        table_pk = primary_keys.get(table, set())
        table_samples = samples.get(table, {})

        for name, dtype, maxlen, nullable in columns:
            # maxlen is NULL for non-text types and -1 for the MAX types, so both render as
            # the bare type name.
            type_desc = dtype + (f"({maxlen})" if maxlen and maxlen > 0 else "")
            null_desc = "" if nullable else " NOT NULL"
            pk_desc = " PK" if name in table_pk else ""

            values = table_samples.get(name)
            sample_desc = f"   -- e.g. {', '.join(values)}" if values else ""

            # quote_column() is for DISPLAY only — `name` stays raw for the PK comparison.
            lines.append(
                f"  - {quote_column(name)} {type_desc}{null_desc}{pk_desc}{sample_desc}"
            )

        if table in duplicate_keys:
            key = duplicate_keys[table]
            lines.append(
                f"  ⚠ MANY ROWS PER {key} — de-duplicate (COUNT(DISTINCT ...) or GROUP BY) "
                f"before answering per-{key} questions"
            )

        for relationship in foreign_keys.get(table, []):
            lines.append(f"  FK: {relationship}")

        lines.append("")

    return "\n".join(lines).strip()


# ── Value hints: real values from every table ──────────────────────────────────────
# Nothing here names a specific table or column — candidates are recognised by SHAPE, so
# this follows whatever database is configured rather than this one's vocabulary.
#
# Two shapes, because the useful hint differs:
#   small tables  — whole rows, so the code -> description mapping is preserved
#                   (3522|Nimr ODC tells you more than "3522" and "Nimr ODC" separately).
#   every other   — per-column distinct values, but ONLY for columns that turn out to hold
#     table         few distinct values. A column with more than _HINT_MAX_VALUES distinct
#                   values is an id, a name or free text: listing it would be noise, and
#                   the cardinality probe is what decides that, not the column's name.

_HINT_COLUMN_SUFFIXES = ("name", "code", "description", "desc", "label", "status", "type")
_HINT_MAX_VALUES = 30
_HINT_MAX_ROWS = 50  # at or below this, sample whole rows instead of per column

# Candidate columns for per-column sampling. Text longer than this is prose, JSON or a URL,
# never a code; the MAX/blob types are excluded outright.
_CODEABLE_TEXT_TYPES = ("char", "varchar", "nchar", "nvarchar")
_MAX_CODE_TEXT_LENGTH = 100
_HINT_MAX_COLUMNS = 40  # bounds the size of the batched probe query on very wide tables


def _is_hint_column(column_name):
    lower = column_name.lower()
    return lower.endswith(_HINT_COLUMN_SUFFIXES) or lower in ("code", "name")


def _candidate_columns(columns):
    """Columns worth probing for a short list of distinct values."""

    candidates = []

    for name, dtype, maxlen, _nullable in columns:
        lower_type = dtype.lower()

        # Blobs are never a code list: the MAX types and the legacy large types.
        if lower_type in ("text", "ntext", "xml", "image"):
            continue

        if lower_type in _CODEABLE_TEXT_TYPES and maxlen == -1:
            continue

        if _is_hint_column(name):
            # The NAME says it is a code or a label, so probe it whatever its declared
            # length — a column declared nvarchar(255) routinely holds short codes, and
            # judging it by the declaration would drop most lookup labels in this database.
            candidates.append(name)

        elif name.lower() == "id" or name.lower().endswith("_id"):
            # An identifier is for joining, not for filtering by literal value. Some happen
            # to hold few enough distinct values to pass the cardinality probe (task_daily
            # has 27 distinct emp_id), and listing those numbers is pure noise.
            continue

        elif lower_type in _CODEABLE_TEXT_TYPES and maxlen and 0 < maxlen <= _MAX_CODE_TEXT_LENGTH:
            # Short text with an unremarkable name — the cardinality probe decides whether
            # it is really a coded column.
            candidates.append(name)

    return candidates[:_HINT_MAX_COLUMNS]


def _clean_value(value):
    """One line, always. A stored value can itself contain a newline, which would otherwise
    split a table's entry across lines and break the one-line-per-table format."""

    if value is None:
        return ""

    return " ".join(str(value).split())


def _is_small_table(cursor, table, row_count):
    """True when the table is small enough to sample whole rows from."""

    if row_count is not None:
        return row_count <= _HINT_MAX_ROWS

    # Views have no catalogue row count. Probe with TOP (limit + 1) rather than COUNT(*):
    # we only need to know whether it is small, so an expensive view stops as soon as it is
    # known to be too big instead of being evaluated in full just to be discarded.
    schema_name, _, table_name = table.partition(".")

    try:
        cursor.execute(
            f"SELECT TOP {_HINT_MAX_ROWS + 1} 1 FROM [{schema_name}].[{table_name}]"
        )
        return len(cursor.fetchall()) <= _HINT_MAX_ROWS

    except Exception:
        return False


def _sample_whole_rows(cursor, table, columns):
    """Small table: sample whole rows, keeping the code -> description mapping intact."""

    hint_columns = [name for name, *_ in columns if _is_hint_column(name)]

    if not hint_columns:
        return None

    schema_name, _, table_name = table.partition(".")
    column_sql = ", ".join(f"[{name}]" for name in hint_columns)

    try:
        cursor.execute(
            f"SELECT DISTINCT TOP {_HINT_MAX_VALUES} {column_sql} "
            f"FROM [{schema_name}].[{table_name}] ORDER BY {column_sql}"
        )
        rows = cursor.fetchall()

    except Exception:
        return None

    if not rows:
        return None

    values = ["|".join(_clean_value(value) for value in row) for row in rows]

    return f"- {table} ({', '.join(hint_columns)}): " + "; ".join(values)


def _sample_low_cardinality_columns(cursor, table, columns):
    """Large table: per-column distinct values, keeping only the genuinely coded columns.

    Every candidate column is probed in ONE batched statement. The server does the work
    per column, but the round trip — which is what actually costs time against a remote
    server — happens once per table instead of once per column.
    """

    candidates = _candidate_columns(columns)

    if not candidates:
        return None

    schema_name, _, table_name = table.partition(".")
    parts = []

    for index, name in enumerate(candidates):
        # The column name is emitted as a literal to label each row. It comes from the
        # catalogue, not from user input, and the doubled quote keeps it a valid literal.
        label = name.replace("'", "''")
        parts.append(
            f"SELECT '{label}' AS hint_column, CONVERT(nvarchar(400), value) AS hint_value "
            f"FROM (SELECT DISTINCT TOP {_HINT_MAX_VALUES + 1} [{name}] AS value "
            f"FROM [{schema_name}].[{table_name}] WHERE [{name}] IS NOT NULL) AS probe_{index}"
        )

    try:
        cursor.execute(" UNION ALL ".join(parts))
        rows = cursor.fetchall()

    except Exception:
        # A table we cannot read must not break hint building.
        return None

    grouped = {}

    for hint_column, hint_value in rows:
        grouped.setdefault(hint_column, []).append(_clean_value(hint_value))

    described = []

    for name in candidates:
        values = grouped.get(name)

        # More than the cap means the probe hit its TOP limit: too many distinct values to
        # be a code list, so it is an id, a name or free text. Listing it would be noise.
        if not values or len(values) > _HINT_MAX_VALUES:
            continue

        described.append(f"{name} = " + "; ".join(sorted(values)))

    if not described:
        return None

    return f"- {table}: " + " | ".join(described)


def _render_value_hints(cursor, tables, row_counts):
    """Every table gets a line, so a missing table means a missing table — not a table
    that was silently skipped."""

    lines = [
        "VALUE HINTS (real coded values read from the database — filter, join and decode "
        "using these ACTUAL values rather than guessing them). A small table is shown as "
        "whole rows, so a code and its description stay together; a larger table is shown "
        "per column, listing only the columns that hold a short set of distinct values. "
        "Every table is listed: a table with nothing to show says why:"
    ]

    for table, columns in tables.items():
        if _is_small_table(cursor, table, row_counts.get(table)):
            line = _sample_whole_rows(cursor, table, columns)
        else:
            line = _sample_low_cardinality_columns(cursor, table, columns)

        if line:
            lines.append(line)

        elif row_counts.get(table) == 0:
            lines.append(f"- {table}: (empty — no rows stored)")

        else:
            lines.append(
                f"- {table}: (no short value lists — its columns hold ids, names, dates "
                f"or free text)"
            )

    return "\n".join(lines) if len(lines) > 1 else ""


def compute_structural_fingerprint(tables, primary_keys, foreign_keys):
    """A hash of the database's STRUCTURE only — tables, columns, types, nullability,
    primary keys, declared foreign keys.

    Deliberately excludes row counts, duplicate-key findings and sampled values: those
    change whenever DATA changes, and a fingerprint that reacted to data churn would
    flag "the schema changed" every time someone inserts a row, not just when a table
    or column is actually added, dropped, renamed or retyped. This is what lets a
    caller decide "does the SQL need regenerating?" without over-triggering.
    """

    hasher = hashlib.sha256()

    for table in sorted(tables):
        hasher.update(f"TABLE {table}\n".encode("utf-8"))

        for name, dtype, maxlen, nullable in tables[table]:
            hasher.update(f"  COL {name}|{dtype}|{maxlen}|{nullable}\n".encode("utf-8"))

        for pk_column in sorted(primary_keys.get(table, ())):
            hasher.update(f"  PK {pk_column}\n".encode("utf-8"))

        for relationship in sorted(foreign_keys.get(table, ())):
            hasher.update(f"  FK {relationship}\n".encode("utf-8"))

    return hasher.hexdigest()


def refresh_schema_files(connection, db_name):
    """Introspect the active DB and (re)write its schema.txt and hints.txt files."""

    cursor = connection.cursor()

    allowed_schemas = _env_set("SCHEMA_ALLOWED_SCHEMAS")
    excluded_tables = _env_set("SCHEMA_EXCLUDED_TABLES")
    excluded_columns = _env_set("SCHEMA_EXCLUDED_COLUMNS")
    included_tables = _env_set("SCHEMA_INCLUDED_TABLES")

    started_at = time.monotonic()

    tables = _fetch_columns(
        cursor,
        allowed_schemas,
        excluded_tables,
        excluded_columns,
        included_tables,
    )
    visible = set(tables.keys())

    primary_keys = _fetch_primary_keys(cursor, visible, excluded_columns)
    foreign_keys = _fetch_foreign_keys(cursor, visible, excluded_columns)
    row_counts = _fetch_row_counts(cursor, visible)
    duplicate_keys = _detect_duplicate_keys(cursor, tables, primary_keys, row_counts)
    samples = _fetch_sample_rows(cursor, tables)

    schema_text = _render_schema(
        tables, primary_keys, foreign_keys, duplicate_keys, samples
    )

    table_count = len(tables)
    column_count = sum(len(columns) for columns in tables.values())

    log_stage(
        "Schema",
        f"introspected [{db_name}]: {table_count} tables, {column_count} columns, "
        f"{len(samples)} sampled, {len(duplicate_keys)} flagged for de-duplication "
        f"in {time.monotonic() - started_at:.1f}s",
        ok=True,
    )

    hints_started_at = time.monotonic()
    hints_text = _render_value_hints(cursor, tables, row_counts)
    hint_count = max(len(hints_text.splitlines()) - 1, 0)

    log_stage(
        "Hints",
        f"sampled [{db_name}]: {hint_count} lookup entries in "
        f"{time.monotonic() - hints_started_at:.1f}s",
        ok=True,
    )

    fingerprint = compute_structural_fingerprint(tables, primary_keys, foreign_keys)

    cursor.close()

    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    # Fixed filenames, not per-database ones: these three files describe whichever
    # database is active right now, and a refresh overwrites them in place. Naming them
    # after the database would leave a stale set behind on every switch, and the SQL
    # agents would have to guess which set is current.
    schema_path = SCHEMA_FILE
    hints_path = HINTS_FILE
    fingerprint_path = FINGERPRINT_FILE

    # Read the previous fingerprint before overwriting it, so a refresh can report whether
    # the structure actually moved. That comparison is what the SQL pipeline keys off when
    # it is switched on; reported on its own it also makes the schema phase testable in
    # isolation — change a table, refresh, and see the fingerprint move without any SQL
    # being regenerated.
    previous_fingerprint = (
        fingerprint_path.read_text(encoding="utf-8").strip()
        if fingerprint_path.exists()
        else None
    )
    fingerprint_changed = previous_fingerprint != fingerprint

    if previous_fingerprint is None:
        fingerprint_detail = f"computed [{db_name}]: {fingerprint[:16]}... (first run)"
    elif fingerprint_changed:
        fingerprint_detail = (
            f"CHANGED [{db_name}]: {previous_fingerprint[:16]}... -> {fingerprint[:16]}..."
        )
    else:
        fingerprint_detail = f"unchanged [{db_name}]: {fingerprint[:16]}..."

    log_stage("Fingerprint", fingerprint_detail)

    schema_path.write_text(schema_text, encoding="utf-8")
    hints_path.write_text(hints_text, encoding="utf-8")
    fingerprint_path.write_text(fingerprint, encoding="utf-8")

    log_stage(
        "Write",
        f"write ok [{db_name}]: {schema_path.name}, {hints_path.name}, "
        f"{fingerprint_path.name} in {time.monotonic() - started_at:.1f}s total",
        ok=True,
    )

    logger.info(
        "schema: rebuilt %s (%d tables, %d columns, %d lookup tables with value hints)",
        db_name, table_count, column_count, hint_count,
    )

    return {
        "database": db_name,
        "tables": table_count,
        "columns": column_count,
        "hint_tables": hint_count,
        "schema_file": str(schema_path),
        "hints_file": str(hints_path),
        "fingerprint": fingerprint,
        "fingerprint_file": str(fingerprint_path),
        "previous_fingerprint": previous_fingerprint,
        "fingerprint_changed": fingerprint_changed,
    }
