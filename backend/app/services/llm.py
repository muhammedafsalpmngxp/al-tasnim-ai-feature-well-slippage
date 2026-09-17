"""
Single point of contact with OpenAI for every LLM-driven agent in this app:
- the delay-analysis answering agent below (analyze_well_delay)
- the SQL generation and verification agents (app/services/sql_agent.py,
  app/services/sql_verifier_agent.py), which import call_llm() and OPENAI_FAST_MODEL
  from here rather than calling OpenAI themselves.

Two models, chosen by task:
    OPENAI_MODEL       — delay-analysis answering. One call per request, user-facing
                         prose, worth spending a stronger/slower model on.
    OPENAI_FAST_MODEL   — the whole SQL agent pipeline (generation + verification), which
                         can run several calls per target across the retry loop, so a
                         faster/cheaper model keeps that loop responsive.
"""

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from app.prompts.prompt import DELAY_ANALYSIS_PROMPT
from app.services.console_log import log_stage


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

BUSINESS_RULES_FILE = BASE_DIR / "prompts" / "business_rules.md"
SLIPPAGE_RULES_FILE = BASE_DIR / "prompts" / "slippage.md"

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_FAST_MODEL = os.getenv("OPENAI_FAST_MODEL", OPENAI_MODEL)
REQUEST_TIMEOUT_SECONDS = 120


class LLMUnavailable(Exception):
    """Raised when an OpenAI chat completion cannot be produced."""


# ============================================================================
# SHARED OPENAI CALL — every agent in this app goes through this one function
# ============================================================================

def call_llm(
    system_prompt,
    user_content,
    model=None,
    temperature=1,
    max_completion_tokens=2048,
    log_label=None,
):
    """Send one system+user message pair to OpenAI and return the assistant's text.

    `model` defaults to OPENAI_MODEL when not given; the SQL agents pass
    OPENAI_FAST_MODEL explicitly instead.

    `log_label` — when given (e.g. "sql_author", "verifier"), prints one "LLM" console
    line reporting which model answered and how long it took, once the call succeeds.
    Omit it for a call that shouldn't show up in the pipeline log (there isn't one yet,
    but this keeps that decision at the call site rather than hardcoded here).
    """

    if not OPENAI_API_KEY:
        raise LLMUnavailable("OpenAI API key is not configured. Set OPENAI_API_KEY.")

    resolved_model = model or OPENAI_MODEL

    payload = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_completion_tokens": max_completion_tokens,
    }

    started_at = time.monotonic()

    try:
        response = requests.post(
            OPENAI_CHAT_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        raise LLMUnavailable(f"Could not reach OpenAI: {exc}") from exc

    if not response.ok:
        raise LLMUnavailable(f"OpenAI returned {response.status_code}: {response.text[:500]}")

    try:
        message = response.json()["choices"][0]["message"]
        content = message.get("content")

        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            )
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMUnavailable(f"Unexpected OpenAI response shape: {exc}") from exc

    content = (content or "").strip()

    if not content:
        raise LLMUnavailable("OpenAI returned an empty response.")

    if log_label:
        elapsed = time.monotonic() - started_at
        log_stage("LLM", f"llm: {log_label} -> {resolved_model} in {elapsed:.1f}s")

    return content


# ============================================================================
# DELAY-ANALYSIS ANSWERING AGENT
# ============================================================================

def build_system_prompt():
    """Combine the authoritative rules and task prompt for the delay-analysis LLM."""

    for rules_file in (BUSINESS_RULES_FILE, SLIPPAGE_RULES_FILE):
        if not rules_file.exists():
            raise LLMUnavailable(f"Prompt rules file not found: {rules_file}")

    business_rules = BUSINESS_RULES_FILE.read_text(encoding="utf-8")
    slippage_rules = SLIPPAGE_RULES_FILE.read_text(encoding="utf-8")

    return f"""You are analysing a well-delay investigation.

Use all source documents below. The business rules and slippage rules define
the authoritative meaning of dates, milestones, ownership, and consequences.
The task prompt defines the required analysis and response format. Apply all
of them to the JSON evidence supplied by the user. Never invent facts that are
absent from the evidence.

<business_rules>
{business_rules}
</business_rules>

<slippage_rules>
{slippage_rules}
</slippage_rules>

<analysis_task>
{DELAY_ANALYSIS_PROMPT}
</analysis_task>"""


def analyze_well_delay(investigation):
    """Send investigation evidence to OpenAI and return the delay analysis."""

    well_id = investigation.get("well_id") if isinstance(investigation, dict) else None

    analysis = call_llm(
        system_prompt=build_system_prompt(),
        user_content="Well investigation evidence:\n\n" + json.dumps(
            investigation, indent=2, default=str
        ),
        model=OPENAI_MODEL,
        temperature=1,
        # DELAY_ANALYSIS_PROMPT requires listing every entry in `delayed_activities`,
        # not a summary — a well with many delayed tasks needs headroom beyond a short
        # narrative, or the list truncates mid-way and silently drops tasks/crews.
        max_completion_tokens=4096,
        log_label="delay_analysis",
    )

    log_stage("Answer", f"answer ok [well {well_id}]: {len(analysis)} chars", ok=True)

    return analysis
