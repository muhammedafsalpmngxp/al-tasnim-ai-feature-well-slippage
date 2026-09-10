export default function KpiCards({ wells }) {
  return (
    <section className="kpi-row">
      <div className="kpi-card">
        <div className="kpi-topline"><span className="kpi-icon alert-icon">!</span><span className="kpi-label">Total slipped wells</span></div>
        <div className="kpi-value">{wells.length}<span className="kpi-unit">wells</span></div>
        <div className="kpi-foot">Requires schedule review</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-topline"><span className="kpi-icon neutral-icon">ID</span><span className="kpi-label">Tracked in roster</span></div>
        <div className="kpi-value">{wells.length}<span className="kpi-unit">records</span></div>
        <div className="kpi-foot">Unique well identifiers</div>
      </div>
      <div className="kpi-card kpi-card-note">
        <div className="kpi-topline"><span className="kpi-icon live-icon">●</span><span className="kpi-label">Monitoring status</span></div>
        <div className="kpi-value status-value">Active</div>
        <div className="kpi-foot">Investigation service ready</div>
      </div>
    </section>
  );
}