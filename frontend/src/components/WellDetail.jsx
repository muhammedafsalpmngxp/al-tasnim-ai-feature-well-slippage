const SCENARIO_LABELS = {
  BEFORE_DRILLING: 'Before drilling',
  DRILLING_IN_PROGRESS: 'Drilling in progress',
  AFTER_DRILLING: 'After drilling',
  COMPLETED: 'Completed'
}

const DATE_LABELS = {
  ex_rig_on_date: 'Expected rig on',
  rig_on_date: 'Actual rig on',
  ex_rig_off_date: 'Expected rig off',
  rig_off_date: 'Actual rig off',
  pegged_date: 'Pegged',
  flaf_issue_date: 'FLAF issued',
  eng_completion_date: 'Eng. completion'
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

const ACTIVITY_COLUMNS = [
  { key: 'activity', label: 'Activity' },
  { key: 'activity_code', label: 'Code' },
  { key: 'project_type', label: 'Type' },
  { key: 'crew', label: 'Crew' },
  { key: 'progress_percent', label: 'Progress %' },
  { key: 'target_start', label: 'Target start', date: true },
  { key: 'target_end', label: 'Target end', date: true },
  { key: 'actual_start', label: 'Actual start', date: true },
  { key: 'actual_end', label: 'Actual end', date: true },
  { key: 'remaining_duration', label: 'Rem. dur.' },
  { key: 'delay_days', label: 'Delay (days)' },
  { key: 'schedule_risk', label: 'Schedule risk' },
  { key: 'execution_status', label: 'Execution' },
  { key: 'target_achievability', label: 'Achievability' }
]

function formatDate(value) {
  if (!value) return '—'

  return String(value).split('T')[0]
}

function riskBand(score) {
  if (score === null || score === undefined) return 'none'
  if (score >= 70) return 'high'
  if (score >= 40) return 'medium'
  return 'low'
}

function statusTone(status) {
  if (!status) return 'neutral'
  if (['MISSED', 'DELAYED', 'HOOKUP_DEADLINE_PASSED', 'DATA_QUALITY_ISSUE'].includes(status)) {
    return 'bad'
  }
  if (['PENDING', 'HOOKUP_DEADLINE_FORECAST_PASSED', 'NOT_YET_DUE'].includes(status)) {
    return 'warn'
  }
  return 'good'
}

export default function WellDetail({ detail }) {
  const well = detail.well || {}
  const risk = detail.risk || {}
  const dataQuality = detail.data_quality || {}
  const activities = detail.delayed_activities || []

  const band = riskBand(risk.risk_score)

  return (
    <section className="section detail">
      <h2>Well {well.well_id}</h2>

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
            <span className="fact-label">Expected delay</span>
            <span className="fact-value">
              {risk.expected_delay_days === null || risk.expected_delay_days === undefined
                ? '—'
                : `${risk.expected_delay_days} days`}
            </span>
          </div>

          <div>
            <span className="fact-label">Scenario</span>
            <span className="fact-value">
              {SCENARIO_LABELS[risk.scenario] || risk.scenario}
            </span>
          </div>

          <div>
            <span className="fact-label">Deadline</span>
            <span className="fact-value">{risk.deadline_status || '—'}</span>
          </div>

          <div>
            <span className="fact-label">Accountability</span>
            <span className={`badge badge-${risk.due_status === 'DUE' ? 'bad' : 'warn'}`}>
              {risk.due_status === 'DUE' ? 'DUE — TASNIM' : 'NON-DUE'}
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

      {risk.due_status !== 'DUE' && (
        <p className="note">
          Non-due — delay attributed to
          {` ${risk.kpi_miss_reason || 'an external cause'}`}, so this well counts
          as bonus potential rather than Tasnim-side risk.
        </p>
      )}

      {risk.note && <p className="note">{risk.note}</p>}

      <h3>Key dates</h3>
      <div className="grid">
        {Object.entries(DATE_LABELS).map(([key, label]) => (
          <div key={key} className="grid-item">
            <span className="fact-label">{label}</span>
            <span className="fact-value">{formatDate(well[key])}</span>
          </div>
        ))}

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

      <h3>Evidence level</h3>
      <div className="grid">
        <div className="grid-item">
          <span className="fact-label">Schedule evidence</span>
          <span className="fact-value">
            {dataQuality.schedule_evidence_level || '—'}
          </span>
        </div>
        <div className="grid-item">
          <span className="fact-label">Data evidence</span>
          <span className="fact-value">
            {dataQuality.data_evidence_level || '—'}
          </span>
        </div>
      </div>

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

                    return (
                      <td key={column.key}>
                        {column.date
                          ? formatDate(value)
                          : value === null || value === undefined || value === ''
                            ? '—'
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
