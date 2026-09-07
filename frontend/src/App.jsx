import { useEffect, useState } from "react";
import { getSlippedWells } from "./api.js";
import { wellSlippage } from "./utils.js";
import KpiCards from "./components/KpiCards.jsx";
import WellsTable from "./components/WellsTable.jsx";
import WellDetail from "./components/WellDetail.jsx";
import InvestigationPanel from "./components/InvestigationPanel.jsx";

function ConnectionErrorBanner() {
  return (
    <div className="banner error">
      ❌ Cannot connect to the FastAPI backend.
      <div className="caption">
        Make sure FastAPI is running: <code>cd backend && uvicorn main:app --reload</code>
      </div>
    </div>
  );
}

export default function App() {
  const [pageState, setPageState] = useState({ status: "loading" });
  const [wells, setWells] = useState([]);
  const [selectedWellId, setSelectedWellId] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setPageState({ status: "loading" });

      try {
        const result = await getSlippedWells();

        if (cancelled) return;

        if (!result || typeof result !== "object") {
          setPageState({ status: "error", kind: "invalid" });
          return;
        }

        if (!result.success) {
          setPageState({ status: "error", kind: "failure" });
          return;
        }

        const rawWells = Array.isArray(result.wells) ? result.wells : [];

        if (rawWells.length > 0 && !("well_id" in rawWells[0])) {
          setPageState({ status: "error", kind: "missing-well-id" });
          return;
        }

        const cleaned = rawWells
          .map((well) => ({ ...well, well_id: Number(well.well_id) }))
          .filter((well) => Number.isFinite(well.well_id));

        if (cleaned.length === 0) {
          setPageState({ status: "empty" });
          return;
        }

        // Rank by actual-vs-expected slippage so genuinely slipped wells lead.
        const ranked = cleaned
          .map((well) => {
            const slippage = wellSlippage(well);

            return {
              ...well,
              rig_on_slip_days: slippage.rigOn,
              rig_off_slip_days: slippage.rigOff,
              max_slip_days: slippage.max,
            };
          })
          .sort((a, b) => b.max_slip_days - a.max_slip_days);

        setWells(ranked);
        setSelectedWellId(ranked[0].well_id);
        setPageState({ status: "ready" });
      } catch (err) {
        if (cancelled) return;
        setPageState({ status: "error", kind: err.kind, message: err.message });
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, []);

  const wellIds = [...new Set(wells.map((well) => well.well_id))];
  const selectedWell = wells.find((well) => well.well_id === selectedWellId);

  return (
    <div className="page">
      <header>
        <h1>🔎 Well Slippage Dashboard</h1>
        <p className="caption">Well slippage monitoring and investigation</p>
      </header>
      <hr />

      {pageState.status === "loading" && <p>Loading slipped wells...</p>}

      {pageState.status === "error" && pageState.kind === "connection" && (
        <ConnectionErrorBanner />
      )}

      {pageState.status === "error" && pageState.kind === "timeout" && (
        <div className="banner error">
          ❌ The request to the backend timed out.
        </div>
      )}

      {pageState.status === "error" && pageState.kind === "http" && (
        <div className="banner error">
          ❌ Backend returned an HTTP error.
          {pageState.message && <div className="caption">{pageState.message}</div>}
        </div>
      )}

      {pageState.status === "error" && pageState.kind === "invalid" && (
        <div className="banner error">❌ Invalid response received from backend.</div>
      )}

      {pageState.status === "error" && pageState.kind === "failure" && (
        <div className="banner error">❌ Failed to retrieve slipped wells.</div>
      )}

      {pageState.status === "error" && pageState.kind === "missing-well-id" && (
        <div className="banner error">
          ❌ <code>well_id</code> is missing from the backend response.
        </div>
      )}

      {pageState.status === "error" &&
        !["connection", "timeout", "http", "invalid", "failure", "missing-well-id"].includes(
          pageState.kind
        ) && (
          <div className="banner error">
            ❌ Unexpected error: {pageState.message || "Unknown error."}
          </div>
        )}

      {pageState.status === "empty" && (
        <div className="banner success">✅ No slipped wells found.</div>
      )}

      {pageState.status === "ready" && (
        <>
          <KpiCards wells={wells} />
          <WellsTable wells={wells} />

          <section>
            <h2>🔍 Select a Slipped Well</h2>
            <select
              value={selectedWellId ?? ""}
              onChange={(event) => setSelectedWellId(Number(event.target.value))}
            >
              {wellIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </section>

          {selectedWell && (
            <>
              <WellDetail well={selectedWell} />
              <InvestigationPanel key={selectedWell.well_id} wellId={selectedWell.well_id} />
            </>
          )}

          <hr />
          <p className="caption">
            Investigation data is stored in the backend. LLM analysis will be
            implemented in the next stage.
          </p>
        </>
      )}
    </div>
  );
}
