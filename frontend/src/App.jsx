import { useEffect, useState } from "react";
import { getSlippedWells, refreshSchema } from "./api.js";
import KpiCards from "./components/KpiCards.jsx";
import WellsTable from "./components/WellsTable.jsx";
import WellDetail from "./components/WellDetail.jsx";
import InvestigationPanel from "./components/InvestigationPanel.jsx";
import DbSettingsPanel from "./components/DbSettingsPanel.jsx";
import SqlRegenerationSummary from "./components/SqlRegenerationSummary.jsx";

export default function App() {
  const [pageState, setPageState] = useState({ status: "loading" });
  const [wells, setWells] = useState([]);
  const [calculations, setCalculations] = useState(null);
  const [selectedWellId, setSelectedWellId] = useState(null);
  const [showDbSettings, setShowDbSettings] = useState(false);
  const [schemaRefreshState, setSchemaRefreshState] = useState({ status: "idle" });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setPageState({ status: "loading" });
      try {
        const result = await getSlippedWells();
        if (cancelled) return;
        if (!result?.success || !Array.isArray(result.wells)) {
          setPageState({ status: "error", message: "Invalid response received from backend." });
          return;
        }

        const normalizedWells = [...new Map(
          result.wells
            .filter((well) => well && Number.isFinite(Number(well.well_id)))
            .map((well) => [String(well.well_id), { ...well, well_id: Number(well.well_id) }])
        ).values()].sort((a, b) => Number(a.well_id) - Number(b.well_id));

        setWells(normalizedWells);
        setCalculations(result.calculations ?? null);
        setSelectedWellId((current) => current ?? normalizedWells[0]?.well_id ?? null);
        setPageState({ status: normalizedWells.length ? "ready" : "empty" });
      } catch (err) {
        if (!cancelled) setPageState({ status: "error", message: err.message || "Unable to load slipped wells." });
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  const selectedWell = wells.find((well) => Number(well.well_id) === Number(selectedWellId)) ?? wells[0] ?? null;
  const isRefreshingSchema = schemaRefreshState.status === "loading";

  async function handleRefreshSchema() {
    setSchemaRefreshState({ status: "loading" });
    try {
      const result = await refreshSchema();
      setSchemaRefreshState({
        status: "success",
        database: result.database,
        tables: result.tables,
        columns: result.columns,
        hintTables: result.hint_tables ?? 0,
        sqlRegeneration: result.sql_regeneration ?? null,
      });
    } catch (err) {
      setSchemaRefreshState({ status: "error", message: err.message || "Unable to refresh the schema." });
    }
  }

  return (
    <div className="page">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">WT</div>
          <div>
            <p className="eyebrow topbar-eyebrow">Operations intelligence</p>
            <h1>Well Slippage Dashboard</h1>
          </div>
        </div>
        <div className="topbar-actions">
          <button type="button" className="btn-settings" onClick={handleRefreshSchema} disabled={isRefreshingSchema}>
            {isRefreshingSchema ? "⟳ Refreshing..." : "⟳ Refresh Schema"}
          </button>
          <button type="button" className="btn-settings" onClick={() => setShowDbSettings((current) => !current)}>
            ⚙ Database
          </button>
          <div className="live-status"><span className="status-dot" />Live schedule watch</div>
        </div>
      </header>

      <main>
        {showDbSettings && <DbSettingsPanel onClose={() => setShowDbSettings(false)} />}

        {schemaRefreshState.status === "loading" && (
          <div className="banner warning">
            Reading the database structure and rebuilding the schema and hint files —
            this can take a few minutes.
          </div>
        )}
        {schemaRefreshState.status === "success" && (
          <div className="banner success is-dismissible">
            <span>
              Schema refreshed for {schemaRefreshState.database}: {schemaRefreshState.tables} tables,
              {" "}{schemaRefreshState.columns} columns, {schemaRefreshState.hintTables} lookup tables with value hints.
              <SqlRegenerationSummary sqlRegeneration={schemaRefreshState.sqlRegeneration} />
            </span>
            <button type="button" className="btn-close" onClick={() => setSchemaRefreshState({ status: "idle" })} aria-label="Dismiss">✕</button>
          </div>
        )}
        {schemaRefreshState.status === "error" && (
          <div className="banner error is-dismissible">
            <span>{schemaRefreshState.message}</span>
            <button type="button" className="btn-close" onClick={() => setSchemaRefreshState({ status: "idle" })} aria-label="Dismiss">✕</button>
          </div>
        )}

        <div className="page-intro">
          <div>
            <p className="eyebrow accent">Asset performance</p>
            <h2>Delayed well portfolio</h2>
          </div>
          <div className="date-chip">
            <span className="date-chip-label">Review date</span>
            <strong>{new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}</strong>
          </div>
        </div>

        {pageState.status === "loading" && <div className="loading-state"><span className="loader" />Loading slipped wells...</div>}
        {pageState.status === "error" && <div className="banner error">{pageState.message}</div>}
        {pageState.status === "empty" && <div className="banner success">No slipped wells found.</div>}
        {pageState.status === "ready" && (
          <>
            <KpiCards calculations={calculations} />
            <div className="workspace-grid">
              <WellsTable
                wells={wells}
                selectedWellId={selectedWellId}
                onSelectWell={setSelectedWellId}
              />
              <WellDetail well={selectedWell} />
            </div>
            <InvestigationPanel />
          </>
        )}
      </main>

      <footer>
        <span>Well schedule watch</span>
        <span>Aligned to operational review cycle</span>
      </footer>
    </div>
  );
}