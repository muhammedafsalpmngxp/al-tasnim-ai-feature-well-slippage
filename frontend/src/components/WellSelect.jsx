import { useMemo, useState } from 'react'

function optionLabel(well) {
  const days = Math.round(well.delay_days)
  const late = days === 1 ? '1 day late' : `${days} days late`
  const reasons = well.slip_reasons?.length ? ` · ${well.slip_reasons.join(', ')}` : ''

  return `Well ${well.well_id} — ${late}${reasons}`
}

export default function WellSelect({ wells, selectedWellId, onSelect }) {
  const [search, setSearch] = useState('')

  const matches = useMemo(() => {
    const query = search.trim().toLowerCase()

    if (!query) return wells

    return wells.filter((well) => {
      const haystack = [
        String(well.well_id),
        ...(well.slip_reasons || []),
        well.kpi_miss_reason || ''
      ]
        .join(' ')
        .toLowerCase()

      return haystack.includes(query)
    })
  }, [wells, search])

  if (!wells.length) {
    return <p className="muted">No slipped wells found.</p>
  }

  const due = matches.filter((well) => well.due_status === 'DUE')
  const nonDue = matches.filter((well) => well.due_status !== 'DUE')

  return (
    <div className="well-picker">
      <input
        className="well-search"
        type="search"
        list="well-id-options"
        placeholder="Type a well ID to search…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />

      {/* Native typeahead over the well IDs themselves. */}
      <datalist id="well-id-options">
        {wells.map((well) => (
          <option key={well.well_id} value={well.well_id} />
        ))}
      </datalist>

      <select
        className="well-select"
        value={selectedWellId}
        onChange={(event) => onSelect(event.target.value)}
        size={1}
      >
        <option value="">
          {matches.length === wells.length
            ? '— Select a well —'
            : `— ${matches.length} of ${wells.length} wells match —`}
        </option>

        {due.length > 0 && (
          <optgroup label={`Due — Tasnim scope (${due.length})`}>
            {due.map((well) => (
              <option key={well.well_id} value={well.well_id}>
                {optionLabel(well)}
              </option>
            ))}
          </optgroup>
        )}

        {nonDue.length > 0 && (
          <optgroup label={`Non-due — bonus potential (${nonDue.length})`}>
            {nonDue.map((well) => (
              <option key={well.well_id} value={well.well_id}>
                {`${optionLabel(well)} · ${well.kpi_miss_reason || 'no reason recorded'}`}
              </option>
            ))}
          </optgroup>
        )}
      </select>

      {search.trim() && matches.length === 0 && (
        <p className="muted">No well matches “{search.trim()}”.</p>
      )}
    </div>
  )
}
