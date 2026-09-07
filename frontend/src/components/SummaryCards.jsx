export default function SummaryCards({ summary }) {
  if (!summary) return null

  return (
    <section className="cards">
      <div className="card">
        <span className="card-label">Total wells</span>
        <span className="card-value">{summary.total_wells}</span>
        <span className="card-hint">all wells on record</span>
      </div>

      <div className="card">
        <span className="card-label">Live wells</span>
        <span className="card-value">{summary.live_wells}</span>
        <span className="card-hint">
          detection scope · {summary.completed_wells} hooked up
        </span>
      </div>

      <div className="card card-danger">
        <span className="card-label">Slipped — due</span>
        <span className="card-value">{summary.slipped_wells}</span>
        <span className="card-hint">Tasnim scope</span>
      </div>

      <div className="card card-warning">
        <span className="card-label">Slipped — non-due</span>
        <span className="card-value">{summary.non_due_wells}</span>
        <span className="card-hint">FLAF / SCR / PDO — bonus potential</span>
      </div>

      <div className="card">
        <span className="card-label">Not slipped</span>
        <span className="card-value">{summary.not_slipped_wells}</span>
        <span className="card-hint">of live wells</span>
      </div>
    </section>
  )
}
