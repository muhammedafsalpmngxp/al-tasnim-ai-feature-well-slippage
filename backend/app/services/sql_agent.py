"""
SQL GENERATION AGENT.

Writes one candidate T-SQL query from a context block (schema + hints + business rules +
slippage rules + SQL examples + validation policy) and a target description. On a retry,
also receives the previous attempt and the reviewing agent's feedback, and is instructed
to fix exactly that rather than start over.

This module knows nothing about LangGraph, retries, or file writing — it is a single pure
function wrapping one LLM call. Orchestration lives in sql_workflow.py.
"""

import os
import re

from app.prompts.prompt import (
    SQL_GENERATION_PROMPT,
    SQL_GENERATION_PLAN_SECTION,
    SQL_GENERATION_RETRY_SECTION,
)
from app.services.console_log import log_stage
from app.services.llm import call_llm, LLMUnavailable, OPENAI_FAST_MODEL


SQL_AGENT_TEMPERATURE = float(os.getenv("SQL_AGENT_TEMPERATURE", "0.2"))


def _strip_code_fence(text):
    """Defensive: the prompt forbids markdown fences, but strip one if the model adds it."""

    text = text.strip()
    match = re.match(r"^```(?:sql)?\s*\n(.*?)\n```$", text, re.DOTALL | re.IGNORECASE)

    if match:
        return match.group(1).strip()

    return text


def generate_sql(
    context_block,
    target_description,
    previous_sql=None,
    feedback=None,
    target=None,
    attempt=None,
    plan=None,
):
    """Returns the generated SQL text. Raises LLMUnavailable if the call fails.

    `feedback` (and `previous_sql`) should be omitted on the first attempt, and set to the
    prior attempt's rejection reason on a retry.

    `plan` is the sql_planner_agent's worked-out table/column plan, when one was produced.
    It is optional by design — with no plan the author works straight from the schema, the
    way it did before the planner existed.

    `target`/`attempt` are optional and used only for the console log line — omit them to
    generate silently.
    """

    if plan:
        plan_section = SQL_GENERATION_PLAN_SECTION.format(plan=plan)
    else:
        plan_section = ""

    if feedback:
        retry_section = SQL_GENERATION_RETRY_SECTION.format(
            previous_sql=previous_sql or "(no SQL was produced)",
            feedback=feedback,
        )
    else:
        retry_section = ""

    task_prompt = SQL_GENERATION_PROMPT.format(
        target_description=target_description,
        plan_section=plan_section,
        retry_section=retry_section,
    )
    system_prompt = f"{context_block}\n\n<task>\n{task_prompt}\n</task>"

    raw_sql = call_llm(
        system_prompt=system_prompt,
        user_content="Generate the SQL now.",
        model=OPENAI_FAST_MODEL,
        temperature=SQL_AGENT_TEMPERATURE,
        max_completion_tokens=4096,
        log_label="sql_author",
    )

    sql = _strip_code_fence(raw_sql)

    if target is not None and attempt is not None:
        log_stage("SQL Author", f"SQL[{target} try{attempt}]: {len(sql)} chars")

    return sql
