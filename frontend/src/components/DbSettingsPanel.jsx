import { useEffect, useState } from "react";
import { getDbConfig, updateDbConfig, refreshSchema } from "../api.js";
import SqlRegenerationSummary from "./SqlRegenerationSummary.jsx";

export default function DbSettingsPanel({ onClose }) {
  const [currentDbName, setCurrentDbName] = useState(null);
  const [dbNameInput, setDbNameInput] = useState("");
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const result = await getDbConfig();
        if (cancelled) return;
        setCurrentDbName(result?.db_name ?? null);
        setDbNameInput(result?.db_name ?? "");
        setState({ status: "idle" });
      } catch (err) {
        if (!cancelled) setState({ status: "error", message: err.message || "Unable to load database settings." });
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  async function handleSaveAndRefresh(event) {
    event.preventDefault();
    const dbName = dbNameInput.trim();
    if (!dbName) {
      setState({ status: "validation", message: "Enter a database name." });
      return;
    }

    setState({ status: "saving" });
    try {
      await updateDbConfig(dbName);
      setCurrentDbName(dbName);

      setState({ status: "refreshing" });
      const result = await refreshSchema();

      setState({
        status: "success",
        tables: result.tables,
        columns: result.columns,
        hintTables: result.hint_tables ?? 0,
        schemaFile: result.schema_file,
        hintsFile: result.hints_file,
        sqlRegeneration: result.sql_regeneration ?? null,
      });
    } catch (err) {
      setState({ status: "error", message: err.message || "Unable to update the database." });
    }
  }

  const isBusy = state.status === "saving" || state.status === "refreshing";

  return (
    <section className="panel db-settings-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow accent">Data source</p>
          <h2>Database settings</h2>
        </div>
        {onClose && (
          <button type="button" className="btn-close" onClick={onClose} aria-label="Close database settings">✕</button>
        )}
      </div>
      <p className="panel-copy">
        Switch the database the app reads from, then generate its schema and hint files so
        queries can be adapted to it. A full refresh can take a few minutes.
      </p>

      {currentDbName && <p className="caption">Currently connected to: <strong>{currentDbName}</strong></p>}

      <form className="investigation-form" onSubmit={handleSaveAndRefresh}>
        <label htmlFor="db-name">
          Database name
          <input
            id="db-name"
            type="text"
            value={dbNameInput}
            onChange={(event) => setDbNameInput(event.target.value)}
            placeholder="e.g. AlTasnimBI"
            required
          />
        </label>
        <button className="btn-primary" type="submit" disabled={isBusy}>
          <span>
            {state.status === "saving" && "Saving..."}
            {state.status === "refreshing" && "Reading schema..."}
            {!isBusy && "Save & generate schema"}
          </span>
          <span aria-hidden="true">→</span>
        </button>
      </form>

      {state.status === "validation" && <div className="banner warning">{state.message}</div>}
      {state.status === "error" && <div className="banner error">{state.message}</div>}
      {state.status === "success" && (
        <div className="banner success">
          Schema refreshed for {currentDbName}: {state.tables} tables, {state.columns} columns,
          {" "}{state.hintTables} lookup tables with value hints.
          <div className="caption">Schema file: {state.schemaFile}</div>
          <div className="caption">Hints file: {state.hintsFile}</div>
          <SqlRegenerationSummary sqlRegeneration={state.sqlRegeneration} />
        </div>
      )}
    </section>
  );
}
