const TARGET_LABELS = {
  investigation: "investigation.sql",
  slipped_wells: "slipped_wells.sql",
  calculation: "calculation.sql",
};

export default function SqlRegenerationSummary({ sqlRegeneration }) {
  if (!sqlRegeneration) return null;

  if (sqlRegeneration.disabled) {
    return (
      <div className="caption sql-regen-line">
        Structure fingerprint {sqlRegeneration.fingerprint_changed ? "CHANGED" : "unchanged"} —
        SQL regeneration is switched off (SQL_AUTO_REGENERATE), so no .sql file was touched.
      </div>
    );
  }

  if (sqlRegeneration.error) {
    return (
      <div className="caption sql-regen-line sql-regen-warning">
        SQL regeneration did not run: {sqlRegeneration.error}
      </div>
    );
  }

  const entries = Object.entries(sqlRegeneration.results ?? {});
  if (entries.length === 0) return null;

  return (
    <>
      {entries.map(([target, result]) => {
        const label = TARGET_LABELS[target] ?? target;

        if (!result.changed) {
          return (
            <div key={target} className="caption sql-regen-line">
              {label}: schema unchanged — left as-is
            </div>
          );
        }

        if (result.status === "success") {
          return (
            <div key={target} className="caption sql-regen-line sql-regen-success">
              {label}: schema changed — regenerated ({result.attempts} attempt{result.attempts === 1 ? "" : "s"})
            </div>
          );
        }

        return (
          <div key={target} className="caption sql-regen-line sql-regen-warning">
            {label}: schema changed but regeneration FAILED after {result.attempts} attempt{result.attempts === 1 ? "" : "s"} — kept the existing file. {result.last_reason}
          </div>
        );
      })}
    </>
  );
}
