"""Internal domain objects for the daily morning brief.

These are the shapes the services pass around. The API contract lives in
app/schemas; keeping them apart means a wire-format change never forces a
change to the deterministic core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import List, Optional


class QuantityStatus(str, Enum):
    """Deterministic classification of a daily entry's reported quantity.

    Computed once, in validation_service. Neither React nor the LLM may
    recompute or override it.

    This is also the dashboard's top-level grouping (summary -> status -> WBS ->
    activity), so **definition order is display order**: every ``status_counts``
    mapping and every list of status groups comes out in the order below, and
    the UI never re-sorts them.
    """

    ON_PLAN = "ON_PLAN"
    ABOVE_PLAN = "ABOVE_PLAN"
    BELOW_PLAN = "BELOW_PLAN"
    NO_ACTUAL = "NO_ACTUAL"
    #: An actual was reported but there is no planned quantity to compare it
    #: against. daily_report_rules.md does not define how to classify that, so
    #: the condition is exposed as unresolved rather than guessed at.
    NOT_VALIDATED = "NOT_VALIDATED"


class MappingStatus(str, Enum):
    """How far the task_code -> activity -> WBS / crew chain could be resolved."""

    MAPPED = "MAPPED"
    UNMAPPED_ACTIVITY = "UNMAPPED_ACTIVITY"
    UNMAPPED_DESCRIPTION = "UNMAPPED_DESCRIPTION"
    UNMAPPED_WBS = "UNMAPPED_WBS"
    UNMAPPED_CREW = "UNMAPPED_CREW"


class DataQualityFlag(str, Enum):
    """Data-quality conditions, deliberately kept separate from quantity status.

    A mapping or JSON problem is never folded into the operational numbers.
    """

    UNMAPPED_ACTIVITY = "UNMAPPED_ACTIVITY"
    UNMAPPED_DESCRIPTION = "UNMAPPED_DESCRIPTION"
    UNMAPPED_WBS = "UNMAPPED_WBS"
    UNMAPPED_CREW = "UNMAPPED_CREW"
    MISSING_UOM = "MISSING_UOM"
    INVALID_DAILY_JSON = "INVALID_DAILY_JSON"
    UNPARSEABLE_ACTUAL_QUANTITY = "UNPARSEABLE_ACTUAL_QUANTITY"
    DUPLICATE_ACTUAL_ENTRY = "DUPLICATE_ACTUAL_ENTRY"
    MULTIPLE_TASK_ROWS = "MULTIPLE_TASK_ROWS"
    MISSING_PLANNED = "MISSING_PLANNED"
    MALFORMED_TASK_CODE = "MALFORMED_TASK_CODE"


@dataclass
class DailyTask:
    """One logical daily task on the report date, for one live well."""

    task_daily_id: int
    well_id: int
    action_on: date
    schedule_id: Optional[int]
    task_code: Optional[str]
    activity_id: Optional[str]
    activity_code: Optional[str]
    activity_description: Optional[str]
    wbs: Optional[str]
    crew_code: Optional[str]
    uom_id: Optional[int]
    uom_code: Optional[str]
    #: Reference UOM from the activity master (dbo.mapping_master.UOM), NOT the
    #: authoritative UOM. uom_code above (ref.uom via task_daily.uom_id) is the
    #: only UOM used for grouping or quantity interpretation; this is exposed
    #: purely as traceable evidence for when uom_code is missing or to let a
    #: human compare the two. Never used to fill in, override or convert.
    activity_uom: Optional[str]
    crew_id: Optional[int]
    crew_type_id: Optional[int]
    #: Personnel evidence for the specific crew instance behind this task,
    #: resolved from task_daily.crew_id via ref.crew / ref.crew_type / ref.employee
    #: / bridge.crew_employee. Additive evidence, never a substitute for
    #: crew_code (the business-rule WBS crew) above.
    crew_type_name: Optional[str]
    crew_instance_code: Optional[str]
    crew_supervisor: Optional[str]
    planned: Optional[Decimal]
    progress: Optional[Decimal]
    actual_quantity: Optional[Decimal]
    actual_quantity_raw: Optional[str]
    daily_completed: Optional[bool]
    ph_name: Optional[str]
    quantity_status: QuantityStatus
    mapping_status: MappingStatus
    data_quality_flags: List[DataQualityFlag] = field(default_factory=list)
    group_row_count: int = 1
    group_actual_entry_count: int = 0
    crew_employees: List[str] = field(default_factory=list)

    # --- grouping keys -------------------------------------------------
    # Display labels are never invented. When a value is missing the task is
    # grouped under an explicit "unknown" key and the UI says so.
    @property
    def status_key(self) -> str:
        """Top level of the summary hierarchy -- always present, never blank.

        Unlike the keys below it, this one can never be missing: every task is
        classified by validation_service, so no task can fall out of the
        summary.
        """
        return self.quantity_status.value

    @property
    def uom_key(self) -> str:
        return self.uom_code or ""

    @property
    def wbs_key(self) -> str:
        return self.wbs or ""

    @property
    def activity_key(self) -> str:
        return self.activity_code or ""

    @property
    def group_key(self) -> tuple:
        return (self.status_key, self.wbs_key, self.activity_key)


@dataclass
class DayCounters:
    """Day-level raw counters from daily_summary.sql (pre-grain-resolution)."""

    raw_row_count: int = 0
    raw_well_count: int = 0
    raw_actual_entry_count: int = 0
    invalid_json_row_count: int = 0
    unparseable_actual_row_count: int = 0
    logical_task_count: int = 0
    multi_row_task_count: int = 0
    duplicate_actual_task_count: int = 0
    superseded_row_count: int = 0


@dataclass
class DailyDataset:
    """The resolved evidence for one report date: everything else derives from it."""

    report_date: date
    tasks: List[DailyTask]
    counters: DayCounters
