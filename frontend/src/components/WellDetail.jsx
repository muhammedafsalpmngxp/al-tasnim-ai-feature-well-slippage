import { daysBetween, formatDate, today } from "../utils.js";

function MilestoneBanner({ label, expectedDate, actualDate }) {
  if (expectedDate && actualDate) {
    const slippageDays = daysBetween(actualDate, expectedDate);

    if (slippageDays === null) {
      return null;
    }

    if (slippageDays > 0) {
      return (
        <div className="banner warning">
          ⚠️ {label} Slippage: <strong>{slippageDays} days</strong>
        </div>
      );
    }

    if (slippageDays === 0) {
      return (
        <div className="banner success">{label} completed on schedule.</div>
      );
    }

    return (
      <div className="banner info">
        {label} completed {Math.abs(slippageDays)} days early.
      </div>
    );
  }

  if (expectedDate) {
    const pendingDays = daysBetween(today(), expectedDate);

    if (pendingDays !== null && pendingDays > 0) {
      return (
        <div className="banner warning">
          ⚠️ {label} is pending and <strong>{pendingDays} days</strong> past the
          expected date.
        </div>
      );
    }
  }

  return null;
}

export default function WellDetail({ well }) {
  const expectedRigOn = well.ex_rig_on_date ?? null;
  const actualRigOn = well.rig_on_date ?? null;
  const expectedRigOff = well.ex_rig_off_date ?? null;
  const actualRigOff = well.rig_off_date ?? null;
  const rig = well.rig_id ?? null;

  return (
    <section>
      <h2>Selected Well: {well.well_id}</h2>

      <div className="detail-grid">
        <div>
          <div className="caption">Well ID</div>
          <div className="detail-value">{well.well_id}</div>
        </div>
        <div>
          <div className="caption">Rig</div>
          <div className="detail-value">{rig ?? "N/A"}</div>
        </div>
        <div>
          <div className="caption">Expected Rig On</div>
          <div className="detail-value">{formatDate(expectedRigOn)}</div>
        </div>
        <div>
          <div className="caption">Actual Rig On</div>
          <div className="detail-value">
            {actualRigOn ? formatDate(actualRigOn) : "Pending"}
          </div>
        </div>
        <div>
          <div className="caption">Expected Rig Off</div>
          <div className="detail-value">{formatDate(expectedRigOff)}</div>
        </div>
        <div>
          <div className="caption">Actual Rig Off</div>
          <div className="detail-value">
            {actualRigOff ? formatDate(actualRigOff) : "Pending"}
          </div>
        </div>
      </div>

      <MilestoneBanner
        label="Rig-On"
        expectedDate={expectedRigOn}
        actualDate={actualRigOn}
      />

      <MilestoneBanner
        label="Rig-Off"
        expectedDate={expectedRigOff}
        actualDate={actualRigOff}
      />
    </section>
  );
}
