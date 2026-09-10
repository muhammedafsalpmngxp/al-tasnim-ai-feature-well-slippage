import { useMemo, useState } from 'react'

// The four states a well can be in, in the order they are grouped.
// Both the code and its display wording come from the backend
// (slipped_wells.WELL_CATEGORY_LABELS) — the order and the colour class
// are the only things decided here.
//
// AL TASNIM / PDO are the business names for the accountability split:
// a slipped well Al Tasnim owns, versus one attributed to PDO-side
// causes. Completed wells are selectable like any other.
const CATEGORY_ORDER = ['AL_TASNIM', 'PDO', 'ON_TRACK', 'COMPLETED']

export default function WellSelect({ wells, selectedWellId, onSelect }) {
  const [search, setSearch] = useState('')

  const matches = useMemo(() => {
    const query = search.trim().toLowerCase()

    if (!query) return wells

    return wells.filter((well) =>
      String(well.well_id).toLowerCase().includes(query)
    )
  }, [wells, search])

  // The list itself stays in one ascending run of well IDs — the colour
  // carries the category, so grouping would only break the ordering the
  // list is there to provide. The legend below counts each category.
  const counts = useMemo(() => {
    const tally = new Map()

    for (const well of matches) {
      const entry = tally.get(well.category)

      if (entry) {
        entry.count += 1
      } else {
        tally.set(well.category, {
          count: 1,
          label: well.category_label
        })
      }
    }

    return tally
  }, [matches])

  if (!wells.length) {
    return <p className="muted">No wells found.</p>
  }

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

        {matches.map((well) => (
          <option
            key={well.well_id}
            value={well.well_id}
            className={`well-option well-option-${well.category.toLowerCase()}`}
          >
            {well.well_id}
          </option>
        ))}
      </select>

      {/* The colour carries the state, so it needs a written key too. */}
      <ul className="well-legend">
        {CATEGORY_ORDER.map((code) => {
          const entry = counts.get(code)

          if (!entry) return null

          return (
            <li key={code} className={`well-legend-${code.toLowerCase()}`}>
              {entry.label} ({entry.count})
            </li>
          )
        })}
      </ul>

      {search.trim() && matches.length === 0 && (
        <p className="muted">No well matches “{search.trim()}”.</p>
      )}
    </div>
  )
}
