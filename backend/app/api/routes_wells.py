"""Per-well drill-down: the daily tasks for one well on one date, plus the
well lifecycle milestone alerts that are independent of any report date."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.dependencies import (
    get_daily_service,
    get_milestone_service,
    load_dataset,
    parse_report_date,
)
from app.config.database import DatabaseUnavailable
from app.config.settings import get_settings
from app.schemas.daily import (
    MilestoneAlertOut,
    MilestonesResponse,
    TaskOut,
    WellDetailResponse,
)
from app.services.daily_service import DailyService
from app.services.milestone_service import MilestoneService

router = APIRouter(prefix="/api/daily", tags=["wells"])


@router.get("/well/{well_id}", response_model=WellDetailResponse)
def get_well_detail(
    well_id: int = Path(..., description="well.well_master.well_id"),
    report_date: date = Depends(parse_report_date),
    service: DailyService = Depends(get_daily_service),
) -> WellDetailResponse:
    """Daily task details for one well.

    Every task the well ran on that date is returned separately -- unrelated
    tasks are never merged. Served from the day's already-loaded dataset, so
    drilling into wells never issues one query per well.
    """
    dataset = load_dataset(service, report_date)
    tasks = service.filter_tasks(dataset, well_id=well_id)
    if not tasks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No daily task records for well {well_id} on "
                f"{report_date.isoformat()}. The well may be completed, may have "
                "no entry for this date, or may not exist."
            ),
        )
    return WellDetailResponse(
        report_date=report_date,
        well_id=well_id,
        task_count=len(tasks),
        tasks=[TaskOut.from_task(task) for task in tasks],
    )


@router.get("/milestones", response_model=MilestonesResponse)
def get_well_milestones(
    window_days: int = Query(
        None,
        ge=0,
        description="Days ahead of a deadline to count as 'upcoming'. Defaults to MILESTONE_PRIORITY_WINDOW_DAYS.",
    ),
    service: MilestoneService = Depends(get_milestone_service),
) -> MilestonesResponse:
    """Live wells approaching (or past) a pegging / FLAF / rig-on / rig-off deadline.

    Evaluated against today's date, independent of the Daily Morning Brief's
    selected report date. ``overdue`` is capped for payload size; ``overdue_count``
    always carries the true total.
    """
    settings = get_settings()
    effective_window = window_days if window_days is not None else settings.milestone_priority_window_days
    try:
        upcoming, overdue = service.upcoming_and_overdue(effective_window)
    except DatabaseUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None

    return MilestonesResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        window_days=effective_window,
        upcoming=[_alert_out(alert) for alert in upcoming],
        overdue_count=len(overdue),
        overdue=[_alert_out(alert) for alert in overdue[: settings.milestone_overdue_display_limit]],
    )


def _alert_out(alert) -> MilestoneAlertOut:
    return MilestoneAlertOut(
        well_id=alert.well_id,
        milestone=alert.milestone.value,
        milestone_label=alert.label,
        deadline_date=alert.deadline_date,
        days_remaining=alert.days_remaining,
        overdue=alert.overdue,
        pegged_date=alert.pegged_date,
        flaf_issue_date=alert.flaf_issue_date,
        ex_rig_on_date=alert.ex_rig_on_date,
        rig_on_date=alert.rig_on_date,
        ex_rig_off_date=alert.ex_rig_off_date,
        rig_off_date=alert.rig_off_date,
    )
