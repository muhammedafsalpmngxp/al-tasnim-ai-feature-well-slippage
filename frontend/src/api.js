const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function fetchJson(url, { timeoutMs } = {}) {
  const controller = new AbortController();
  const timer = timeoutMs
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;

  try {
    const response = await fetch(url, { signal: controller.signal });

    if (!response.ok) {
      let detail = null;

      try {
        const body = await response.json();
        detail = body?.detail ?? null;
      } catch {
        // response body wasn't JSON, ignore
      }

      const error = new Error(detail || `Request failed with status ${response.status}`);
      error.kind = "http";
      error.status = response.status;
      error.detail = detail;
      throw error;
    }

    return await response.json();
  } catch (err) {
    if (err.name === "AbortError") {
      const timeoutError = new Error("The request timed out.");
      timeoutError.kind = "timeout";
      throw timeoutError;
    }

    if (err instanceof TypeError) {
      const connectionError = new Error("Cannot connect to the backend.");
      connectionError.kind = "connection";
      throw connectionError;
    }

    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export function getSlippedWells() {
  return fetchJson(`${API_URL}/api/slipped-wells`, { timeoutMs: 60000 });
}

export function checkWell(wellId) {
  return fetchJson(`${API_URL}/api/well/${wellId}/investigation`, { timeoutMs: 300000 });
}
