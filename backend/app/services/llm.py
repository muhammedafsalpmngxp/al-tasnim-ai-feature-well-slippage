import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
from app.prompts.prompt import DELAY_ANALYSIS_PROMPT


load_dotenv(BASE_DIR / ".env")

BUSINESS_RULES_FILE = BASE_DIR / "prompts" / "business_rules.md"
SLIPPAGE_RULES_FILE = BASE_DIR / "prompts" / "slippage.md"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or os.getenv("GROK_KEY") or "").strip()
GROQ_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
REQUEST_TIMEOUT_SECONDS = 120


class LLMUnavailable(Exception):
    """Raised when the Groq delay analysis cannot be produced."""


def build_system_prompt():
    """Combine the authoritative rules and task prompt for the LLM."""
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
    """Send investigation evidence to Groq and return the delay analysis."""
    if not GROQ_API_KEY:
        raise LLMUnavailable("Groq API key is not configured. Set GROK_KEY or GROQ_API_KEY.")

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {
                "role": "user",
                "content": "Well investigation evidence:\n\n" + json.dumps(
                    investigation, indent=2, default=str
                ),
            },
        ],
        "temperature": 1,
        "reasoning_effort": "low",
        "max_completion_tokens": 2048,
        "stream": False,
    }

    try:
        response = requests.post(
            GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        raise LLMUnavailable(f"Could not reach Groq: {exc}") from exc

    if not response.ok:
        raise LLMUnavailable(f"Groq returned {response.status_code}: {response.text[:500]}")

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
        raise LLMUnavailable(f"Unexpected Groq response shape: {exc}") from exc

    content = (content or "").strip()
    if not content:
        raise LLMUnavailable("Groq returned an empty analysis.")

    return content