export default function KpiCards({ wells }) {
  const liveWells = wells.filter((well) => !well.eng_completion_date).length;

  return (
    <section className="kpi-row">
      <div className="kpi-card">
        <div className="kpi-topline"><span className="kpi-icon alert-icon">!</span><span className="kpi-label">Total slipped wells</span></div>
        <div className="kpi-value">{wells.length}<span className="kpi-unit">wells</span></div>
        <div className="kpi-foot">Requires schedule review</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-topline"><span className="kpi-icon neutral-icon">LIVE</span><span className="kpi-label">Live wells</span></div>
        <div className="kpi-value">{liveWells}<span className="kpi-unit">wells</span></div>
        <div className="kpi-foot">Not yet engineering-complete</div>
      </div>
      <div className="kpi-card kpi-card-note">
        <div className="kpi-topline"><span className="kpi-icon live-icon">●</span><span className="kpi-label">Monitoring status</span></div>
        <div className="kpi-value status-value">Active</div>
        <div className="kpi-foot">Investigation service ready</div>
      </div>
    </section>
  );
}