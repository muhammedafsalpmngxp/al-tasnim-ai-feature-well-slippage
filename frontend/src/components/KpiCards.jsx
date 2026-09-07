export default function KpiCards({ wells }) {
  const slippedWellsCount = new Set(wells.map((well) => well.well_id)).size;

  const hasRigColumn = wells.some((well) => "rig_id" in well);
  const rigsCount = hasRigColumn
    ? new Set(
        wells
          .map((well) => well.rig_id)
          .filter((rigId) => rigId !== null && rigId !== undefined)
      ).size
    : null;

  return (
    <section className="kpi-row">
      <div className="kpi-card">
        <div className="kpi-label">Slipped Wells</div>
        <div className="kpi-value">{slippedWellsCount}</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">Rigs</div>
        <div className="kpi-value">{rigsCount === null ? "N/A" : rigsCount}</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">Records</div>
        <div className="kpi-value">{wells.length}</div>
      </div>
    </section>
  );
}
