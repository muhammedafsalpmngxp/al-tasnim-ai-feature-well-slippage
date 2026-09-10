function delayLabel(value) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return value;
  return numeric > 0 ? `+${numeric}d` : `${numeric}d`;
}

function statusTone(status) {
  const key = String(status ?? "").toUpperCase();

  if (["DELAYED", "CRITICAL", "LATE"].includes(key)) return "is-delayed";
  if (["AHEAD", "ON_SCHEDULE", "COMPLETED"].includes(key)) return "is-good";
  if (["NOT_YET_DUE", "NO_EXPECTED_DATE"].includes(key)) return "is-neutral";

  return "is-neutral";
}

export default function WellsTable({ wells, selectedWellId, onSelectWell }) {
  if (wells.length === 0) return null;

  return (
    <section className="panel roster-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow accent">Watchlist</p>
          <h2>Slipped wells</h2>
        </div>
        <span className="count-pill">{wells.length} tracked</span>
      </div>
      <p className="panel-copy">Select a well to review milestone slippage, expected dates, and current operational risk.</p>
      <div className="table-wrap well-list-wrap">
        <table className="well-list">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Well</th>
              <th scope="col">Rig-on</th>
              <th scope="col">Rig-off</th>
              <th scope="col">Delay</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {wells.map((well, index) => {
              const selected = Number(well.well_id) === Number(selectedWellId);
              const status = well.rig_on_status || well.rig_off_status || well.hookup_status || "DELAYED";

              return (
                <tr
                  key={well.well_id}
                  className={selected ? "is-selected" : ""}
                  onClick={() => onSelectWell?.(well.well_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectWell?.(well.well_id);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                >
                  <td className="row-number">{String(index + 1).padStart(2, "0")}</td>
                  <td className="well-id">{well.well_id}</td>
                  <td>{well.ex_rig_on_date ? well.ex_rig_on_date.split("T")[0] : "—"}</td>
                  <td>{well.ex_rig_off_date ? well.ex_rig_off_date.split("T")[0] : "—"}</td>
                  <td className="delay-cell">{delayLabel(well.rig_on_delay_days ?? well.rig_off_delay_days ?? well.hookup_delay_days)}</td>
                  <td>
                    <span className={`status-badge ${statusTone(status)}`}>
                      <span className="status-dot" />{String(status).replace(/_/g, " ")}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}