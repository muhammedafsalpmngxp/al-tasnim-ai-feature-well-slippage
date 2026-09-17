"""
SQL VALIDATION AGENT.

Enforces SQL_VALIDATION_POLICY (app/prompts/prompt.py) against one generated query:
no write/DDL/admin statement, no stacked statements, no temp table, and — for
`investigation` — the exact DECLARE contract the service layer depends on.

This is intentionally NOT an LLM call. Whether a query contains INSERT/UPDATE/DDL, or is
missing a required DECLARE line, is a fact about its text, not a judgment call — a
keyword/shape scan is instant, free, and (unlike a language model) cannot be talked out of
flagging something it was told to flag. Business-logic correctness is the verifier
agent's job (sql_verifier_agent.py); this agent only ever checks the policy above.

This module knows nothing about LangGraph or retries — it is a single pure function.
Orchestration lives in sql_workflow.py.
"""

import re


_FORBIDDEN_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "EXEC", "EXECUTE", "GRANT", "REVOKE", "DENY", "BACKUP", "RESTORE", "SHUTDOWN",
    "KILL", "DBCC", "INTO",
    "OPENROWSET", "OPENDATASOURCE", "OPENQUERY", "OPENXML",
)
_FORBIDDEN_PATTERN = re.compile(r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE)
_TEMP_TABLE_PATTERN = re.compile(r"#{1,2}[A-Za-z_]\w*")
_SP_XP_PATTERN = re.compile(r"\b(?:sp|xp)_\w+", re.IGNORECASE)

# A simple, single-variable declaration: DECLARE @Name TYPE = value;
_GENERIC_DECLARE = re.compile(
    r"^\s*DECLARE\s+@[A-Za-z_][A-Za-z0-9_]*\s+\w+(?:\(\s*\d+\s*\))?\s*=.+$",
    re.IGNORECASE | re.DOTALL,
)
_MAIN_STATEMENT_START = re.compile(r"^\s*(WITH|SELECT)\b", re.IGNORECASE)

# The exact contract app/services/investigation.py depends on: it regex-replaces this
# line to inject the well id, and fails outright if it is not found exactly once.
_WELLID_DECLARE = re.compile(r"DECLARE\s+@WellId\s+INT\s*=\s*[^;]+;", re.IGNORECASE)
_TODAY_DECLARE = re.compile(r"DECLARE\s+@Today\s+DATE\s*=\s*[^;]+;", re.IGNORECASE)

REQUIRED_DECLARE_COUNT = {
    "investigation": 2,
    "slipped_wells": 0,
    "calculation": 0,
}


def _strip_comments_and_strings(sql):
    """Removes text that cannot itself be an executable keyword, so a forbidden word
    inside a comment or a quoted literal is not mistaken for one in the query itself."""

    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    return sql


def validate_sql(sql_text, target):
    """Returns (passed: bool, reason: str | None).

    `target` is one of the keys in REQUIRED_DECLARE_COUNT — an unknown target is treated
    as requiring zero DECLARE statements (the strict, no-preamble default).
    """

    if not sql_text or not sql_text.strip():
        return False, "The generated SQL is empty."

    cleaned = _strip_comments_and_strings(sql_text)

    forbidden = _FORBIDDEN_PATTERN.search(cleaned)
    if forbidden:
        return False, (
            f"The query contains a disallowed keyword: {forbidden.group(1).upper()}. "
            "Only a single read-only SELECT (optionally with CTEs) is allowed — no "
            "writes, no DDL, no SELECT ... INTO."
        )

    if _TEMP_TABLE_PATTERN.search(cleaned):
        return False, "The query references a temp table (#name or ##name), which is not allowed."

    if _SP_XP_PATTERN.search(cleaned):
        return False, "The query calls a stored procedure (sp_*/xp_*), which is not allowed."

    statements = [part.strip() for part in cleaned.split(";") if part.strip()]

    if not statements:
        return False, "The generated SQL has no executable statement."

    *preamble, main_statement = statements
    expected_declares = REQUIRED_DECLARE_COUNT.get(target, 0)

    if len(preamble) != expected_declares:
        return False, (
            f"Expected {expected_declares} DECLARE statement(s) before the main query for "
            f"target '{target}', found {len(preamble)}."
        )

    for statement in preamble:
        if not _GENERIC_DECLARE.match(statement):
            return False, (
                "Only simple 'DECLARE @name TYPE = value;' statements are allowed before "
                f"the main query. Found something else: {statement[:120]!r}"
            )

    if not _MAIN_STATEMENT_START.match(main_statement):
        return False, "The main query must start with SELECT or WITH."

    if target == "investigation":
        wellid_matches = _WELLID_DECLARE.findall(sql_text)

        if len(wellid_matches) != 1:
            return False, (
                "investigation.sql must contain exactly one "
                "'DECLARE @WellId INT = <value>;' line "
                f"(found {len(wellid_matches)}) — the service layer replaces this exact "
                "line by regex to select the well."
            )

        if not _TODAY_DECLARE.search(sql_text):
            return False, (
                "investigation.sql must declare "
                "'DECLARE @Today DATE = CAST(GETDATE() AS DATE);' (or an equivalent DATE "
                "expression) before it is used."
            )

    return True, None
