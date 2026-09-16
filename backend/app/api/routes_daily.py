"""Daily morning brief endpoints: summary, detail and group drill-down."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import (
    get_daily_service,
    get_grouping_service,
    get_llm_service,
    load_dataset,
    parse_report_date,
)
from app.config.database import DatabaseUnavailable
from app.config.settings import get_settings
from app.models.daily import DailyTask
from app.schemas.daily import (
    ActivityGroupOut,
    DataQualityOut,
    DayTotalsOut,
    DetailResponse,
    GroupDetailsResponse,
    RecentDateOut,
    RecentDatesResponse,
    StatusGroupOut,
    SummaryResponse,
    TaskOut,
    WbsGroupOut,
    WellTaskSummaryOut,
)
from app.services.daily_service import DailyService
from app.services.grouping_service import (
    ActivityGroup,
    GroupingService,
    StatusGroup,
    WbsGroup,
)
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/daily", tags=["daily"])


def _q(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _quantities(group) -> Dict[str, object]:
    """The quantity/unit fields shared by every summary level.

    One helper for all three levels so a status group, a WBS group and an
    activity group can never disagree about when a total may be reported.
    """
    return {
        "well_count": group.well_count,
        "task_count": group.task_count,
        "uom_code": group.uom_code,
        "uom_codes": group.uom_codes,
        "quantities_summable": group.quantities_summable,
        "planned_quantity": _q(group.planned_quantity),
        "actual_quantity": _q(group.actual_quantity),
        "data_quality_counts": group.data_quality_counts,
    }


def _activity_out(activity: ActivityGroup) -> ActivityGroupOut:
    return ActivityGroupOut(
        status=activity.status.value,
        wbs=activity.wbs,
        activity_code=activity.activity_code,
        activity_description=activity.activity_description,
        **_quantities(activity),
    )


def _wbs_out(wbs_group: WbsGroup) -> WbsGroupOut:
    return WbsGroupOut(
        status=wbs_group.status.value,
        wbs=wbs_group.wbs,
        activities=[_activity_out(a) for a in wbs_group.sorted_activities()],
        **_quantities(wbs_group),
    )


def _status_out(status_group: StatusGroup) -> StatusGroupOut:
    return StatusGroupOut(
        status=status_group.status.value,
        wbs_groups=[_wbs_out(g) for g in status_group.sorted_wbs_groups()],
        **_quantities(status_group),
    )


@router.get("/summary", response_model=SummaryResponse)
def get_summary(
    report_date: date = Depends(parse_report_date),
    refresh: bool = Query(False, description="Bypass the server-side cache"),
    service: DailyService = Depends(get_daily_service),
    grouping: GroupingService = Depends(get_grouping_service),
    llm_service: LLMService = Depends(get_llm_service),
) -> SummaryResponse:
    """Grouped daily summary for the selected date (Dataset A).

    Grouped validation status -> WBS -> activity, with the status sections in
    fixed ``QuantityStatus`` order so the brief reads the same way every day.

    Also decides, from configuration rather than from React, whether the day is
    small enough to be shown as individual task cards.
    """
    settings = get_settings()
    if refresh:
        # The dataset for this date is about to be reloaded from scratch; any
        # cached AI explanation was computed against the old data and must not
        # outlive it, even in the rare case where the reload happens to come
        # back byte-identical.
        llm_service.invalidate_date(report_date)
    dataset = load_dataset(service, report_date, refresh=refresh)
    status_groups = grouping.build(dataset)
    totals = grouping.day_totals(dataset)
    quality = grouping.data_quality(dataset)

    view_mode = (
        "detail"
        if len(dataset.tasks) <= settings.detail_view_task_threshold
        else "grouped"
    )

    return SummaryResponse(
        report_date=report_date,
        generated_at=datetime.now(timezone.utc).isoformat(),
        totals=DayTotalsOut(**totals),
        data_quality=DataQualityOut(**quality),
        status_groups=[_status_out(group) for group in status_groups],
        view_mode=view_mode,
        detail_view_task_threshold=settings.detail_view_task_threshold,
        tasks=(
            [TaskOut.from_task(task) for task in dataset.tasks]
            if view_mode == "detail"
            else []
        ),
    )


@router.get("/details", response_model=DetailResponse)
def get_details(
    report_date: date = Depends(parse_report_date),
    service: DailyService = Depends(get_daily_service),
) -> DetailResponse:
    """Every logical daily task for the selected date (Dataset B)."""
    dataset = load_dataset(service, report_date)
    return DetailResponse(
        report_date=report_date,
        task_count=len(dataset.tasks),
        tasks=[TaskOut.from_task(task) for task in dataset.tasks],
    )


@router.get("/group-details", response_model=GroupDetailsResponse)
def get_group_details(
    report_date: date = Depends(parse_report_date),
    wbs: Optional[str] = Query(None, description="WBS; '' selects tasks with no WBS"),
    activity_code: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="ON_PLAN | ABOVE_PLAN | BELOW_PLAN | NO_ACTUAL | NOT_VALIDATED",
    ),
    uom: Optional[str] = Query(
        None,
        description=(
            "UOM code; '' selects tasks with no UOM. No longer part of the "
            "summary hierarchy -- kept as an optional filter so a single unit "
            "stays reachable."
        ),
    ),
    refresh: bool = Query(False, description="Bypass the server-side cache"),
    service: DailyService = Depends(get_daily_service),
    llm_service: LLMService = Depends(get_llm_service),
) -> GroupDetailsResponse:
    """The wells and tasks behind one summary figure -- called with no filter
    at all, this is also the whole day's per-well rollup that drives the main
    dashboard's well list.

    The status being filtered on was classified by the backend; this endpoint
    only selects the matching rows, which is what makes every count on the
    dashboard traceable to the records that produced it.
    """
    if refresh:
        llm_service.invalidate_date(report_date)
    dataset = load_dataset(service, report_date, refresh=refresh)
    try:
        tasks = service.filter_tasks(
            dataset,
            uom=uom,
            wbs=wbs,
            activity_code=activity_code,
            status=status_filter,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from None

    return GroupDetailsResponse(
        report_date=report_date,
        filters={
            "status": status_filter,
            "wbs": wbs,
            "activity_code": activity_code,
            "uom": uom,
        },
        task_count=len(tasks),
        well_count=len({task.well_id for task in tasks}),
        wells=_well_summaries(tasks),
        tasks=[TaskOut.from_task(task) for task in tasks],
    )


def _well_summaries(tasks: List[DailyTask]) -> List[WellTaskSummaryOut]:
    """Per-well roll-up of a filtered task list.

    Quantities are only reported when every task for that well shares one UOM,
    because no conversion between units is defined.
    """
    by_well: Dict[int, List[DailyTask]] = {}
    for task in tasks:
        by_well.setdefault(task.well_id, []).append(task)

    summaries: List[WellTaskSummaryOut] = []
    for well_id in sorted(by_well):
        well_tasks = by_well[well_id]
        status_counts: Dict[str, int] = {}
        planned: Optional[Decimal] = None
        actual: Optional[Decimal] = None
        for task in well_tasks:
            key = task.quantity_status.value
            status_counts[key] = status_counts.get(key, 0) + 1
            if task.planned is not None:
                planned = (planned or Decimal(0)) + task.planned
            if task.actual_quantity is not None:
                actual = (actual or Decimal(0)) + task.actual_quantity

        uom_codes = {task.uom_code for task in well_tasks}
        single_uom = len(uom_codes) == 1
        summaries.append(
            WellTaskSummaryOut(
                well_id=well_id,
                task_count=len(well_tasks),
                status_counts=status_counts,
                planned_quantity=_q(planned) if single_uom else None,
                actual_quantity=_q(actual) if single_uom else None,
                uom_code=next(iter(uom_codes)) if single_uom else None,
            )
        )
    return summaries


@router.get("/dates", response_model=RecentDatesResponse)
def get_recent_dates(
    limit: int = Query(30, ge=1, le=180),
    service: DailyService = Depends(get_daily_service),
) -> RecentDatesResponse:
    """Recent dates that carry daily entries, to guide the date picker."""
    try:
        rows = service.recent_dates(limit)
    except DatabaseUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return RecentDatesResponse(dates=[RecentDateOut(**row) for row in rows])
