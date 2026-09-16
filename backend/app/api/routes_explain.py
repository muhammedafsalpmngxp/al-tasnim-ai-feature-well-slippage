"""The Explain / Elaborate endpoint.

The request names a scope. The backend re-derives the deterministic evidence
for that scope, sends it to the LLM, and returns the explanation alongside the
evidence it was based on. The client cannot supply the figures to be explained,
and the LLM never touches the database.

A failure here is not a dashboard failure: the response carries
``available: false`` with a reason, plus the evidence, which remains valid.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_daily_service,
    get_evidence_service,
    get_llm_service,
    load_dataset,
)
from app.models.daily import DailyTask
from app.schemas.daily import ExplainRequest, ExplainResponse
from app.services.daily_service import DailyService
from app.services.evidence_service import EvidenceService
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/daily", tags=["explain"])

VALID_SCOPES = {"day", "uom", "group", "status", "well", "task"}


@router.post("/explain", response_model=ExplainResponse)
def explain(
    request: ExplainRequest,
    service: DailyService = Depends(get_daily_service),
    evidence_service: EvidenceService = Depends(get_evidence_service),
    llm_service: LLMService = Depends(get_llm_service),
) -> ExplainResponse:
    scope = (request.scope or "day").strip().lower()
    if scope not in VALID_SCOPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown scope {request.scope!r}. Valid scopes: "
            + ", ".join(sorted(VALID_SCOPES)),
        )

    dataset = load_dataset(service, request.report_date)
    try:
        tasks: List[DailyTask] = service.filter_tasks(
            dataset,
            uom=request.uom,
            wbs=request.wbs,
            activity_code=request.activity_code,
            status=request.status,
            well_id=request.well_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from None

    if request.task_daily_id is not None:
        tasks = [task for task in tasks if task.task_daily_id == request.task_daily_id]

    if not tasks:
        return ExplainResponse(
            report_date=request.report_date,
            scope=scope,
            available=False,
            error="There are no daily task records in this selection to explain.",
            evidence={},
        )

    evidence = evidence_service.build(
        dataset,
        tasks,
        scope=scope,
        uom=request.uom,
        wbs=request.wbs,
        activity_code=request.activity_code,
        status=request.status,
        well_id=request.well_id,
    )

    result = llm_service.explain_safe(evidence)
    if not result["available"]:
        logger.info("explanation unavailable for scope=%s: %s", scope, result["error"])

    return ExplainResponse(
        report_date=request.report_date,
        scope=scope,
        available=result["available"],
        explanation=result["explanation"],
        error=result["error"],
        model=result["model"],
        cached=result.get("cached", False),
        evidence=evidence,
    )
