"""
Groq-backed narration of deterministic well-slippage evidence.

Architecture:

    SQL
      -> deterministic evidence
      -> Python / ai_evidence
      -> this module
      -> LLM narration
      -> React dashboard

IMPORTANT:
- SQL/Python calculate facts.
- The LLM only explains supplied facts.
- The LLM must never calculate, infer, repair, reinterpret,
  or invent business values.

CURRENT PROVIDER:
    Groq

CURRENT MODEL:
    Read from GROQ_MODEL in .env (falls back to openai/gpt-oss-120b
    if unset). Changing models later is just editing .env — nothing
    in this file needs to change.

API KEY:
    Loaded from .env

Expected .env:
    api_key=YOUR_GROQ_API_KEY
    GROQ_MODEL=openai/gpt-oss-120b
"""

import sys
import json
import os

import requests
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

# LLM prose routinely contains characters outside the Windows default
# console codepage (cp1252) -- non-breaking hyphens, em dashes, smart
# quotes. Left alone, printing/logging that text on Windows crashes
# with UnicodeEncodeError. Force UTF-8 on stdio where the runtime
# supports it; harmless elsewhere.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Model selection lives in .env (GROQ_MODEL) so switching models is a
# config change, not a code change.
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()

REQUEST_TIMEOUT_SECONDS = 60

# Safety ceiling for the final rendered summary.
MAX_SUMMARY_CHARS = 4000


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """You are a drilling-operations reporting assistant for Al-Tasnim. Turn the supplied evidence JSON into clear prose. It is authoritative: SQL/Python already computed every date, delay, status, classification, score, count and mapping. You are a NARRATOR only, never a calculator, investigator, decision-maker, or data-cleaner.

RULES
1. Source of truth: use only facts explicitly in the JSON. No outside knowledge, no assumptions, no repairing or reinterpreting values. Null/missing means "not recorded" or "unavailable" -- never invented, never treated as 0.
2. Never calculate: no dates, date differences, days late/early, percentages, totals, shares, risk scores, progress, productivity, quantities, or rankings you derive yourself. Report every number exactly as supplied (delay_days 16 -> "16", not recomputed).
3. Never decide: DUE/NON-DUE status, delay ownership, project responsibility, activity causation, milestone/activity status, resource sufficiency, or whether something is suspicious or a data-quality issue -- those are the evidence layer's calls, not yours.
4. Well-level vs activity-level delay: risk.expected_delay_days plus risk.expected_delay_gate is the WELL's delay. Each delayed_activities[].delay_days belongs only to that activity. Never state an activity's delay as the well's delay -- report them as separate facts, e.g. "the well-level delay is 16 days at the Construction gate; the most delayed activity, LCCC1010, is 36 days late."
5. Milestones: use each one's own expected date, actual date, delay_days, variance_days and status exactly as supplied. delay_days = 0 is not delayed. actual = null means "not recorded". AHEAD_OF_SCHEDULE or a negative variance_days means early -- describe it as early/positive, never as delayed, overdue, suspicious, or a data-quality issue, however large the gap.
6. Construction is a schedule GATE, not a completion date. Its "actual" value is the rig-on date, used only to test whether the rig arrived by the deadline. Say "rig-on occurred on [date], satisfying the Construction gate" -- never "construction completed/occurred/finished on [date]".
7. Hook-up/completion: if eng_completion_date is null, do not claim the well is completed even if the hook-up deadline has passed -- say completion is not recorded.
8. Accountability, recorded reason, and remarks are three separate things -- never merge them into an unsupported causal claim. Accountability: reproduce the supplied DUE/NON-DUE classification exactly, never reversed or softened ("classified as DUE" / "classified as NON-DUE"). Recorded reason: state it as a recorded value ("Scope Change is recorded as the reason"), not as a cause ("caused the delay"). Remarks: report what they record ("the remarks record a scope change...") -- never as a cause of anything, and never simplified into a cleaner claim than the text supports (e.g. do not turn ambiguous well-type/artificial-lift/water-injection wording into "the well type changed to X" unless the evidence says exactly that).
9. Projects are evidence, not a basis for blame -- list them if relevant, but never infer which project (e.g. Location vs Flowline) owns the delay; only the supplied accountability classification does that.
10. WBS is a grouping, not an activity -- never call an activity code a WBS or vice versa, and never invent one from the other.
11. Missing identifiers (WBS, activity code, crew/employee/equipment IDs) mean "not recorded", never invented or guessed. RESOURCE_DATA_AVAILABLE means data exists -- it is NOT evidence of a shortage, insufficiency, or resource-caused delay; never claim otherwise without explicit evidence.
12. Productivity: report only if the evidence supplies a productivity value. Never derive it from hours, quantity, progress, duration, or counts.
13. Data quality: if data_quality.has_issue is true, name the supplied flags as a caveat -- do not invent extra problems, and do not turn a flag into an operational conclusion (e.g. "missing WBS mapping" does not mean "the activity is invalid").
14. Translate every SCREAMING_SNAKE_CASE enum and dq_* flag into plain English, e.g. AHEAD_OF_SCHEDULE -> "ahead of schedule", RED_DELAYED -> "significantly delayed", NOT_STARTED_LATE -> "not yet started and already late", dq_missing_wbs -> "missing WBS mapping". Never output a raw enum token.
15. Numbers: use supplied values exactly, written as numerals ("7", not "seven"). Never add or recompute a number.
16. Avoid causal/unsupported language ("caused by", "because of", "due to", "responsible for", "shortage", "likely", "probably", "appears to", "suggests") unless the evidence explicitly establishes that relationship. Never confuse ordinary "due" with the DUE/NON-DUE classification.
17. State each fact once -- no repeated delay values, data-quality flags, or accountability statements.

OUTPUT
Reply with the paragraph itself and nothing else -- no preamble, no sign-off, no JSON, no quotes around it. One flowing paragraph of at most 170 words, complete sentences, factual, concise but sufficiently detailed. No bullet points, no numbered lists, no markdown, no headings, no field names, no references to "the evidence" or these instructions.

PER-WELL ORDER (when supported): stage and the date establishing it -> every milestone with delay_days > 0 (gate, expected date, actual date or "not recorded", exact delay) -> early/on-schedule milestones -> the well-level delay and its gate -> accountability classification and recorded reason, kept separate from causality -> most delayed activities with their own delay_days, kept separate from the well-level figure -> what the remarks record, never as a cause -> projects, if useful -> the data-quality caveat and its flags. Skip anything the evidence does not support.

PORTFOLIO ORDER: use the supplied counts, percentages, leading reason(s), and comparison statement exactly as given -- never recompute or independently compare any of them.

The evidence layer owns the facts; Python owns the arithmetic; you own only the wording. When in doubt, say less rather than invent or interpret more."""


# ============================================================
# EXCEPTIONS
# ============================================================

class LLMUnavailable(RuntimeError):
    """Raised when the LLM cannot be reached or is not configured."""


# ============================================================
# API KEY
# ============================================================

def _api_key():
    """
    Read the API key from .env.

    Accepted names:
        api_key
        API_KEY
        GROQ_API_KEY
        groq_api_key
    """

    for name in (
        "api_key",
        "API_KEY",
        "GROQ_API_KEY",
        "groq_api_key",
    ):
        key = os.getenv(name)

        if key and key.strip():
            return key.strip()

    raise LLMUnavailable(
        "No Groq API key found. Set api_key in .env."
    )


# ============================================================
# MODEL COMPLETION
# ============================================================

def _complete(user_prompt, max_tokens):
    """
    Send one narration request to Groq.

    The model receives deterministic evidence and narration
    instructions only.
    """

    if not MODEL:
        raise LLMUnavailable(
            "No Groq model configured. Set GROQ_MODEL in .env."
        )

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],

        # Low temperature is appropriate for controlled
        # evidence-to-prose narration.
        "temperature": 0.2,

        "max_tokens": max_tokens,

        # Deliberately NOT response_format=json_object. Under JSON mode a
        # reply that hits max_tokens is rejected outright by Groq with
        # 400 json_validate_failed ("max completion tokens reached before
        # generating a valid document"), losing the whole summary. Plain
        # prose degrades to a shorter paragraph instead of failing, and
        # costs fewer tokens against the account's TPM limit.
    }

    # gpt-oss models support reasoning effort through Groq.
    # Low is appropriate because SQL/Python already perform
    # calculations and business logic.
    if "gpt-oss" in MODEL.lower():
        payload["reasoning_effort"] = "low"

    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    except requests.exceptions.RequestException as exc:
        raise LLMUnavailable(
            f"Could not reach Groq: {exc}"
        ) from exc

    if response.status_code != 200:
        raise LLMUnavailable(
            f"Groq returned {response.status_code}: "
            f"{response.text[:500]}"
        )

    try:
        body = response.json()

        content = (
            body["choices"][0]["message"]["content"]
            .strip()
        )

    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMUnavailable(
            "Unexpected response shape from Groq."
        ) from exc

    return _parse_summary(content)


# ============================================================
# RESPONSE PARSING
# ============================================================

def _parse_summary(content):
    """
    Normalise the model's reply into one paragraph.

    The model is asked for bare prose, but a reply that still arrives
    wrapped as {"summary": "..."} is unwrapped rather than shown raw.
    """

    text = None

    try:
        parsed = json.loads(content)

        if isinstance(parsed, dict):
            text = parsed.get("summary")

    except (json.JSONDecodeError, TypeError):
        pass

    if not isinstance(text, str) or not text.strip():
        text = content

    # Keep the UI output as one flowing paragraph.
    text = " ".join(text.split())

    if not text:
        raise LLMUnavailable(
            "Model returned no usable summary."
        )

    # Safety ceiling against malformed/runaway responses.
    if len(text) > MAX_SUMMARY_CHARS:
        text = (
            text[:MAX_SUMMARY_CHARS]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return text


# ============================================================
# PER-WELL NARRATIVE
# ============================================================

def summarize_well(ai_evidence):
    """
    Narrate ONE well from compact deterministic AI evidence.

    ai_evidence must be the output of:
        ai_evidence.build_ai_evidence()

    Do not pass raw SQL rows here.
    """

    if not isinstance(ai_evidence, dict):
        raise ValueError(
            "summarize_well() requires a dictionary of AI evidence."
        )

    evidence_json = json.dumps(
        ai_evidence,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )

    prompt = (
        "Deterministic evidence for ONE well is provided below. Every "
        "date, number, status, classification and delay has already "
        "been determined -- narrate it accurately. Do not calculate "
        "anything, infer causality, reinterpret remarks, change "
        "accountability, fill missing values, turn an activity delay "
        "into the well delay, or create facts that are not present.\n\n"
        f"EVIDENCE: {evidence_json}\n\n"
        "FIELD NOTES: stage.scenario is supplied, do not re-derive it. "
        "milestones[] each carry their own dates, delay_days and "
        "status. accountability is authoritative -- do not derive "
        "DUE/NON-DUE yourself. risk.expected_delay_days with "
        "risk.expected_delay_gate is the WELL-LEVEL delay. "
        "delayed_activities[] each have their OWN delay_days, never "
        "the well-level figure. remarks are operational evidence only, "
        "not causal unless an explicit causal field says so. "
        "data_quality carries only the flags actually set.\n\n"
        "TONE BY STAGE -- read this first, it governs the whole "
        "paragraph:\n"
        "* stage.scenario COMPLETED: this well is finished. Open the "
        "paragraph by saying plainly that the well is complete. Any "
        "historical milestone delays are resolved, not a current risk -- "
        "report them factually in the middle of the paragraph, then "
        "CLOSE with a sentence such as 'despite these delays, the well "
        "was completed overall' (adapt the wording, keep the meaning: "
        "finished, delays are in the past, no current alarm). This "
        "closing sentence is REQUIRED -- include it even if another, "
        "lower-priority point below must be shortened or dropped to fit "
        "the word limit.\n"
        "* risk.deadline_status NON_DUE and risk.risk_score null: this "
        "well is currently on track -- it has not missed its own "
        "current gate. Open the paragraph by saying plainly that the "
        "well is currently proceeding on schedule. Any activities listed "
        "are informational context, not a current problem -- do not "
        "call them 'at risk' or frame the well as troubled. This opening "
        "framing is REQUIRED even if other, lower-priority points below "
        "must be shortened or dropped to fit the word limit.\n"
        "* Neither of the above (the well is genuinely overdue right "
        "now): no special framing -- report the delay factually as "
        "usual.\n"
        "In every case, skip the well-level delay point below whenever "
        "risk.expected_delay_days is 0 or negative, rather than "
        "reporting a delay of zero or fewer than zero days.\n\n"
        "Write one paragraph in this order when supported: (1) the "
        "stage-tone opening above, then the date establishing the "
        "stage; (2) every milestone with delay_days > 0 -- gate, "
        "expected date, actual date or 'not recorded', exact delay; (3) "
        "early/on-schedule milestones when useful, never as delayed; "
        "(4) the well-level delay and its gate, when it is greater than "
        "0; (5) accountability classification and recorded reason, kept "
        "separate from causality -- omit this point entirely if "
        "risk.deadline_status is not DUE, since accountability for a "
        "delay does not apply where none exists; (6) most delayed "
        "activities with their own delay values, kept separate from the "
        "well-level figure; (7) what the remarks record, never as a "
        "cause; (8) projects if useful; (9) the data-quality caveat and "
        "its flags, kept brief -- name at most the 3 most notable flags "
        "rather than every one, so the required stage-tone framing is "
        "never crowded out; (10) for a COMPLETED well only, the required "
        "closing sentence from the tone guidance above. State each fact "
        "once; skip unsupported points, but never skip the required "
        "tone framing.\n\n"
        "Reply with the paragraph only -- no preamble, no markdown, no "
        "JSON. At most 170 words."
    )

    return _complete(
        prompt,
        max_tokens=900,
    )


# ============================================================
# PORTFOLIO HELPERS
# ============================================================

def _percent(part, whole):
    """
    Deterministically calculate a percentage.

    The LLM never performs this calculation.
    """

    if not whole:
        return None

    return round(part / whole * 100, 1)


def _normalise_reason_breakdown(reason_breakdown):
    """
    Convert a reason/count dictionary into a deterministic list.

    Expected input:

        {
            "Awaiting Manifold/MSV": 40,
            "SCR": 37,
            ...
        }
    """

    if not isinstance(reason_breakdown, dict):
        return []

    items = []

    for reason, count in reason_breakdown.items():

        if not isinstance(reason, str):
            continue

        if isinstance(count, bool):
            continue

        if isinstance(count, (int, float)):
            cleaned_reason = reason.strip()

            if not cleaned_reason:
                continue

            items.append(
                {
                    "reason": cleaned_reason,
                    "count": count,
                }
            )

    # Deterministic ordering:
    # highest supplied count first, then reason alphabetically.
    items.sort(
        key=lambda item: (
            -item["count"],
            item["reason"].lower(),
        )
    )

    return items


def build_portfolio_evidence(summary, reason_breakdown=None):
    """
    Build compact deterministic portfolio evidence.

    All arithmetic required by the narrative is performed here,
    outside the LLM.
    """

    if not isinstance(summary, dict):
        raise ValueError(
            "build_portfolio_evidence() requires a summary dictionary."
        )

    live = summary.get("live_wells") or 0
    due = summary.get("slipped_wells") or 0
    non_due = summary.get("non_due_wells") or 0
    not_slipped = summary.get("not_slipped_wells") or 0

    total_slipped = due + non_due

    reasons = _normalise_reason_breakdown(
        reason_breakdown
    )

    leading_reason = (
        reasons[0]
        if len(reasons) >= 1
        else None
    )

    second_reason = (
        reasons[1]
        if len(reasons) >= 2
        else None
    )

    # Deterministic comparison.
    if non_due > due:
        risk_balance = "NON_DUE_EXCEEDS_DUE"

    elif due > non_due:
        risk_balance = "DUE_EXCEEDS_NON_DUE"

    else:
        risk_balance = "DUE_AND_NON_DUE_ARE_EQUAL"

    return {
        "counts": {
            **summary,
            "total_slipped_wells": total_slipped,
        },

        "percentages_of_live_wells": {
            "total_slipped": _percent(
                total_slipped,
                live,
            ),
            "slipped_due": _percent(
                due,
                live,
            ),
            "slipped_non_due": _percent(
                non_due,
                live,
            ),
            "not_slipped": _percent(
                not_slipped,
                live,
            ),
        },

        "delay_reasons_for_non_due_wells": (
            reason_breakdown or {}
        ),

        "portfolio_comparison": {
            "due_vs_non_due": risk_balance,
            "leading_reason": leading_reason,
            "second_reason": second_reason,
        },
    }


# ============================================================
# PORTFOLIO NARRATIVE
# ============================================================

def summarize_portfolio(portfolio_evidence):
    """
    Narrate deterministic portfolio evidence.
    """

    if not isinstance(portfolio_evidence, dict):
        raise ValueError(
            "summarize_portfolio() requires a portfolio "
            "evidence dictionary."
        )

    evidence_json = json.dumps(
        portfolio_evidence,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )

    prompt = (
        "Deterministic portfolio evidence is provided below. Every "
        "count, percentage, leading reason and comparison statement "
        "has already been calculated by Python -- convert those "
        "supplied facts into readable prose. Do not calculate, "
        "recompute percentages, add counts, determine the leading "
        "reason yourself, independently compare due vs non-due counts, "
        "or infer causality.\n\n"
        f"EVIDENCE: {evidence_json}\n\n"
        "FIELD NOTES: total_wells is every well on record. live_wells "
        "are within the current detection scope. completed_wells are "
        "hooked-up wells outside that scope. slipped_wells are "
        "slipped and classified DUE. non_due_wells are slipped and "
        "classified NON-DUE. total_slipped_wells is already summed. "
        "not_slipped_wells are live wells with no milestone slip. "
        "percentages_of_live_wells are already computed. "
        "delay_reasons_for_non_due_wells are recorded reasons with "
        "their counts. portfolio_comparison is a precomputed "
        "due-vs-non-due comparison.\n\n"
        "Write one paragraph in this order: (1) total slipped wells "
        "vs live wells with the supplied percentage; (2) DUE slipped "
        "wells, count and percentage; (3) NON-DUE slipped wells, "
        "count and percentage; (4) the supplied leading non-due "
        "reason and second reason if present; (5) the not-slipped "
        "count and percentage; (6) the supplied due-vs-non-due "
        "comparison. Do not calculate or reinterpret any of these, "
        "and do not use wording stronger than the evidence supports.\n\n"
        "Reply with the paragraph only -- no preamble, no markdown, no "
        "JSON. At most 170 words."
    )

    return _complete(
        prompt,
        max_tokens=700,
    )


# ============================================================
# PORTFOLIO HIGHLIGHT TERMS
# ============================================================

def portfolio_highlight_terms(reason_breakdown):
    """
    Return database-derived reason terms for UI highlighting.

    No model reasoning is involved.
    """

    terms = set()

    if not isinstance(reason_breakdown, dict):
        return []

    for reason in reason_breakdown:

        if not isinstance(reason, str):
            continue

        cleaned = " ".join(
            reason.split()
        ).strip()

        if len(cleaned) >= 3:
            terms.add(cleaned)

    return sorted(
        terms,
        key=lambda value: (
            -len(value),
            value.lower(),
        ),
    )
