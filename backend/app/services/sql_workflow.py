"""
LangGraph workflow connecting the four SQL agents:

    plan      (sql_planner_agent.py — LLM)     decides which tables/columns the query needs
        v                                      (once per run; retries do not come back here)
    generate  (sql_agent.py — LLM)             writes one candidate query from that plan
        v
    verify    (sql_verifier_agent.py — LLM)    checks it against business/slippage logic
        |  fail -> back to generate, with the reviewer's feedback, until max attempts
        v pass
    validate  (sql_validation_agent.py — code) checks it against SQL_VALIDATION_POLICY
        |  fail -> back to generate, with the failure reason, until max attempts
        v pass
    write             backs up the current file, then atomically replaces it

This module owns everything the agents themselves do not: the LangGraph state, nodes and
edges, loading the shared context (business rules, slippage rules, milestone rules, live
schema/hints, the validation policy) once per run, and writing the result to disk. The
three agent modules are pure functions — this is the only place that knows about retries,
attempt budgets, or LangGraph at all.

A successful run updates the file the app actually runs — `calculation.sql`,
`investigation.sql`, or `slipped_wells.sql` — in place, after backing up whatever was
there to `backend/sql/backups/`. A run that exhausts its attempts leaves the existing
file untouched and reports every attempt's failure reason, so a human can see exactly
what went wrong. (An earlier version of this module wrote to a separate "_new.sql"
candidate file instead of updating in place; that was reverted — direct update, with the
backup as the safety net, is the current design.)

generate_sql_if_schema_changed() (bottom of this file) is what a schema refresh calls:
it compares the schema's current structural fingerprint against the one each target's
SQL was generated from, and only runs this whole pipeline for a target whose schema
actually changed — refreshing the schema is cheap even when regeneration isn't needed.

Env vars (all optional, sensible defaults):
    SQL_AGENT_MAX_RETRIES   total generation attempts per target, across both the
                            verifier and the validator failing (default 3)

All three LLM agents call OpenAI's OPENAI_FAST_MODEL (app/services/llm.py) — the whole SQL
pipeline can run several calls per target across the retry loop, so a faster/cheaper
model keeps it responsive. Per-agent temperature env vars (SQL_PLANNER_TEMPERATURE,
SQL_AGENT_TEMPERATURE, SQL_VERIFIER_TEMPERATURE) are read by sql_planner_agent.py /
sql_agent.py / sql_verifier_agent.py themselves, not here.
"""

import os
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END

from app.database.connection import get_active_db_name
from app.prompts.prompt import SQL_VALIDATION_POLICY
from app.services.console_log import log_stage
from app.services.llm import LLMUnavailable
from app.services.sql_planner_agent import plan_sql
from app.services.sql_agent import generate_sql
from app.services.sql_verifier_agent import verify_sql
from app.services.sql_validation_agent import validate_sql


BASE_DIR = Path(__file__).resolve().parents[2]
SQL_DIR = BASE_DIR / "sql"
SCHEMA_DIR = BASE_DIR / "schema"
PROMPTS_DIR = BASE_DIR / "prompts"
BACKUP_DIR = SQL_DIR / "backups"

BUSINESS_RULES_FILE = PROMPTS_DIR / "business_rules.md"
SLIPPAGE_RULES_FILE = PROMPTS_DIR / "slippage.md"
MILESTONE_RULES_FILE = PROMPTS_DIR / "milestone_rules.md"

SQL_AGENT_MAX_RETRIES = max(1, int(os.getenv("SQL_AGENT_MAX_RETRIES", "3")))

TARGET_SPECS = {
    "investigation": {
        "output_file": SQL_DIR / "investigation.sql",
        "description": (
            "investigation.sql — one row per current task for a single well, used to "
            "explain why that well is delayed. Must begin with "
            "'DECLARE @WellId INT = 37857;' followed by "
            "'DECLARE @Today DATE = CAST(GETDATE() AS DATE);' verbatim (the well id "
            "value does not matter — it is replaced at runtime), because the service "
            "layer rewrites the well id by regex before running the query."
        ),
    },
    "slipped_wells": {
        "output_file": SQL_DIR / "slipped_wells.sql",
        "description": (
            "slipped_wells.sql — one row per currently slipped well (not yet completed "
            "and failing at least one milestone), ordered by urgency, used to populate "
            "the dashboard's slipped-wells list."
        ),
    },
    "calculation": {
        "output_file": SQL_DIR / "calculation.sql",
        "description": (
            "calculation.sql — dashboard KPI counts. Must return exactly one row with "
            "exactly two columns: total_wells (COUNT of every well) and live_wells "
            "(COUNT of wells where the completion date column is NULL, i.e. not yet "
            "completed). No grouping, no filtering beyond that — one summary row."
        ),
    },
}


class SqlAgentError(Exception):
    """Raised when the pipeline cannot even attempt to run (missing input files, etc.)."""


class SqlPipelineState(TypedDict, total=False):
    target: str
    context_block: str
    plan: Optional[str]

    current_sql: str
    attempt: int
    max_attempts: int

    generation_error: Optional[str]
    verify_passed: bool
    verify_reason: Optional[str]
    safety_passed: bool
    safety_reason: Optional[str]

    history: list
    status: str
    output_file: Optional[str]
    backup_file: Optional[str]


# ============================================================================
# CONTEXT LOADING
# ============================================================================

def _read_required(path):
    if not path.exists():
        raise SqlAgentError(f"Required file not found: {path}")

    text = path.read_text(encoding="utf-8").strip()

    if not text:
        raise SqlAgentError(f"Required file is empty: {path}")

    return text


def _load_schema_and_hints():
    db_name = get_active_db_name()

    if not db_name:
        raise SqlAgentError(
            "No database is configured. Set one via /api/db-config first."
        )

    schema_path = SCHEMA_DIR / "schema.txt"
    hints_path = SCHEMA_DIR / "hints.txt"

    if not schema_path.exists() or not hints_path.exists():
        raise SqlAgentError(
            "schema.txt / hints.txt not found. Run POST /api/schema/refresh first."
        )

    return (
        schema_path.read_text(encoding="utf-8").strip(),
        hints_path.read_text(encoding="utf-8").strip(),
    )


def _build_context_block():
    """Everything all three agents share: the same rules, the same examples, the same
    live schema/hints, the same validation policy. Assembled once per run.

    The validation policy is included here — not just enforced later by the validation
    agent — so the generation agent tries to satisfy it upfront and the verifier agent
    can flag an obvious violation in its own reasoning, instead of every policy violation
    being caught only on the last, hard-coded gate.
    """

    business_rules = _read_required(BUSINESS_RULES_FILE)
    slippage_rules = _read_required(SLIPPAGE_RULES_FILE)
    milestone_rules = _read_required(MILESTONE_RULES_FILE)
    schema_text, hints_text = _load_schema_and_hints()

    return f"""<business_rules>
{business_rules}
</business_rules>

<slippage_rules>
{slippage_rules}
</slippage_rules>

<milestone_and_task_rules>
{milestone_rules}
</milestone_and_task_rules>


<validation_policy>
{SQL_VALIDATION_POLICY}
</validation_policy>


<schema>
{schema_text}
</schema>

<hints>
{hints_text}
</hints>"""


# ============================================================================
# GRAPH NODES
# ============================================================================

def _node_plan(state: SqlPipelineState) -> dict:
    """Decides what the query must contain, once, before any SQL is written.

    Runs only on entry — the retry edges go back to `generate`, not here. A retry fixes a
    specific defect in the SQL; which tables to use was already settled, and re-deciding it
    each round would let the query drift between attempts instead of converging.

    plan_sql never raises: if planning fails, `plan` stays None and the author works
    straight from the schema, exactly as it did before this node existed.
    """

    target = state["target"]

    plan = plan_sql(
        context_block=state["context_block"],
        target_description=TARGET_SPECS[target]["description"],
        target=target,
    )

    return {"plan": plan}


def _node_generate(state: SqlPipelineState) -> dict:
    is_retry = state.get("attempt", 0) > 0
    attempt = state.get("attempt", 0) + 1
    target = state["target"]
    description = TARGET_SPECS[target]["description"]

    feedback = None

    if is_retry:
        # The validator always runs after (and therefore overrides) the verifier, so
        # its reason is checked first.
        feedback = (
            state.get("safety_reason")
            or state.get("verify_reason")
            or state.get("generation_error")
            or "The previous attempt was rejected for an unspecified reason."
        )

    try:
        sql = generate_sql(
            context_block=state["context_block"],
            target_description=description,
            previous_sql=state.get("current_sql") if is_retry else None,
            feedback=feedback,
            target=target,
            attempt=attempt,
            plan=state.get("plan"),
        )
    except LLMUnavailable as exc:
        return {
            "attempt": attempt,
            "generation_error": f"SQL generation call failed: {exc}",
            "verify_reason": None,
            "safety_reason": None,
        }

    return {
        "attempt": attempt,
        "current_sql": sql,
        "generation_error": None,
        "verify_reason": None,
        "safety_reason": None,
    }


def _node_verify(state: SqlPipelineState) -> dict:
    target = state["target"]
    description = TARGET_SPECS[target]["description"]

    try:
        passed, reason = verify_sql(
            context_block=state["context_block"],
            target_description=description,
            sql_text=state["current_sql"],
            target=target,
        )
    except LLMUnavailable as exc:
        passed, reason = False, f"SQL verification call failed: {exc}"

    return {
        "verify_passed": passed,
        "verify_reason": reason,
        "history": state.get("history", []) + [
            {"attempt": state["attempt"], "stage": "verify", "passed": passed, "reason": reason}
        ],
    }


def _node_validate(state: SqlPipelineState) -> dict:
    target = state["target"]
    passed, reason = validate_sql(state["current_sql"], target)

    verdict = "ok" if passed else "rejected"
    detail = f"validation {verdict} [{target}]" + (f" -> {reason}" if reason else "")
    log_stage("Validator", detail, ok=passed)

    return {
        "safety_passed": passed,
        "safety_reason": reason,
        "history": state.get("history", []) + [
            {"attempt": state["attempt"], "stage": "validate", "passed": passed, "reason": reason}
        ],
    }


def _backup_existing(path: Path):
    if not path.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"{path.stem}.{stamp}.sql"
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    return backup_path


def _write_sql_file(path: Path, sql_text: str):
    """Back up whatever is currently there, then atomically replace it — never a
    partial write. This is the LIVE file the app runs; the backup is the safety net
    that makes overwriting it in place recoverable if the new query turns out wrong."""

    backup_path = _backup_existing(path)

    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.stem}-",
        suffix=".tmp",
        delete=False,
    ) as file:
        file.write(sql_text.rstrip() + "\n")
        temp_path = Path(file.name)

    temp_path.replace(path)

    return backup_path


def _node_finalize_success(state: SqlPipelineState) -> dict:
    target = state["target"]
    output_file = TARGET_SPECS[target]["output_file"]
    backup_file = _write_sql_file(output_file, state["current_sql"])

    log_stage("Write", f"write ok [{target}]: {output_file}", ok=True)

    return {
        "status": "success",
        "output_file": str(output_file),
        "backup_file": str(backup_file) if backup_file else None,
    }


def _node_finalize_failure(state: SqlPipelineState) -> dict:
    target = state["target"]

    log_stage(
        "Write",
        f"write skipped [{target}]: exhausted {state['max_attempts']} attempts, kept the existing file",
        ok=False,
    )

    return {
        "status": "failed",
        "output_file": None,
        "backup_file": None,
    }


# ============================================================================
# ROUTING
# ============================================================================

def _route_after_generate(state: SqlPipelineState) -> str:
    if state.get("generation_error"):
        return "retry" if state["attempt"] < state["max_attempts"] else "fail"

    return "verify"


def _route_after_verify(state: SqlPipelineState) -> str:
    if state.get("verify_passed"):
        return "validate"

    return "retry" if state["attempt"] < state["max_attempts"] else "fail"


def _route_after_validate(state: SqlPipelineState) -> str:
    if state.get("safety_passed"):
        return "success"

    return "retry" if state["attempt"] < state["max_attempts"] else "fail"


def _build_graph():
    graph = StateGraph(SqlPipelineState)

    graph.add_node("plan", _node_plan)
    graph.add_node("generate", _node_generate)
    graph.add_node("verify", _node_verify)
    graph.add_node("validate", _node_validate)
    graph.add_node("finalize_success", _node_finalize_success)
    graph.add_node("finalize_failure", _node_finalize_failure)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "generate")

    graph.add_conditional_edges(
        "generate",
        _route_after_generate,
        {"verify": "verify", "retry": "generate", "fail": "finalize_failure"},
    )
    graph.add_conditional_edges(
        "verify",
        _route_after_verify,
        {"validate": "validate", "retry": "generate", "fail": "finalize_failure"},
    )
    graph.add_conditional_edges(
        "validate",
        _route_after_validate,
        {"success": "finalize_success", "retry": "generate", "fail": "finalize_failure"},
    )

    graph.add_edge("finalize_success", END)
    graph.add_edge("finalize_failure", END)

    return graph.compile()


_COMPILED_GRAPH = _build_graph()


# ============================================================================
# PUBLIC API
# ============================================================================

def generate_sql_for_target(target: str) -> dict:
    """Runs the full generate/verify/validate/write pipeline for one target.

    A successful run updates the live file the app runs (`calculation.sql` /
    `investigation.sql` / `slipped_wells.sql`) in place. Returns a plain dict (not the
    internal state) describing the outcome:
        status        "success" | "failed"
        attempts      how many generation attempts were made
        planned       whether the planner produced a usable plan for this run
        output_file   the file updated, when status == "success"
        backup_file   path of the previous version's backup, when one existed
        history       every attempt's verify/validate result, oldest first
        last_reason   the most recent failure reason, when status == "failed"
    """

    if target not in TARGET_SPECS:
        raise SqlAgentError(
            f"Unknown SQL target '{target}'. Valid targets: {sorted(TARGET_SPECS)}"
        )

    context_block = _build_context_block()

    initial_state: SqlPipelineState = {
        "target": target,
        "context_block": context_block,
        "attempt": 0,
        "max_attempts": SQL_AGENT_MAX_RETRIES,
        "history": [],
    }

    final_state = _COMPILED_GRAPH.invoke(
        initial_state,
        config={"recursion_limit": SQL_AGENT_MAX_RETRIES * 6 + 10},
    )

    last_reason = (
        final_state.get("safety_reason")
        or final_state.get("verify_reason")
        or final_state.get("generation_error")
    )

    return {
        "target": target,
        "status": final_state.get("status", "failed"),
        "attempts": final_state.get("attempt", 0),
        "planned": bool(final_state.get("plan")),
        "output_file": final_state.get("output_file"),
        "backup_file": final_state.get("backup_file"),
        "history": final_state.get("history", []),
        "last_reason": last_reason,
        "final_sql": final_state.get("current_sql") if final_state.get("status") == "failed" else None,
    }


def run_sql_agent_pipeline(targets=None) -> dict:
    """Runs generate_sql_for_target for each target (default: all of them)."""

    selected = targets or list(TARGET_SPECS)
    unknown = [t for t in selected if t not in TARGET_SPECS]

    if unknown:
        raise SqlAgentError(f"Unknown SQL target(s): {unknown}. Valid: {sorted(TARGET_SPECS)}")

    results = {target: generate_sql_for_target(target) for target in selected}
    overall_success = all(r["status"] == "success" for r in results.values())

    return {"success": overall_success, "results": results}


# ============================================================================
# SCHEMA-CHANGE-TRIGGERED REGENERATION
# ============================================================================
#
# Connects a schema refresh to this pipeline: each target's SQL remembers the
# structural fingerprint (schema_introspection.compute_structural_fingerprint) it was
# generated from. Call generate_sql_if_schema_changed() with the fingerprint a fresh
# refresh just produced, and a target whose fingerprint still matches is left alone —
# no LLM calls, no write, no backup — so refreshing the schema only spends the several
# minutes/LLM calls this pipeline costs when a table or column actually changed.

def _generated_from_path(target):
    """Where a target records the fingerprint its current SQL was generated from.

    Not per-database, matching schema.txt/hints.txt/structure_fingerprint.txt: there is
    one live set of SQL files, so there is one record of what they were built from.
    Pointing the app at a different database changes the fingerprint, which is exactly
    what should trigger regeneration."""

    return SCHEMA_DIR / f"{target}_generated_from.txt"


def _read_generated_from_fingerprint(target):
    path = _generated_from_path(target)

    if not path.exists():
        return None

    return path.read_text(encoding="utf-8").strip() or None


def _write_generated_from_fingerprint(target, fingerprint):
    _generated_from_path(target).write_text(fingerprint, encoding="utf-8")


def generate_sql_if_schema_changed(schema_fingerprint, targets=None) -> dict:
    """For each target, regenerates its SQL only if `schema_fingerprint` differs from
    the fingerprint its current file was last successfully generated from.

    A target with no saved fingerprint yet (first run, or its last generation never
    succeeded) is always treated as changed, so it gets a first real attempt.
    """

    db_name = get_active_db_name()

    if not db_name:
        raise SqlAgentError("No database is configured. Set one via /api/db-config first.")

    selected = targets or list(TARGET_SPECS)
    unknown = [t for t in selected if t not in TARGET_SPECS]

    if unknown:
        raise SqlAgentError(f"Unknown SQL target(s): {unknown}. Valid: {sorted(TARGET_SPECS)}")

    results = {}

    for target in selected:
        previous_fingerprint = _read_generated_from_fingerprint(target)

        if previous_fingerprint == schema_fingerprint:
            results[target] = {"target": target, "changed": False, "status": "unchanged"}
            continue

        result = generate_sql_for_target(target)
        result["changed"] = True

        if result["status"] == "success":
            _write_generated_from_fingerprint(target, schema_fingerprint)

        results[target] = result

    return {
        "schema_fingerprint": schema_fingerprint,
        "results": results,
    }
