import { useEffect, useState } from "react";
import { getSlippedWells } from "./api.js";
import KpiCards from "./components/KpiCards.jsx";
import WellsTable from "./components/WellsTable.jsx";
import InvestigationPanel from "./components/InvestigationPanel.jsx";

export default function App() {
  const [pageState, setPageState] = useState({ status: "loading" });
  const [wells, setWells] = useState([]);

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
        const uniqueWells = [...new Map(
          result.wells
            .map((well) => Number(well.well_id))
            .filter(Number.isFinite)
            .map((wellId) => [wellId, { well_id: wellId }])
        ).values()];
        setWells(uniqueWells);
        setPageState({ status: uniqueWells.length ? "ready" : "empty" });
      } catch (err) {
        if (!cancelled) setPageState({ status: "error", message: err.message || "Unable to load slipped wells." });
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="page">
      <header>
        <h1>Well Slippage Dashboard</h1>
        <p className="caption">Slipped well overview</p>
      </header>
      <hr />
      {pageState.status === "loading" && <p>Loading slipped wells...</p>}
      {pageState.status === "error" && <div className="banner error">{pageState.message}</div>}
      {pageState.status === "empty" && <div className="banner success">No slipped wells found.</div>}
      {pageState.status === "ready" && <><KpiCards wells={wells} /><WellsTable wells={wells} /><InvestigationPanel /></>}
    </div>
  );
}