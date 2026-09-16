import { useState } from 'react'
import ExplainPanel from '../ExplainPanel/ExplainPanel'
import { Field, QuantityTrio, statusLabel } from '../common'

/**
 * Full detail for one well on the report date.
 *
 * Each task the well ran that day is shown as its own panel -- unrelated tasks
 * are never merged into a single figure.
 */
export default function WellDetail({ result }) {
  const { well_id: wellId, report_date: reportDate, task_count: taskCount, tasks } = result

  return (
    <>
      <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
        Well {wellId} · {reportDate} · {taskCount} daily task{taskCount === 1 ? '' : 's'}
        {taskCount > 1 ? ' — each task is listed separately below.' : ''}
      </p>

      {tasks.map((task) => (
        <TaskDetailPanel key={task.task_daily_id} task={task} reportDate={reportDate} />
      ))}
    </>
  )
}

/**
 * One task's detail panel, including its own AI explanation.
 *
 * The explanation is scoped to this one task, so it renders inside this same
 * panel rather than at the top of the page -- the answer belongs next to the
 * task it describes, not detached from it.
 */
function TaskDetailPanel({ task, reportDate }) {
  const [explaining, setExplaining] = useState(false)

  return (
    <section className="detail-panel">
      <div className="detail-panel__head">
        <h3 className="detail-panel__title">
          {task.activity_description || (
            <span className="missing">Activity description not mapped</span>
          )}
        </h3>
        <div style={{ display: 'flex', gap: 9, alignItems: 'center' }}>
          <span className={`status-pill status-pill--small status-pill--${task.quantity_status}`}>
            {statusLabel(task.quantity_status)}
          </span>
          <button type="button" className="btn" onClick={() => setExplaining((value) => !value)}>
            {explaining ? 'Hide explanation' : 'Explain this task'}
          </button>
        </div>
      </div>

      <div className="field-grid">
        <Field label="Well ID" value={task.well_id} />
        <Field label="Date" value={task.action_on} />
        <Field label="Task Code" value={task.task_code} mono missingText="Not recorded" />
        <Field label="Activity ID" value={task.activity_id} mono missingText="Not derivable" />
        <Field label="Activity Code" value={task.activity_code} mono missingText="Not mapped" />
        <Field label="WBS" value={task.wbs} missingText="Not mapped" />
        <Field label="Crew" value={task.crew_code} missingText="Not mapped" />
        <Field
          label="UOM"
          value={task.uom_code}
          missingText={
            task.activity_uom
              ? `Not recorded on this task (activity master: ${task.activity_uom})`
              : 'Not recorded'
          }
        />
        {task.activity_uom ? (
          <Field label="Activity Master UOM" value={task.activity_uom} missingText="Not recorded" />
        ) : null}
        <Field
          label="Daily Completed"
          value={
            task.daily_completed === null || task.daily_completed === undefined
              ? null
              : task.daily_completed
                ? 'Yes'
                : 'No'
          }
          missingText="Not recorded"
        />
        <Field label="PH Name" value={task.ph_name} missingText="Not recorded" />
        <Field label="Mapping Status" value={task.mapping_status} />
        <Field label="Quantity Status" value={statusLabel(task.quantity_status)} />
        <Field label="Schedule ID" value={task.schedule_id} missingText="Not recorded" />
      </div>

      <QuantityTrio
        planned={task.planned}
        actual={task.actual_quantity}
        progress={task.progress}
        uom={task.uom_code}
      />

      <CrewPersonnel task={task} />

      {task.data_quality_flags?.length ? (
        <div className="dq" style={{ marginTop: 14, marginBottom: 0 }}>
          <div className="dq__title">Data quality on this task</div>
          <div className="dq__list">
            {task.data_quality_flags.map((flag) => (
              <span className="flag-chip" key={flag}>
                {flag}
              </span>
            ))}
          </div>
          <div className="dq__note">
            These conditions are reported separately and do not change the planned
            or actual quantities above.
            {task.group_row_count > 1
              ? ` This task was recorded on ${task.group_row_count} rows; one was selected as authoritative.`
              : ''}
          </div>
        </div>
      ) : null}

      {explaining ? (
        <ExplainPanel
          request={{
            report_date: reportDate,
            scope: 'task',
            well_id: task.well_id,
            task_daily_id: task.task_daily_id,
          }}
          onClose={() => setExplaining(false)}
        />
      ) : null}
    </section>
  )
}

/**
 * Personnel behind the task: Well -> WBS -> Activity -> Task (already shown
 * in the fields above) -> Crew -> Supervisor -> Employees.
 *
 * Resolved from the specific crew instance assigned to this task
 * (task_daily.crew_id), NOT activity_master_csv.crew_code above -- that field
 * stays the sole business-rule WBS crew. This is additive "who actually
 * worked it" evidence, absent whenever the task carries no crew_id or the
 * crew instance has no supervisor/roster on file.
 */
export function CrewPersonnel({ task }) {
  const hasAnyPersonnel =
    task.crew_type_name || task.crew_supervisor || (task.crew_employees && task.crew_employees.length)
  if (!hasAnyPersonnel) return null

  return (
    <div className="crew-chain">
      <div className="crew-chain__title">Crew behind this task</div>
      <div className="crew-chain__path">
        <span className="crew-chain__well">Well {task.well_id}</span>
        <span className="crew-chain__sep">›</span>
        <span>{task.wbs || 'Not mapped'}</span>
        <span className="crew-chain__sep">›</span>
        <span>{task.activity_code || 'unmapped'}</span>
        <span className="crew-chain__sep">›</span>
        <span>{task.crew_type_name || <span className="missing">Crew type not recorded</span>}</span>
        <span className="crew-chain__sep">›</span>
        <span className="crew-chain__supervisor">
          {task.crew_supervisor || <span className="missing">Supervisor not recorded</span>}
        </span>
      </div>
      <dl className="kv" style={{ marginTop: 10 }}>
        <dt>Supervisor</dt>
        <dd>{task.crew_supervisor || <span className="missing">Not recorded</span>}</dd>
        <dt>Employees</dt>
        <dd>
          {task.crew_employees && task.crew_employees.length ? (
            <ul className="crew-chain__employees">
              {task.crew_employees.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ) : (
            <span className="missing">No roster on file</span>
          )}
        </dd>
      </dl>
    </div>
  )
}
