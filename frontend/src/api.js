const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function fetchJson(url, { timeoutMs, method, body } = {}) {
  const controller = new AbortController();
  const timer = timeoutMs
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      method: method || "GET",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });

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

export function getDbConfig() {
  return fetchJson(`${API_URL}/api/db-config`, { timeoutMs: 15000 });
}

export function updateDbConfig(dbName) {
  return fetchJson(`${API_URL}/api/db-config`, {
    timeoutMs: 15000,
    method: "POST",
    body: { db_name: dbName },
  });
}

export function refreshSchema() {
  // Introspection makes a query per candidate lookup table against a remote server, so a
  // full refresh runs into minutes on a large database.
  return fetchJson(`${API_URL}/api/schema/refresh`, {
    timeoutMs: 600000,
    method: "POST",
  });
}
