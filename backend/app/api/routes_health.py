"""Health and configuration endpoints. No secret is ever returned."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.dependencies import get_llm_service
from app.config.database import DatabaseUnavailable, check_connectivity
from app.config.settings import ConfigurationError, get_settings
from app.schemas.daily import HealthResponse
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(llm_service: LLMService = Depends(get_llm_service)) -> HealthResponse:
    """Report database reachability and LLM configuration.

    The dashboard uses this to tell a database outage apart from a day with no
    records -- two very different things for an operator.
    """
    settings = get_settings()
    database = {"connected": False, "error": None}
    try:
        info = check_connectivity()
        database = {
            "connected": True,
            "error": None,
            "database_name": info.get("database_name"),
            "server_version": info.get("server_version"),
            "read_only": True,
        }
    except (DatabaseUnavailable, ConfigurationError) as exc:
        database["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected health-check failure")
        database["error"] = f"Unexpected database error: {type(exc).__name__}"

    return HealthResponse(
        status="ok" if database["connected"] else "degraded",
        database=database,
        llm=llm_service.status(),
        config=settings.safe_dump(),
    )
