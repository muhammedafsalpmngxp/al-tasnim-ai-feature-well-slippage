import logging
from typing import List, Optional

from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel

from app.services.sql_workflow import (
    run_sql_agent_pipeline,
    SqlAgentError,
    TARGET_SPECS,
)


router = APIRouter(
    prefix="/api",
    tags=["SQL Agent"]
)

logger = logging.getLogger(__name__)


class SqlAgentRequest(BaseModel):
    targets: Optional[List[str]] = None


# ============================================================
# GENERATE / VERIFY / VALIDATE / WRITE investigation.sql and
# slipped_wells.sql from schema + hints + business rules
# ============================================================

@router.post("/sql-agent/generate")
def generate_sql(payload: SqlAgentRequest = SqlAgentRequest()):

    try:
        result = run_sql_agent_pipeline(payload.targets)
        return result

    except SqlAgentError as exc:
        logger.warning("SQL agent pipeline could not run: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        ) from exc

    except Exception:
        logger.exception("SQL agent pipeline failed unexpectedly")
        raise HTTPException(
            status_code=500,
            detail="SQL agent pipeline failed unexpectedly. Check the server logs."
        )


@router.get("/sql-agent/targets")
def list_targets():

    return {
        "success": True,
        "targets": {
            name: spec["description"]
            for name, spec in TARGET_SPECS.items()
        },
    }
