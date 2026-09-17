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
    get_crew_suggestion_service,
    get_daily_service,
    get_evidence_service,
    get_llm_service,
    load_dataset,
)
from app.models.daily import DailyTask
from app.schemas.daily import ExplainRequest, ExplainResponse
from app.services.crew_suggestion_service import CrewSuggestionService
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
    crew_suggestion_service: CrewSuggestionService = Depends(get_crew_suggestion_service),
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

    # Crew suggestion is an extension of the task-specific AI summary only --
    # never a second UI control or a second request. It rides inside this
    # same evidence payload, for this same LLM call, only when the request
    # resolves to exactly one task (the task AI summary the frontend already
    # requests via scope="task" + task_daily_id). See daily_report_rules.md,
    # "Crew suggestion" section.
    if scope == "task" and len(tasks) == 1:
        try:
            crew_suggestion = crew_suggestion_service.build(
                well_id=tasks[0].well_id,
                task_code=tasks[0].task_code,
                report_date=request.report_date,
            )
        except Exception:  # noqa: BLE001 - this must never break the task's own summary
            logger.exception("crew suggestion evidence failed; continuing without it")
            crew_suggestion = None
        if crew_suggestion is not None:
            evidence["crew_suggestion"] = crew_suggestion

    # Whenever there is nothing at all for the model to say about crew
    # suggestion -- a completed task, or an in-progress task with no
    # historically-proven crew to point to -- the evidence is withheld from
    # the LLM call entirely rather than trusted to stay silent on its own. A
    # system-instruction rule alone cannot guarantee that from a
    # non-deterministic model. The full evidence, including the suppression
    # reason, still reaches the client below for transparency/audit -- only
    # the LLM's own input is narrowed. `suggested_crew` (a stalled, eligible
    # task), `consult_crew` (an in-progress task worth an informational
    # mention) and `no_suggestion_reason` (eligible, but no crew found) are
    # each, on their own, something worth the model narrating.
    llm_evidence = evidence
    crew_suggestion_evidence = evidence.get("crew_suggestion")
    if isinstance(crew_suggestion_evidence, dict) and not (
        crew_suggestion_evidence.get("suggested_crew")
        or crew_suggestion_evidence.get("consult_crew")
        or crew_suggestion_evidence.get("no_suggestion_reason")
    ):
        llm_evidence = {key: value for key, value in evidence.items() if key != "crew_suggestion"}

    result = llm_service.explain_safe(llm_evidence)
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
