"""Internal domain objects for well lifecycle milestones.

Kept apart from app/models/daily.py because this evidence is not scoped to a
report date: it is computed against "today" for every live well, independent
of which day the operator happens to be browsing on the Daily Morning Brief.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class MilestoneType(str, Enum):
    """The four well lifecycle dates business_rules.md defines a deadline for.

    See business_rules.md section 2 (column dictionary) and section 3
    (milestone deadlines). Location/Flowline Construction completion are
    excluded here because they have no actual-date column to test against --
    section 3 judges those by the rig rule instead, not by a date column.
    """

    PEGGING = "PEGGING"
    FLAF = "FLAF"
    RIG_ON = "RIG_ON"
    RIG_OFF = "RIG_OFF"


#: Human labels. The code above stays authoritative; this is display-only.
#: No organisation name (PDO/Al Tasnim) is shown here -- business_rules.md's
#: scope/responsibility split is an internal rule, not something this
#: operator-facing label needs to repeat.
MILESTONE_LABELS = {
    MilestoneType.PEGGING: "Pegging sheet",
    MilestoneType.FLAF: "FLAF",
    MilestoneType.RIG_ON: "Rig-on",
    MilestoneType.RIG_OFF: "Rig-off",
}


@dataclass
class MilestoneAlert:
    """One outstanding milestone for one live well, evaluated against today.

    ``days_remaining`` is signed exactly like schedule_variance_days in
    business_rules.md section 4: negative means the deadline has already
    passed (overdue), zero means it is due today, positive means it is still
    ahead. This is a deadline computed per section 3, not the schedule
    variance of section 4 -- the two are not the same number.
    """

    well_id: int
    milestone: MilestoneType
    deadline_date: date
    days_remaining: int
    #: The well's full set of lifecycle dates, for the detail view. Carried
    #: through so a click never needs a second query.
    pegged_date: Optional[date]
    flaf_issue_date: Optional[date]
    ex_rig_on_date: Optional[date]
    rig_on_date: Optional[date]
    ex_rig_off_date: Optional[date]
    rig_off_date: Optional[date]

    @property
    def overdue(self) -> bool:
        return self.days_remaining < 0

    @property
    def label(self) -> str:
        return MILESTONE_LABELS[self.milestone]
