"""API request/response contracts.

Kept separate from app/models so the wire format can change without touching
the deterministic core. Quantities cross the wire as strings to preserve the
exact decimal value the database returned -- no float rounding is introduced
between SQL Server and the browser.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.daily import DailyTask


def _decimal_to_str(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    normalised = value.normalize()
    # Avoid scientific notation for values such as 1E+2.
    if normalised == normalised.to_integral_value():
        try:
            return str(normalised.quantize(Decimal(1)))
        except Exception:  # noqa: BLE001
            return format(normalised, "f")
    return format(normalised, "f")


class TaskOut(BaseModel):
    """One logical daily task -- the Detail dataset row."""

    task_daily_id: int
    well_id: int
    action_on: date
    schedule_id: Optional[int] = None
    task_code: Optional[str] = None
    activity_id: Optional[str] = None
    activity_code: Optional[str] = None
    activity_description: Optional[str] = None
    wbs: Optional[str] = None
    crew_code: Optional[str] = None
    uom_id: Optional[int] = None
    uom_code: Optional[str] = None
    activity_uom: Optional[str] = Field(
        None,
        description=(
            "Reference UOM from the activity master (dbo.mapping_master.UOM). "
            "Not authoritative -- uom_code above is the only UOM used for "
            "grouping or quantity interpretation. Provided for traceability, "
            "especially where uom_code is missing."
        ),
    )
    crew_id: Optional[int] = None
    crew_type_name: Optional[str] = Field(
        None,
        description=(
            "ref.crew_type.crew_type_name for the specific crew instance assigned "
            "to this task (task_daily.crew_type_id). Personnel evidence, additive "
            "to -- never a substitute for -- crew_code above."
        ),
    )
    crew_instance_code: Optional[str] = None
    crew_supervisor: Optional[str] = Field(
        None, description="ref.employee.emp_name for the crew's supervisor (ref.crew.supervisor_id)."
    )
    crew_employees: List[str] = Field(
        default_factory=list,
        description="Employees on the crew instance, via bridge.crew_employee.",
    )
    planned: Optional[str] = Field(None, description="Planned quantity, exact decimal as text")
    actual_quantity: Optional[str] = Field(None, description="Reported actual quantity")
    progress: Optional[str] = Field(
        None,
        description=(
            "task_daily.progress, reported exactly as stored. Its unit is not "
            "defined in daily_report_rules.md, so it is not rendered as a percentage."
        ),
    )
    daily_completed: Optional[bool] = None
    ph_name: Optional[str] = None
    quantity_status: str
    mapping_status: str
    data_quality_flags: List[str] = []
    group_row_count: int = 1
    group_actual_entry_count: int = 0

    @classmethod
    def from_task(cls, task: DailyTask) -> "TaskOut":
        return cls(
            task_daily_id=task.task_daily_id,
            well_id=task.well_id,
            action_on=task.action_on,
            schedule_id=task.schedule_id,
            task_code=task.task_code,
            activity_id=task.activity_id,
            activity_code=task.activity_code,
            activity_description=task.activity_description,
            wbs=task.wbs,
            crew_code=task.crew_code,
            uom_id=task.uom_id,
            uom_code=task.uom_code,
            activity_uom=task.activity_uom,
            crew_id=task.crew_id,
            crew_type_name=task.crew_type_name,
            crew_instance_code=task.crew_instance_code,
            crew_supervisor=task.crew_supervisor,
            crew_employees=task.crew_employees,
            planned=_decimal_to_str(task.planned),
            actual_quantity=_decimal_to_str(task.actual_quantity),
            progress=_decimal_to_str(task.progress),
            daily_completed=task.daily_completed,
            ph_name=task.ph_name,
            quantity_status=task.quantity_status.value,
            mapping_status=task.mapping_status.value,
            data_quality_flags=[flag.value for flag in task.data_quality_flags],
            group_row_count=task.group_row_count,
            group_actual_entry_count=task.group_actual_entry_count,
        )


class GroupQuantitiesMixin(BaseModel):
    """Quantity fields every summary level shares.

    ``planned_quantity`` / ``actual_quantity`` are populated only when
    ``quantities_summable`` is true -- that is, when every task in the group
    shares one unit of measure. When the group spans several, both totals are
    null and ``uom_codes`` names the units involved, because no conversion
    between units is defined. A null total therefore means "not summable here",
    never "zero".
    """

    well_count: int
    task_count: int
    uom_code: Optional[str] = Field(
        None, description="The group's single UOM, or null when it spans several."
    )
    uom_codes: List[str] = Field(
        default_factory=list, description="Every UOM present in the group."
    )
    quantities_summable: bool = Field(
        True, description="False when the group spans more than one UOM."
    )
    planned_quantity: Optional[str] = None
    actual_quantity: Optional[str] = None
    data_quality_counts: Dict[str, int] = {}


class ActivityGroupOut(GroupQuantitiesMixin):
    activity_code: Optional[str] = None
    activity_description: Optional[str] = None
    wbs: Optional[str] = None
    status: str


class WbsGroupOut(GroupQuantitiesMixin):
    wbs: Optional[str] = None
    status: str
    activities: List[ActivityGroupOut] = []


class StatusGroupOut(GroupQuantitiesMixin):
    """One validation status for the day -- the top level of the summary.

    Every task below this node carries ``status``, so no level under it repeats
    a status breakdown.
    """

    status: str = Field(
        ...,
        description="ON_PLAN | ABOVE_PLAN | BELOW_PLAN | NO_ACTUAL | NOT_VALIDATED",
    )
    wbs_groups: List[WbsGroupOut] = []


class DayTotalsOut(BaseModel):
    task_count: int
    well_count: int
    status_counts: Dict[str, int]


class DataQualityOut(BaseModel):
    flag_counts: Dict[str, int] = {}
    affected_task_count: int = 0
    raw_row_count: int = 0
    logical_task_count: int = 0
    superseded_row_count: int = 0
    multi_row_task_count: int = 0
    duplicate_actual_task_count: int = 0
    invalid_json_row_count: int = 0
    unparseable_actual_row_count: int = 0


class SummaryResponse(BaseModel):
    report_date: date
    generated_at: str
    totals: DayTotalsOut
    data_quality: DataQualityOut
    #: Sections in fixed QuantityStatus order: ON_PLAN, ABOVE_PLAN, BELOW_PLAN,
    #: NO_ACTUAL, NOT_VALIDATED. A status with no tasks is omitted; `totals`
    #: still reports it as a zero.
    status_groups: List[StatusGroupOut]
    #: Backend-owned presentation decision (§ "few tasks vs many tasks").
    view_mode: str = Field(..., description="'detail' or 'grouped'")
    detail_view_task_threshold: int
    #: Populated only in 'detail' mode, so the UI never decides what to show.
    tasks: List[TaskOut] = []


class DetailResponse(BaseModel):
    report_date: date
    task_count: int
    tasks: List[TaskOut]


class WellTaskSummaryOut(BaseModel):
    well_id: int
    task_count: int
    status_counts: Dict[str, int]
    planned_quantity: Optional[str] = None
    actual_quantity: Optional[str] = None
    uom_code: Optional[str] = None


class GroupDetailsResponse(BaseModel):
    report_date: date
    filters: Dict[str, Optional[str]]
    task_count: int
    well_count: int
    wells: List[WellTaskSummaryOut]
    tasks: List[TaskOut]


class WellDetailResponse(BaseModel):
    report_date: date
    well_id: int
    task_count: int
    tasks: List[TaskOut]


class RecentDateOut(BaseModel):
    report_date: date
    row_count: int
    well_count: int


class RecentDatesResponse(BaseModel):
    dates: List[RecentDateOut]


class ExplainRequest(BaseModel):
    """Everything the explanation needs is identified by keys, never by values.

    The client names a scope; the backend re-derives the deterministic evidence
    for it. The client cannot supply the numbers to be explained.
    """

    report_date: date
    scope: str = Field(
        "day",
        description="'day', 'group', 'status', 'well' or 'task'",
    )
    uom: Optional[str] = None
    wbs: Optional[str] = None
    activity_code: Optional[str] = None
    status: Optional[str] = None
    well_id: Optional[int] = None
    task_daily_id: Optional[int] = None


class ExplainResponse(BaseModel):
    report_date: date
    scope: str
    available: bool
    explanation: Optional[str] = None
    error: Optional[str] = None
    model: Optional[str] = None
    #: True when this text was reused from an earlier identical request rather
    #: than generated just now -- the underlying evidence hashed the same, so
    #: no new LLM call was made. See LLMService._ExplainCache.
    cached: bool = False
    evidence: Dict = {}


class MilestoneAlertOut(BaseModel):
    """One outstanding well lifecycle deadline (pegging / FLAF / rig-on / rig-off).

    ``days_remaining`` is signed: negative means the deadline has already
    passed and the well is overdue. All six lifecycle dates are included so a
    click can show full context without a second request.
    """

    well_id: int
    milestone: str = Field(..., description="PEGGING | FLAF | RIG_ON | RIG_OFF")
    milestone_label: str
    deadline_date: date
    days_remaining: int
    overdue: bool
    pegged_date: Optional[date] = None
    flaf_issue_date: Optional[date] = None
    ex_rig_on_date: Optional[date] = None
    rig_on_date: Optional[date] = None
    ex_rig_off_date: Optional[date] = None
    rig_off_date: Optional[date] = None


class MilestonesResponse(BaseModel):
    generated_at: str
    window_days: int
    upcoming: List[MilestoneAlertOut]
    overdue_count: int
    #: Capped list of the most-recently-missed deadlines; overdue_count above
    #: is the true total so the UI can say "292 overdue" without listing all.
    overdue: List[MilestoneAlertOut]


class HealthResponse(BaseModel):
    status: str
    database: Dict
    llm: Dict
    config: Dict
