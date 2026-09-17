"""
SQL PLANNER AGENT.

Runs once per target, before any SQL is written. Reads the same context block as the other
agents (schema + hints + business rules + slippage rules + SQL examples + validation
policy) and returns a plain-text plan: which tables are needed and at what grain, how they
join and with what data types, which source column supplies each required output column,
which values need decoding, and what could not be resolved from the schema.

The point is to split one hard job into two easier ones. Without this, the author agent
has to search a whole schema AND write several hundred lines of T-SQL in a single call,
and the searching is what it tends to get wrong — an invented column name, a join onto a
non-key column, a history table used without de-duplication. The planner does the reading;
the author translates a decided plan into SQL.

The plan is produced once and reused across retries. A retry is a fix to the SQL, not a
fresh decision about which tables to use, so re-planning each round would spend a call to
re-derive something already settled and would let the target drift between attempts.

A planning failure is not fatal: the caller may proceed with no plan, in which case the
author works straight from the schema exactly as it did before this agent existed.

This module knows nothing about LangGraph or retries — it is a single pure function
wrapping one LLM call. Orchestration lives in sql_workflow.py.
"""

import os

from app.prompts.prompt import SQL_PLANNING_PROMPT
from app.services.console_log import log_stage
from app.services.llm import call_llm, OPENAI_FAST_MODEL


SQL_PLANNER_TEMPERATURE = float(os.getenv("SQL_PLANNER_TEMPERATURE", "0.1"))

_EXPECTED_HEADINGS = ("## TABLES", "## COLUMNS")


def _looks_like_a_plan(text):
    """A usable plan names tables and maps columns. Anything else is treated as no plan.

    Cheap structural check only — the plan is read by another model, not parsed by code,
    so there is nothing to gain from validating it strictly. This just catches a response
    that came back empty or as a refusal, so the author is not handed noise and told to
    treat it as decided.
    """

    if not text:
        return False

    upper = text.upper()

    return all(heading in upper for heading in _EXPECTED_HEADINGS)


def plan_sql(context_block, target_description, target=None):
    """Returns the plan text, or None when no usable plan could be produced.

    Never raises: this step is an optimisation, and the pipeline stays able to run without
    it. `target` is optional and used only for the console log line.
    """

    task_prompt = SQL_PLANNING_PROMPT.format(
        target_description=target_description,
    )
    system_prompt = f"{context_block}\n\n<task>\n{task_prompt}\n</task>"

    try:
        plan = call_llm(
            system_prompt=system_prompt,
            user_content="Produce the plan now.",
            model=OPENAI_FAST_MODEL,
            temperature=SQL_PLANNER_TEMPERATURE,
            max_completion_tokens=2048,
            log_label="planner",
        )

    except Exception as exc:
        # Deliberately broad: a planning failure must never be able to stop the SQL
        # pipeline, because the author can still work from the schema alone.
        if target is not None:
            log_stage("Planner", f"planning failed [{target}]: {exc}", ok=False)

        return None

    plan = (plan or "").strip()

    if not _looks_like_a_plan(plan):
        if target is not None:
            log_stage(
                "Planner",
                f"unusable plan [{target}]: no TABLES/COLUMNS sections, continuing without one",
                ok=False,
            )

        return None

    if target is not None:
        log_stage("Planner", f"plan ready [{target}]: {len(plan)} chars", ok=True)

    return plan
