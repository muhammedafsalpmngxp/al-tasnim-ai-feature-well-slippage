import { formatDate } from "../utils.js";

function statusTone(status) {
  const key = String(status ?? "").toUpperCase();

  if (["DELAYED", "CRITICAL", "LATE"].includes(key)) return "is-delayed";
  if (["AHEAD", "ON_SCHEDULE", "COMPLETED"].includes(key)) return "is-good";
  if (["NOT_YET_DUE", "NO_EXPECTED_DATE"].includes(key)) return "is-neutral";

  return "is-neutral";
}

function delayText(value) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return value;
  return numeric > 0 ? `+${numeric} days` : `${numeric} days`;
}

export default function WellDetail({ well }) {
  if (!well) {
    return (
      <section className="panel detail-panel empty-detail">
        <p className="panel-copy">Select a well from the roster to review the detailed schedule status.</p>
      </section>
    );
  }

  const summaryStatus =
    [well.rig_on_status, well.rig_off_status, well.hookup_status].find((status) => status === "DELAYED")
      ?? "MONITORING";

  return (
    <section className="panel detail-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow accent">Well focus</p>
          <h2>Well {well.well_id}</h2>
        </div>
        <span className={`status-badge detail-badge ${statusTone(summaryStatus)}`}>
          <span className="status-dot" />{String(summaryStatus).replace(/_/g, " ")}
        </span>
      </div>

      <p className="panel-copy">Operational overview and live milestone slippage signals for this asset.</p>

      <div className="detail-header">
        <div className="detail-stat">
          <span>Station</span>
          <strong>{well.station_id ?? "—"}</strong>
        </div>
        <div className="detail-stat">
          <span>Well type</span>
          <strong>{well.well_type_id ?? "—"}</strong>
        </div>
      </div>

      <div className="milestone-stack">
        <article className="milestone-card">
          <div className="milestone-head">
            <h3>Rig-on milestone</h3>
            <span className={`status-badge ${statusTone(well.rig_on_status)}`}>
              <span className="status-dot" />{well.rig_on_status ? String(well.rig_on_status).replace(/_/g, " ") : "NO DATE"}
            </span>
          </div>
          <div className="milestone-meta">
            <div><label>Expected</label><strong>{formatDate(well.ex_rig_on_date)}</strong></div>
            <div><label>Actual</label><strong>{formatDate(well.rig_on_date)}</strong></div>
            <div><label>Delay</label><strong>{delayText(well.rig_on_delay_days)}</strong></div>
          </div>
        </article>

        <article className="milestone-card">
          <div className="milestone-head">
            <h3>Rig-off milestone</h3>
            <span className={`status-badge ${statusTone(well.rig_off_status)}`}>
              <span className="status-dot" />{well.rig_off_status ? String(well.rig_off_status).replace(/_/g, " ") : "NO DATE"}
            </span>
          </div>
          <div className="milestone-meta">
            <div><label>Expected</label><strong>{formatDate(well.ex_rig_off_date)}</strong></div>
            <div><label>Actual</label><strong>{formatDate(well.rig_off_date)}</strong></div>
            <div><label>Delay</label><strong>{delayText(well.rig_off_delay_days)}</strong></div>
          </div>
        </article>

        <article className="milestone-card">
          <div className="milestone-head">
            <h3>Hook-up completion</h3>
            <span className={`status-badge ${statusTone(well.hookup_status)}`}>
              <span className="status-dot" />{well.hookup_status ? String(well.hookup_status).replace(/_/g, " ") : "NO DATE"}
            </span>
          </div>
          <div className="milestone-meta">
            <div><label>Deadline</label><strong>{formatDate(well.hookup_deadline)}</strong></div>
            <div><label>Completion</label><strong>{formatDate(well.eng_completion_date)}</strong></div>
            <div><label>Delay</label><strong>{delayText(well.hookup_delay_days)}</strong></div>
          </div>
        </article>
      </div>
    </section>
  );
}
