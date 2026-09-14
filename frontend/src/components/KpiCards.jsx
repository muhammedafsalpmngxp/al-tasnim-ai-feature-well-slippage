export default function KpiCards({ calculations }) {
  const metrics = calculations ?? {};

  return (
    <section className="kpi-row">
      <div className="kpi-card">
        <div className="kpi-topline"><span className="kpi-icon neutral-icon">ALL</span><span className="kpi-label">Total wells</span></div>
        <div className="kpi-value">{metrics.total_wells ?? "—"}<span className="kpi-unit">wells</span></div>
        <div className="kpi-foot">Active portfolio</div>
      </div>
      <div className="kpi-card kpi-card-note">
        <div className="kpi-topline"><span className="kpi-icon live-icon">LIVE</span><span className="kpi-label">Live wells</span></div>
        <div className="kpi-value">{metrics.live_wells ?? "—"}<span className="kpi-unit">wells</span></div>
        <div className="kpi-foot">Not engineering-complete</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-topline"><span className="kpi-icon alert-icon">!</span><span className="kpi-label">Slipped wells</span></div>
        <div className="kpi-value">{metrics.slipped_wells ?? "—"}<span className="kpi-unit">wells</span></div>
        <div className="kpi-foot">Requires schedule review</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-topline"><span className="kpi-icon alert-icon">AT</span><span className="kpi-label">Due: Al Tasnim</span></div>
        <div className="kpi-value">{metrics.due_wells ?? "—"}<span className="kpi-unit">wells</span></div>
        <div className="kpi-foot">Penalty review applies</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-topline"><span className="kpi-icon neutral-icon">PDO</span><span className="kpi-label">Non-due: PDO</span></div>
        <div className="kpi-value">{metrics.non_due_wells ?? "—"}<span className="kpi-unit">wells</span></div>
        <div className="kpi-foot">FLAF-originated delay</div>
      </div>
    </section>
  );
}