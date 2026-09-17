import logging
import os

from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel

from app.database.connection import (
    get_connection,
    get_active_db_name,
    set_active_db_name,
)
from app.services.console_log import log_stage
from app.services.schema_introspection import (
    refresh_schema_files,
)


router = APIRouter(
    prefix="/api",
    tags=["Schema"]
)

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


def _auto_regenerate_enabled():
    """Whether a schema refresh may also regenerate SQL when the fingerprint changed.

    Off by default. Set SQL_AUTO_REGENERATE=true to switch the second phase on — it costs
    several LLM calls per changed target and rewrites live .sql files, so it stays opt-in
    while the schema side is still being worked on.
    """

    return os.getenv("SQL_AUTO_REGENERATE", "false").strip().lower() in _TRUTHY


class DbConfigRequest(BaseModel):
    db_name: str


# ============================================================
# GET / SET ACTIVE DATABASE NAME
# ============================================================

@router.get("/db-config")
def read_db_config():

    return {
        "success": True,
        "db_name": get_active_db_name(),
    }


@router.post("/db-config")
def update_db_config(payload: DbConfigRequest):

    db_name = payload.db_name.strip()

    if not db_name:
        raise HTTPException(
            status_code=400,
            detail="db_name must not be empty."
        )

    previous_db_name = get_active_db_name()
    set_active_db_name(db_name)

    log_stage("Database", f"switched: {previous_db_name} -> {db_name}", ok=True)

    return {
        "success": True,
        "db_name": db_name,
    }


# ============================================================
# REFRESH SCHEMA + HINT FILES FOR THE ACTIVE DATABASE.
#
# A refresh runs in two phases. First, introspection: read the catalogue and write
# schema.txt / hints.txt / structure_fingerprint.txt. Then, if the structural fingerprint
# differs from the one a target's SQL was last generated from, that target's SQL is
# regenerated (sql_workflow.generate_sql_if_schema_changed). A target whose fingerprint
# still matches is left alone, so an unchanged database costs no LLM calls at all.
#
# The second phase is OFF by default: a refresh is pure introspection unless
# SQL_AUTO_REGENERATE=true. The fingerprint comparison still happens either way and is
# still reported, so you can see exactly what WOULD have been regenerated before paying
# for it — the second phase costs several LLM calls per changed target and rewrites live
# .sql files.
# ============================================================


def _maybe_regenerate_sql(result):
    """Run the SQL agent pipeline, but only when SQL_AUTO_REGENERATE is switched on.

    sql_workflow is imported lazily here on purpose: it pulls in langgraph, and the
    schema phase has to keep working whether or not that dependency is installed yet.
    """

    if not _auto_regenerate_enabled():
        would_run = (
            "fingerprint changed — regeneration WOULD run"
            if result["fingerprint_changed"]
            else "fingerprint unchanged — nothing would run"
        )
        log_stage("SQL agent", f"disabled (SQL_AUTO_REGENERATE): {would_run}")

        return {
            "disabled": True,
            "fingerprint_changed": result["fingerprint_changed"],
        }

    try:
        from app.services.sql_workflow import (
            generate_sql_if_schema_changed,
            SqlAgentError,
        )
    except ImportError as exc:
        logger.warning("SQL regeneration is enabled but unavailable: %s", exc)
        return {"error": f"SQL workflow could not be imported: {exc}"}

    try:
        return generate_sql_if_schema_changed(result["fingerprint"])

    except SqlAgentError as exc:
        # Schema/hints were still written successfully — only the regeneration step
        # failed to even run (e.g. business_rules.md missing, or no LLM key yet).
        # Report that separately rather than turning a successful refresh into a 500.
        logger.warning("Schema refreshed, but SQL regeneration could not run: %s", exc)
        return {"error": str(exc)}

@router.post("/schema/refresh")
def refresh_schema():

    connection = None

    try:
        db_name = get_active_db_name()

        if not db_name:
            raise HTTPException(
                status_code=400,
                detail="No database is configured. Set one via /api/db-config first."
            )

        connection = get_connection()

        result = refresh_schema_files(connection, db_name)

        # The SQL agent pipeline is LLM calls and file I/O only — it needs none of the
        # database connection, so it's released before that (potentially multi-minute)
        # work starts rather than held open and idle for the duration.
        connection.close()
        connection = None

        sql_regeneration = _maybe_regenerate_sql(result)

        return {
            "success": True,
            **result,
            "sql_regeneration": sql_regeneration,
        }

    except HTTPException:
        raise

    except ValueError as exc:
        logger.warning("Unable to refresh schema: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database configuration is invalid or incomplete."
        ) from exc

    except Exception:
        logger.exception("Unable to refresh schema")
        raise HTTPException(
            status_code=500,
            detail="Unable to read the database schema. Check the server logs."
        )

    finally:

        if connection:
            connection.close()
