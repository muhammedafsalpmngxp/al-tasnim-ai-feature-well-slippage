"""
SQL VERIFIER AGENT.

Checks one generated query for business-logic correctness: does it use real
tables/columns, does it match the target's output contract, does its NULL/deadline/
variance handling follow business_rules.md, slippage.md and milestone_rules.md, and is it
structurally sound (de-duplication, guarded string parsing, LEFT JOIN for optional data).
This is a judgment call, so — unlike the validation agent — it is an LLM call.

This module knows nothing about LangGraph or retries — it is a single pure function
wrapping one LLM call and parsing its verdict. Orchestration lives in sql_workflow.py.
"""

import os
import re

from app.prompts.prompt import SQL_VERIFICATION_PROMPT
from app.services.console_log import log_stage
from app.services.llm import call_llm, LLMUnavailable, OPENAI_FAST_MODEL


SQL_VERIFIER_TEMPERATURE = float(os.getenv("SQL_VERIFIER_TEMPERATURE", "0.1"))


def _parse_verdict(response_text):
    """Returns (passed: bool, reason: str | None) from the agent's PASS/FAIL response."""

    if re.search(r"VERDICT:\s*PASS", response_text, re.IGNORECASE):
        return True, None

    reason_match = re.search(r"REASON:\s*(.+)", response_text, re.IGNORECASE | re.DOTALL)
    reason = reason_match.group(1).strip() if reason_match else response_text.strip()

    return False, reason


def verify_sql(context_block, target_description, sql_text, target=None):
    """Returns (passed: bool, reason: str | None). Raises LLMUnavailable if the call fails.

    `target` is optional and used only for the console log line — omit it to verify
    silently.
    """

    task_prompt = SQL_VERIFICATION_PROMPT.format(
        target_description=target_description,
        sql_under_review=sql_text,
    )
    system_prompt = f"{context_block}\n\n<task>\n{task_prompt}\n</task>"

    response = call_llm(
        system_prompt=system_prompt,
        user_content="Review the SQL now.",
        model=OPENAI_FAST_MODEL,
        temperature=SQL_VERIFIER_TEMPERATURE,
        max_completion_tokens=1024,
        log_label="verifier",
    )

    passed, reason = _parse_verdict(response)

    if target is not None:
        verdict = "passed" if passed else "rejected"
        detail = f"verify: {verdict} [{target}]" + (f" -> {reason}" if reason else "")
        log_stage("Verifier", detail, ok=passed)

    return passed, reason
