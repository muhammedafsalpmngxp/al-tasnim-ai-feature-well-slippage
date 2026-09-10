import InsightPanel from './InsightPanel.jsx'

const SCENARIO_LABELS = {
  BEFORE_DRILLING: 'Before drilling',
  DRILLING_IN_PROGRESS: 'Drilling in progress',
  AFTER_DRILLING: 'After drilling',
  COMPLETED: 'Completed'
}

// Gate keys come from the authoritative SQL via milestone_delays.
//
// The two date rows are labelled per gate because they do not all mean
// the same thing: rig-on/rig-off compare a planned date to an actual
// one, whereas pegging, FLAF, construction and hook-up are measured
// against a DEADLINE the evidence layer derives. The construction gate
// in particular tests "did rig-on happen by the deadline" — its actual
// value is the rig-on date, NOT a construction completion date, so it is
// labelled as such.
const MILESTONE_GATE_LABELS = {
  rig_on: { name: 'Rig on', expected: 'Expected', actual: 'Actual' },
  rig_off: { name: 'Rig off', expected: 'Expected', actual: 'Actual' },
  pegging: { name: 'Pegging', expected: 'Deadline', actual: 'Pegged' },
  flaf: { name: 'FLAF', expected: 'Deadline', actual: 'Issued' },
  construction: {
    name: 'Construction',
    expected: 'Deadline',
    actual: 'Rig-on'
  },
  hookup: {
    name: 'Hook-up',
    expected: 'Deadline',
    actual: 'Eng. compl.'
  }
}

// Milestone-state vocabulary, kept deliberately distinct from the
// accountability (due / non-due) vocabulary so the two concepts cannot
// be read as the same thing.
const DEADLINE_STATE_LABELS = {
  DUE: 'Overdue',
  NON_DUE: 'Not yet due'
}

// Presentation only — the underlying enums stay authoritative.
const RESOURCE_STATUS_LABELS = {
  RESOURCE_DATA_AVAILABLE: 'Data available',
  RESOURCE_DATA_NOT_AVAILABLE: 'No data'
}

const PRODUCTIVITY_STATUS_LABELS = {
  PRODUCTIVITY_AVAILABLE: 'Available',
  PRODUCTIVITY_NOT_AVAILABLE: 'Not available'
}

const MILESTONE_LABELS = {
  pegging_status: 'Pegging',
  flaf_status: 'FLAF',
  construction_status: 'Construction',
  hookup_status: 'Hook-up'
}

const PROGRESS_LABELS = {
  well_progress: 'Well progress',
  flowline_progress: 'Flowline progress'
}

// `mapped: true` marks a column resolved through the activity/WBS master
// mapping (business_rules.md §3/§6: task_code -> activity_id ->
// activity_master_mapping -> activity_master_csv). A missing value there
// means the mapping row does not exist, so the cell says "Unmapped".
//
// `raw: true` marks a column read directly off task_daily — planned
// crew, crew/crew-type/employee IDs, equipment IDs. A missing value
// there is just an unpopulated source column, not a failed lookup, so
// the cell says "Not available" instead. business_rules.md §7/§8: these
// are kept as separate fields — Master Crew Code (from the mapping),
// Planned Crew, Crew ID and Crew Type ID are different concepts and are
// never collapsed into one "crew" value.
const ACTIVITY_COLUMNS = [
  { key: 'activity_code', label: 'Activity', mapped: true },
  { key: 'activity_id', label: 'Activity ID', mapped: true },
  { key: 'wbs', label: 'WBS', mapped: true },
  { key: 'project_type', label: 'Project', mapped: true },
  { key: 'master_crew_code', label: 'Master Crew Code', mapped: true },
  { key: 'planned_crew', label: 'Planned Crew', raw: true },
  { key: 'crew_id', label: 'Crew ID', raw: true },
  { key: 'crew_type_id', label: 'Crew Type ID', raw: true },
  { key: 'emp_id', label: 'Employee ID', raw: true },
  { key: 'data_employees', label: 'Employee data', raw: true },
  { key: 'daily_employee_ids', label: 'Daily employee IDs', raw: true },
  { key: 'daily_equipment_ids', label: 'Daily equipment IDs', raw: true },
  { key: 'progress_percent', label: 'Progress %' },
  { key: 'target_start', label: 'Target start', date: true },
  { key: 'target_end', label: 'Target end', date: true },
  { key: 'actual_start', label: 'Actual start', date: true },
  { key: 'actual_end', label: 'Actual end', date: true },
  { key: 'remaining_duration', label: 'Rem. dur.' },
  { key: 'delay_days', label: 'Delay (days)' },
  { key: 'schedule_risk', label: 'Schedule risk' },
  { key: 'execution_status', label: 'Execution' },
  {
    key: 'resource_status',
    label: 'Resource data',
    labels: RESOURCE_STATUS_LABELS
  },
  {
    key: 'productivity_status',
    label: 'Productivity data',
    labels: PRODUCTIVITY_STATUS_LABELS
  },
  { key: 'target_achievability', label: 'Achievability' }
]

function formatDate(value) {
  if (!value) return '—'

  return String(value).split('T')[0]
}

function isMissing(value) {
  return value === null || value === undefined || value === ''
}

function downloadJSON(detail) {
  const wellId = detail?.well?.well_id ?? 'unknown'
  const blob = new Blob([JSON.stringify(detail, null, 2)], {
    type: 'application/json'
  })
  const url = URL.createObjectURL(blob)

  const link = document.createElement('a')
  link.href = url
  link.download = `well-${wellId}-assessment.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)

  URL.revokeObjectURL(url)
}

// Colour only — the statuses themselves come from the evidence layer and
// are displayed verbatim.
function statusTone(status) {
  if (!status) return 'neutral'
  if (['MISSED', 'DELAYED', 'OVERDUE', 'HOOKUP_DEADLINE_PASSED',
       'DATA_QUALITY_ISSUE'].includes(status)) {
    return 'bad'
  }
  if (['PENDING', 'HOOKUP_DEADLINE_FORECAST_PASSED', 'NOT_YET_DUE'].includes(status)) {
    return 'warn'
  }
  return 'good'
}

export default function WellDetail({
  detail,
  insight,
  insightLoading,
  insightError
}) {
  const well = detail.well || {}
  const risk = detail.risk || {}
  const dataQuality = detail.data_quality || {}
  const activities = detail.delayed_activities || []
  const crews = well.crews || []

  // A completed well is now selectable, and present-tense accountability
  // wording ("owns this delay") would misread on a finished well.
  const completed = risk.scenario === 'COMPLETED'

  // Band comes from the backend so the threshold is not duplicated here.
  const band = (risk.risk_band || 'none').toLowerCase()

  // The whole panel is themed by who owns the delay: red for
  // Tasnim-side risk, amber for bonus-potential/non-due — not just
  // the small badge, so the distinction reads at a glance.
  const accountabilityTheme = risk.due_status === 'DUE' ? 'due' : 'non-due'
  const delays = detail.milestone_delays || {}

  // The well-level delay belongs to one specific gate. The slipped-well
  // list ranks by the WORST gate instead, so both are labelled with the
  // gate they refer to rather than both saying "delay".
  const delayGate = risk.expected_delay_gate
  const delayGateName = MILESTONE_GATE_LABELS[delayGate]?.name

  // Every flag the evidence layer actually raised, de-duplicated.
  const dqFlags = [
    ...new Set([
      ...(dataQuality.well_flags || []),
      ...(dataQuality.activity_flags || [])
    ])
  ]

  const unevaluatedGates = dataQuality.unevaluated_gates || []

  return (
    <section className={`section detail detail-${accountabilityTheme}`}>
      <div className="detail-head">
        <h2>Well {well.well_id}</h2>
        <button
          type="button"
          className="btn-download"
          onClick={() => downloadJSON(detail)}
        >
          Download JSON
        </button>
      </div>

      <div
        className={`accountability-banner accountability-${
          completed ? 'completed' : accountabilityTheme
        }`}
      >
        {completed
          ? `Completed — hook-up recorded ${
              well.eng_completion_date
                ? `on ${formatDate(well.eng_completion_date)}`
                : '(date not recorded)'
            }`
          : risk.due_status === 'DUE'
            ? 'Accountability: DUE — Tasnim owns this delay'
            : 'Accountability: NON-DUE — outside Tasnim scope (bonus potential)'}
      </div>

      <div className="risk-row">
        <div className={`risk-score risk-${band}`}>
          <span className="risk-value">
            {risk.risk_score === null || risk.risk_score === undefined
              ? '—'
              : risk.risk_score}
          </span>
          <span className="risk-label">risk score / 100</span>
        </div>

        <div className="risk-facts">
          <div>
            <span className="fact-label">Stage</span>
            <span className="fact-value">
              {SCENARIO_LABELS[risk.scenario] || risk.scenario}
            </span>
          </div>

          <div>
            <span className="fact-label">
              {delayGateName ? `${delayGateName} delay` : 'Well delay'}
            </span>
            <span className="fact-value">
              {isMissing(risk.expected_delay_days)
                ? '—'
                : `${risk.expected_delay_days} days`}
            </span>
          </div>

          <div>
            <span className="fact-label">Milestone status</span>
            <span className="fact-value">
              {DEADLINE_STATE_LABELS[risk.deadline_status] || '—'}
            </span>
          </div>

          <div>
            <span className="fact-label">Accountability</span>
            <span
              className={`badge badge-${risk.due_status === 'DUE' ? 'bad' : 'warn'}`}
            >
              {risk.due_status === 'DUE' ? 'DUE' : 'NON-DUE'}
            </span>
          </div>

          <div>
            <span className="fact-label">Data quality</span>
            <span className={`badge badge-${dataQuality.has_issue ? 'bad' : 'good'}`}>
              {dataQuality.has_issue ? 'ISSUE' : 'OK'}
            </span>
          </div>
        </div>
      </div>

      {(risk.kpi_miss_reason || well.remarks) && (
        <div className="note">
          {risk.due_status !== 'DUE' && risk.kpi_miss_reason && (
            <p>
              <strong>Classified NON-DUE</strong> under the current
              accountability rules, with recorded reason{' '}
              <strong>{risk.kpi_miss_reason}</strong> (bonus potential).
            </p>
          )}
          {risk.due_status === 'DUE' && risk.kpi_miss_reason && (
            <p>
              <strong>Classified DUE</strong> under the current
              accountability rules, with recorded reason{' '}
              <strong>{risk.kpi_miss_reason}</strong>.
            </p>
          )}
          {well.remarks && (
            <p>
              <strong>Remarks (evidence, not a stated cause) —</strong>{' '}
              {well.remarks}
            </p>
          )}
        </div>
      )}

      {risk.note && <p className="note">{risk.note}</p>}

      <InsightPanel
        title={`AI summary — well ${well.well_id}`}
        insight={insight}
        loading={insightLoading}
        error={insightError}
      />

      <h3>Projects ({(well.project_ids || []).length})</h3>
      {well.project_ids?.length ? (
        <div className="grid">
          {well.project_ids.map((project) => (
            <div key={project.project_id} className="grid-item project-item">
              <span className="fact-value">
                {project.project_code || 'Unresolved project'}
              </span>
              {project.project_name && (
                <span className="project-name">{project.project_name}</span>
              )}
              <span className="project-guid">{project.project_id}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">No project reference recorded for this well.</p>
      )}

      {/* well -> task_daily.crew_id -> ref.crew -> bridge.crew_employee
          -> ref.employee, resolved and de-duplicated in SQL/Python (see
          well_crew.sql). Supervisor is the recorded supervisor_email on
          the crew's tasks — there is no approved supervisor id/name
          column, so none is invented. */}
      <h3>Crews, supervisors &amp; employees ({crews.length})</h3>
      {crews.length ? (
        <div className="grid">
          {crews.map((crew) => (
            <div key={crew.crew_id} className="grid-item crew-item">
              <span className="fact-label">
                {crew.crew_code || 'Crew code not recorded'}
              </span>
              <span className="crew-line">Crew ID {crew.crew_id}</span>

              <span className="crew-line">
                <span className="crew-sub">Supervisor</span>{' '}
                {crew.supervisor_name || 'Not recorded'}
                {crew.supervisor_id !== null &&
                  crew.supervisor_id !== undefined && (
                    <span className="crew-emp-id"> · ID {crew.supervisor_id}</span>
                  )}
              </span>

              <span className="crew-line">
                <span className="crew-sub">
                  Employees ({crew.employees?.length || 0})
                </span>
              </span>

              {crew.employees?.length ? (
                <ul className="crew-employees">
                  {crew.employees.map((employee) => (
                    <li
                      key={`${crew.crew_id}-${employee.employee_id ?? employee.employee_name}`}
                    >
                      {employee.employee_name || 'Name not recorded'}
                      {employee.employee_id !== null &&
                        employee.employee_id !== undefined && (
                          <span className="crew-emp-id">
                            {' '}
                            · ID {employee.employee_id}
                          </span>
                        )}
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="muted">No employees recorded.</span>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">
          No crew recorded against this well&apos;s tasks.
        </p>
      )}

      <h3>Milestone gates</h3>
      <div className="grid">
        {Object.entries(MILESTONE_GATE_LABELS).map(([key, gate]) => {
          const entry = delays[key] || {}
          const late = entry.delay_days > 0

          // A negative variance means the gate was met early. The
          // evidence layer supplies it; it is only shown where it exists.
          const early = entry.variance_days < 0

          return (
            <div key={key} className="grid-item date-pair">
              <span className="fact-label">{gate.name}</span>
              <span className="date-pair-row">
                <span className="date-pair-sub">{gate.expected}</span>
                <span className="fact-value">{formatDate(entry.expected)}</span>
              </span>
              <span className="date-pair-row">
                <span className="date-pair-sub">{gate.actual}</span>
                <span className="fact-value">
                  {entry.actual ? formatDate(entry.actual) : 'Not recorded'}
                </span>
              </span>
              {late ? (
                <span className="chip-late">
                  {entry.delay_days} {entry.delay_days === 1 ? 'day' : 'days'} late
                </span>
              ) : early ? (
                <span className="chip-early">
                  {Math.abs(entry.variance_days)} days early
                </span>
              ) : null}
            </div>
          )
        })}

        {Object.entries(PROGRESS_LABELS).map(([key, label]) => (
          <div key={key} className="grid-item">
            <span className="fact-label">{label}</span>
            <span className="fact-value">{well[key] ?? '—'}</span>
          </div>
        ))}
      </div>

      <h3>Milestones</h3>
      <div className="grid">
        {Object.entries(MILESTONE_LABELS).map(([key, label]) => {
          const status = detail.milestones?.[key]

          return (
            <div key={key} className="grid-item">
              <span className="fact-label">{label}</span>
              <span className={`badge badge-${statusTone(status)}`}>{status || '—'}</span>
            </div>
          )
        })}
      </div>

      <h3>Data quality &amp; evidence</h3>
      <div className="grid">
        <div className="grid-item">
          <span className="fact-label">Schedule evidence</span>
          <span className="fact-value">
            {dataQuality.schedule_evidence_level || 'Not available'}
          </span>
        </div>
        <div className="grid-item">
          <span className="fact-label">Data evidence</span>
          <span className="fact-value">
            {dataQuality.data_evidence_level || 'Not available'}
          </span>
        </div>
        <div className="grid-item">
          <span className="fact-label">Tasks examined</span>
          <span className="fact-value">
            {detail.evidence_counts?.current_tasks ?? '—'}
          </span>
        </div>
      </div>

      {/* DQ flags stay visible: they qualify every figure above. */}
      {dqFlags.length > 0 && (
        <div className="dq-flags">
          <span className="dq-flags-label">
            Flags raised by the evidence layer ({dqFlags.length})
          </span>
          <ul className="dq-flag-list">
            {dqFlags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
          {unevaluatedGates.length > 0 && (
            <p className="dq-flags-note">
              Gates that could not be evaluated:{' '}
              {unevaluatedGates.join(', ')}
            </p>
          )}
        </div>
      )}

      <h3>Lagging WBS branches</h3>
      {risk.lagging_wbs_branches?.length ? (
        <table className="table">
          <thead>
            <tr>
              <th>Branch</th>
              <th>Delayed activities</th>
              <th>Worst delay (days)</th>
            </tr>
          </thead>
          <tbody>
            {risk.lagging_wbs_branches.map((branch) => (
              <tr key={branch.branch}>
                <td>{branch.branch}</td>
                <td>{branch.delayed_task_count}</td>
                <td>{branch.max_delay_days}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">No lagging branches flagged for this well.</p>
      )}

      <h3>Delayed activities ({activities.length})</h3>
      {activities.length ? (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                {ACTIVITY_COLUMNS.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {activities.map((activity) => (
                <tr key={activity.task_id}>
                  {ACTIVITY_COLUMNS.map((column) => {
                    const value = activity[column.key]
                    const missing = isMissing(value)

                    const isLate =
                      column.key === 'delay_days' &&
                      typeof value === 'number' &&
                      value > 0

                    // A missing MAPPED field means the master-mapping
                    // lookup found nothing; a missing RAW field means the
                    // source column itself is unpopulated. Different
                    // facts, different wording — never fill either in.
                    if (missing) {
                      const label = column.mapped
                        ? 'Unmapped'
                        : column.raw
                          ? 'Not available'
                          : '—'

                      return (
                        <td
                          key={column.key}
                          className={
                            column.mapped || column.raw
                              ? 'cell-unmapped'
                              : undefined
                          }
                        >
                          {label}
                        </td>
                      )
                    }

                    return (
                      <td key={column.key} className={isLate ? 'cell-late' : undefined}>
                        {column.date
                          ? formatDate(value)
                          : column.labels
                            ? column.labels[value] || String(value)
                            : String(value)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No delayed activities flagged for this well.</p>
      )}
    </section>
  )
}
