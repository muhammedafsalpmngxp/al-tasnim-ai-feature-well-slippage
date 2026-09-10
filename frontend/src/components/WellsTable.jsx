export default function WellsTable({ wells }) {
  if (wells.length === 0) return null;

  return (
    <section className="panel roster-panel">
      <div className="panel-heading">
        <div><p className="eyebrow accent">Watchlist</p><h2>Slipped wells</h2></div>
        <span className="count-pill">{wells.length} tracked</span>
      </div>
      <p className="panel-copy">Select a well ID below to investigate schedule evidence and delay signals.</p>
      <div className="table-wrap well-list-wrap">
        <table className="well-list">
          <thead>
            <tr><th scope="col">Index</th><th scope="col">Well identifier</th><th scope="col">Status</th><th scope="col">Action</th></tr>
          </thead>
          <tbody>
            {wells.map((well, index) => (
              <tr key={well.well_id}>
                <td className="row-number">{String(index + 1).padStart(2, "0")}</td>
                <td className="well-id">{well.well_id}</td>
                <td><span className="status-badge"><span className="status-dot" />Slipped</span></td>
                <td><span className="table-arrow">View investigation <span aria-hidden="true">→</span></span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}