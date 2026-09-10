"""
ORCHESTRATION of the evidence pipeline.

    DATABASE
      -> well_evidence.sql          authoritative deterministic evidence
      -> raw_evidence               untouched SQL output (both result sets)
      -> build_ui_json()            dashboard payload
      -> build_ai_evidence()        compact facts for the LLM
      -> investigation response

The AI summary endpoint consumes the SAME bundle, so there is never a
second, different interpretation of the database.
"""

from pathlib import Path
import json
from tempfile import NamedTemporaryFile

from app.services.ai_evidence import build_ai_evidence, highlight_terms
from app.services.crew import get_well_crews
from app.services.evidence import (
    get_well_evidence,
    WellNotFoundError  # re-exported: the API layer imports it from here
)
from app.services.serialization import clean_value
from app.services.ui_json import build_ui_json


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

PROJECT_IDS_SQL_FILE = BASE_DIR / "sql" / "well_project_ids.sql"

JSON_DIR = BASE_DIR / "app" / "responses"

# The dashboard payload (existing filename kept).
JSON_FILE = JSON_DIR / "investigation.json"

# Kept so a summary can be audited later without re-querying (see §19 of
# the refactor brief). Both are git-ignored along with investigation.json.
RAW_EVIDENCE_FILE = JSON_DIR / "evidence_raw.json"
AI_EVIDENCE_FILE = JSON_DIR / "evidence_ai.json"


__all__ = [
    "WellNotFoundError",
    "get_evidence_bundle",
    "get_well_risk_assessment",
    "get_well_project_ids",
    "update_investigation_json"
]


# ============================================================
# ALL PROJECT IDs FOR THE WELL
# ============================================================
#
# A separate lookup: well_master carries one project_id per well, but the
# task records frequently reference others (separate scopes of work
# tracked as separate projects). Not part of the authoritative evidence
# SQL, so it stays its own small query.

def get_well_project_ids(connection, well_id: int):

    if not PROJECT_IDS_SQL_FILE.exists():

        raise FileNotFoundError(
            f"Well project IDs SQL file not found: {PROJECT_IDS_SQL_FILE}"
        )

    query = PROJECT_IDS_SQL_FILE.read_text(encoding="utf-8")

    cursor = connection.cursor()

    try:

        cursor.execute(query, well_id)

        if cursor.description is None:
            return []

        columns = [column[0] for column in cursor.description]

        return [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

    finally:
        cursor.close()


# ============================================================
# EVIDENCE BUNDLE
# ============================================================

def get_evidence_bundle(connection, well_id: int):

    """
    One database round-trip through the authoritative SQL, transformed
    into both consumer shapes.

    Returns:
        {
            "raw":             untouched SQL evidence (well + activities),
            "ui":              dashboard JSON,
            "ai":              compact AI evidence JSON,
            "highlight_terms": database-derived terms for the frontend
        }
    """

    raw_evidence = get_well_evidence(connection, well_id)

    project_ids = get_well_project_ids(connection, well_id)

    crews = get_well_crews(connection, well_id)

    ui = build_ui_json(raw_evidence, project_ids, crews)

    # The crew roster is deliberately NOT passed to the AI evidence. It is
    # a dashboard fact resolved entirely in SQL/Python, and a full roster
    # would add hundreds of tokens to every narration request against an
    # account limited to 8000 tokens per minute.
    ai = build_ai_evidence(raw_evidence, ui, project_ids)

    return {
        "raw": raw_evidence,
        "ui": ui,
        "ai": ai,
        "highlight_terms": highlight_terms(ai)
    }


def get_well_risk_assessment(connection, well_id: int):

    """The dashboard payload. Kept for the existing API contract."""

    return get_evidence_bundle(connection, well_id)["ui"]


# ============================================================
# DEBUG PERSISTENCE
# ============================================================

def _write_json(path, payload):

    JSON_DIR.mkdir(parents=True, exist_ok=True)

    # Write then replace so readers never see a partial JSON file.
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=JSON_DIR,
        prefix=f"{path.stem}-",
        suffix=".tmp",
        delete=False
    ) as file:
        json.dump(payload, file, indent=4, ensure_ascii=False, default=str)
        temporary_file = Path(file.name)

    temporary_file.replace(path)


def update_investigation_json(bundle):

    """
    Persist the dashboard payload plus the raw and compact evidence, so a
    summary can be investigated afterwards without touching the database.
    """

    _write_json(JSON_FILE, bundle["ui"])

    _write_json(
        RAW_EVIDENCE_FILE,
        {
            "well_id": bundle["raw"]["well_id"],
            "well": {
                key: clean_value(value)
                for key, value in bundle["raw"]["well"].items()
            },
            "activities": [
                {key: clean_value(value) for key, value in activity.items()}
                for activity in bundle["raw"]["activities"]
            ]
        }
    )

    _write_json(AI_EVIDENCE_FILE, bundle["ai"])

    return bundle["ui"]
