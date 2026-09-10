import { useState } from "react";
import { checkWell } from "../api.js";
import AnalysisMarkdown from "./AnalysisMarkdown.jsx";

export default function InvestigationPanel() {
  const [wellIdInput, setWellIdInput] = useState("");
  const [state, setState] = useState({ status: "idle" });
  const wellId = Number(wellIdInput);
  const isValidWellId = Number.isInteger(wellId) && wellId > 0;

  async function handleInvestigate(event) {
    event.preventDefault();
    if (!isValidWellId) {
      setState({ status: "validation", message: "Enter a valid Well ID." });
      return;
    }

    setState({ status: "loading" });
    try {
      const result = await checkWell(wellId);
      if (!result?.success) {
        setState({ status: "failure" });
        return;
      }
      setState({
        status: "success",
        responseWellId: result.well_id ?? wellId,
        rowCount: result.row_count ?? null,
        analysis: result.analysis ?? null,
        analysisError: result.analysis_error ?? null,
        message: result.message ?? null,
      });
    } catch (err) {
      setState({ status: "error", kind: err.kind, message: err.message, detail: err.detail });
    }
  }

  const isLoading = state.status === "loading";
  return (
    <section className="panel investigation-search">
      <div className="investigation-heading"><div className="ai-orbit">✦</div><div><p className="eyebrow accent">Decision support</p><h2>Investigate a well</h2></div></div>
      <p className="panel-copy">Use the delay analyst to turn schedule evidence into a concise operational brief.</p>
      <form className="investigation-form" onSubmit={handleInvestigate}>
        <label htmlFor="well-id">Well ID<input id="well-id" type="number" min="1" step="1" value={wellIdInput} onChange={(event) => setWellIdInput(event.target.value)} placeholder="e.g. 10204" required /></label>
        <button className="btn-primary" type="submit" disabled={isLoading}><span>{isLoading ? "Investigating..." : "Run investigation"}</span><span aria-hidden="true">→</span></button>
      </form>

      {state.status === "validation" && <div className="banner warning">{state.message}</div>}
      {state.status === "success" && (
        <>
          <div className="banner success">
            Well {state.responseWellId} investigated successfully.
            {state.rowCount !== null && <div className="caption">{state.rowCount === 0 ? "No delayed activity rows were returned." : `${state.rowCount} delayed activity rows were processed.`}</div>}
            {state.message && <div className="caption">{state.message}</div>}
          </div>
          {state.analysis && <div className="analysis"><div className="analysis-label"><span>AI delay brief</span><span className="analysis-live">Generated</span></div><AnalysisMarkdown content={state.analysis} /></div>}
          {!state.analysis && state.analysisError && <div className="banner warning">Delay analysis unavailable.<div className="caption">{state.analysisError}</div></div>}
        </>
      )}
      {state.status === "failure" && <div className="banner error">Failed to investigate Well {wellId}.</div>}
      {state.status === "error" && <div className="banner error">
        {state.kind === "connection" ? "Could not connect to the backend." : state.kind === "timeout" ? "Investigation request timed out." : state.kind === "http" ? "Investigation API returned an error." : state.message || "Unexpected investigation error."}
        {state.kind === "http" && state.detail && <div className="caption">{state.detail}</div>}
      </div>}
    </section>
  );
}