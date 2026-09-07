import { useState } from "react";
import { checkWell } from "../api.js";

export default function InvestigationPanel({ wellId }) {
  const [state, setState] = useState({ status: "idle" });

  async function handleCheck() {
    setState({ status: "loading" });

    try {
      const result = await checkWell(wellId);

      if (result && result.success) {
        setState({
          status: "success",
          rowCount: result.row_count ?? null,
          analysis: result.analysis ?? null,
          analysisError: result.analysis_error ?? null,
        });
      } else {
        setState({ status: "failure" });
      }
    } catch (err) {
      setState({
        status: "error",
        kind: err.kind,
        message: err.message,
        detail: err.detail,
      });
    }
  }

  const isLoading = state.status === "loading";

  return (
    <section>
      <h2>🔎 Well Investigation</h2>
      <p>
        Click the button to check the selected well. The investigation result
        will be updated in the backend JSON file.
      </p>

      <button className="btn-primary" disabled={isLoading} onClick={handleCheck}>
        {isLoading ? `Checking Well ${wellId}...` : `Check This Well — ${wellId}`}
      </button>

      {state.status === "success" && (
        <>
          <div className="banner success">
            ✅ Well {wellId} checked successfully.
            {state.rowCount !== null && (
              <div className="caption">
                {state.rowCount} rows processed and investigation.json updated in
                the backend.
              </div>
            )}
          </div>

          {state.analysis && (
            <div className="analysis">
              <h3>Delay Analysis</h3>
              <p>{state.analysis}</p>
              <div className="caption">
                Generated from the investigation evidence and the project
                business rules.
              </div>
            </div>
          )}

          {!state.analysis && state.analysisError && (
            <div className="banner warning">
              ⚠️ Delay analysis unavailable.
              <div className="caption">{state.analysisError}</div>
            </div>
          )}
        </>
      )}

      {state.status === "failure" && (
        <div className="banner error">❌ Failed to check Well {wellId}.</div>
      )}

      {state.status === "error" && state.kind === "connection" && (
        <div className="banner error">
          ❌ Could not connect to the backend.
          <div className="caption">
            Make sure it is running: <code>cd backend && uvicorn main:app --reload</code>
          </div>
        </div>
      )}

      {state.status === "error" && state.kind === "timeout" && (
        <div className="banner error">❌ Investigation request timed out.</div>
      )}

      {state.status === "error" && state.kind === "http" && (
        <div className="banner error">
          ❌ Investigation API returned an error.
          {state.detail && <div className="caption">{state.detail}</div>}
        </div>
      )}

      {state.status === "error" && !state.kind && (
        <div className="banner error">
          ❌ Unexpected investigation error: {state.message}
        </div>
      )}
    </section>
  );
}
