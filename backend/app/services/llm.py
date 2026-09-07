import json
import os
from pathlib import Path

import requests

from dotenv import load_dotenv

from app.prompts.prompt import DELAY_ANALYSIS_PROMPT


load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

BUSINESS_RULES_FILE = BASE_DIR / "prompts" / "business_rules.md"


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_MODEL = "openai/gpt-oss-120b"

REQUEST_TIMEOUT_SECONDS = 60


class LLMUnavailable(Exception):
    """Raised when the analysis cannot be produced."""


# ============================================================
# PROMPT
# ============================================================

def build_system_prompt():

    """
    Business rules first, task instructions second. The rules are
    authoritative, so they frame everything that follows.
    """

    if not BUSINESS_RULES_FILE.exists():

        raise LLMUnavailable(
            f"Business rules file not found: {BUSINESS_RULES_FILE}"
        )

    business_rules = BUSINESS_RULES_FILE.read_text(
        encoding="utf-8"
    )

    return f"{business_rules}\n\n---\n\n{DELAY_ANALYSIS_PROMPT}"


# ============================================================
# GROQ CALL
# ============================================================

def analyze_well_delay(investigation):

    """
    Send the investigation evidence to Groq and return a short
    prose explanation of the well's delay.
    """

    api_key = os.getenv("GROK_KEY")

    if not api_key:

        raise LLMUnavailable(
            "GROK_KEY is not configured."
        )

    model = os.getenv("LLM_MODEL") or DEFAULT_MODEL

    payload = {

        "model": model,

        # Deterministic: the same evidence must always produce the
        # same explanation, since this feeds delay attribution.
        "temperature": 0,

        "max_completion_tokens": 900,

        "messages": [
            {
                "role": "system",
                "content": build_system_prompt()
            },
            {
                "role": "user",
                "content": (
                    "Well investigation evidence:\n\n"
                    + json.dumps(investigation, indent=2)
                )
            }
        ]
    }

    try:

        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS
        )

    except requests.exceptions.RequestException as exc:

        raise LLMUnavailable(
            f"Could not reach Groq: {exc}"
        ) from exc

    if response.status_code != 200:

        raise LLMUnavailable(
            f"Groq returned {response.status_code}: {response.text[:300]}"
        )

    try:

        body = response.json()

        content = body["choices"][0]["message"]["content"]

    except (ValueError, KeyError, IndexError) as exc:

        raise LLMUnavailable(
            f"Unexpected Groq response shape: {exc}"
        ) from exc

    content = (content or "").strip()

    if not content:

        raise LLMUnavailable(
            "Groq returned an empty analysis."
        )

    return content
