import { useMemo, useState } from 'react'
import ExplainPanel from '../ExplainPanel/ExplainPanel'
import StatusCount from '../StatusCount/StatusCount'
import { EmptyState, Num, orderedStatuses, statusDescription } from '../common'

/**
 * The main dashboard view: one compact row per live well.
 *
 * Earlier versions organised the day by validation status, then by work
 * category, then by activity, before ever reaching a well. That hierarchy
 * carried real information, but it took several clicks to answer the question
 * an operator actually asks first thing: *what did each well do, and how did
 * it come out?* This view answers that in one screen -- one row per well, main
 * points only -- and pushes everything else one click away:
 *
 * * a well's own work is summarised, not listed -- the busiest activity plus
 *   how many others, never every task inline. A well with many tasks is not
 *   handled specially; it simply always drills to its own detail page, the
 *   same click as any other well.
 * * a click on the row opens that well's full detail (`WellDetail`), where
 *   every task is its own panel.
 * * "AI summary" is a second, independent control per row: it expands an
 *   explanation of that well's day in place, without leaving the list.
 *
 * Every figure here is still backend-computed -- this component sums nothing
 * and reclassifies nothing. It only decides how much of what the backend
 * already returned belongs on the front page.
 */
export default function WellList({ resource, reportDate, onSelectWell }) {
  const [query, setQuery] = useState('')

  const wells = resource.data?.wells || []
  const tasks = resource.data?.tasks || []

  const workByWell = useMemo(() => summariseWorkByWell(tasks), [tasks])

  const sorted = useMemo(
    () => [...wells].sort((a, b) => b.task_count - a.task_count || a.well_id - b.well_id),
    [wells],
  )

  const filtered = useMemo(() => {
    const needle = query.trim()
    if (!needle) return sorted
    return sorted.filter((well) => String(well.well_id).includes(needle))
  }, [sorted, query])

  if (!resource.data?.task_count) {
    return (
      <EmptyState title="No daily task records for this date">
        No live well has a task dated {reportDate}. Select another date, or check
        that the daily entries for this date have been submitted.
      </EmptyState>
    )
  }

  return (
    <section>
      <div className="well-list__toolbar">
        <input
          type="text"
          className="well-list__search"
          placeholder="Find a well by ID…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Find a well by ID"
        />
        <span className="well-list__count">
          {filtered.length} of {sorted.length} well{sorted.length === 1 ? '' : 's'}
        </span>
      </div>

      {/*
        Keyed by reportDate: each WellRow owns its own "is the AI summary
        open" state locally, and that state must not survive a date change
        -- an open summary describes one specific date, and would otherwise
        keep sitting open (and stale-looking) after the operator has moved
        on to a different one. Changing this key forces React to unmount
        and recreate every row on a date change, resetting that state the
        same way path-reset already closes the top-level explain panel.
      */}
      <div className="well-list" key={reportDate}>
        {filtered.map((well) => (
          <WellRow
            key={well.well_id}
            well={well}
            work={workByWell.get(well.well_id)}
            reportDate={reportDate}
            onSelectWell={onSelectWell}
          />
        ))}
        {filtered.length === 0 ? (
          <div className="notice">
            <div className="notice__body">No well matches “{query}”.</div>
          </div>
        ) : null}
      </div>
    </section>
  )
}

function WellRow({ well, work, reportDate, onSelectWell }) {
  const [explaining, setExplaining] = useState(false)
  const activeStatuses = orderedStatuses(well.status_counts).filter(
    (status) => well.status_counts[status],
  )

  const openWell = () => onSelectWell(well.well_id)
  const openWellOnKey = (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      openWell()
    }
  }

  return (
    <article className="well-row">
      <div className="well-row__line">
        {/*
          A <div> here, not a <button>: StatusCount below renders its own
          <button>, and a button can never contain another button. role and
          tabIndex keep the row a single keyboard- and screen-reader-reachable
          control, same as clicking anywhere on it with a mouse.
        */}
        <div
          className="well-row__main"
          role="button"
          tabIndex={0}
          onClick={openWell}
          onKeyDown={openWellOnKey}
          title={`Open well ${well.well_id}'s daily tasks`}
        >
          <span className="well-row__id">Well {well.well_id}</span>

          <span className="well-row__work">
            {work?.label || <span className="missing">Activity not mapped</span>}
            {work && work.distinctCount > 1 ? (
              <span className="well-row__work-extra"> +{work.distinctCount - 1} more</span>
            ) : null}
          </span>

          <span className="well-row__figure">
            <Num>{well.task_count}</Num> task{well.task_count === 1 ? '' : 's'}
          </span>

          <span className="well-row__statuses">
            {activeStatuses.map((status) => (
              <StatusCount
                key={status}
                status={status}
                count={well.status_counts[status]}
                small
                title={statusDescription(status)}
              />
            ))}
          </span>
        </div>

        <button
          type="button"
          className="btn btn--ghost well-row__ai-toggle"
          onClick={() => setExplaining((value) => !value)}
        >
          {explaining ? 'Hide AI summary' : 'AI summary'}
        </button>
      </div>

      {explaining ? (
        <ExplainPanel
          request={{ report_date: reportDate, scope: 'well', well_id: well.well_id }}
          onClose={() => setExplaining(false)}
        />
      ) : null}
    </article>
  )
}

/**
 * One representative work label per well: the activity most of its tasks
 * belong to, plus how many other distinct activities it also ran. This is a
 * display summary only -- it never feeds back into a count or a total, and it
 * never hides a task, only how much of its description appears on the front
 * page. The full set is always one click away on the well's own detail page.
 */
function summariseWorkByWell(tasks) {
  const byWell = new Map()

  for (const task of tasks) {
    const label = task.activity_description || 'Activity not mapped'
    let entry = byWell.get(task.well_id)
    if (!entry) {
      entry = { counts: new Map(), order: [] }
      byWell.set(task.well_id, entry)
    }
    if (!entry.counts.has(label)) {
      entry.counts.set(label, 0)
      entry.order.push(label)
    }
    entry.counts.set(label, entry.counts.get(label) + 1)
  }

  const result = new Map()
  for (const [wellId, entry] of byWell) {
    let top = entry.order[0]
    for (const label of entry.order) {
      if (entry.counts.get(label) > entry.counts.get(top)) top = label
    }
    result.set(wellId, { label: top, distinctCount: entry.order.length })
  }
  return result
}
