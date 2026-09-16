/**
 * The only place the frontend talks to the backend.
 *
 * Presentation components never call fetch directly, and nothing here
 * interprets or recalculates a business value: every count, total and status
 * arrives already classified by the backend.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, { status, kind } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    // 'database' when the backend could not reach SQL Server, so the dashboard
    // can tell an outage apart from a day that simply has no records.
    this.kind = kind || (status === 503 ? 'database' : 'api')
  }
}

function buildUrl(path, params = {}) {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin)
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) return
    url.searchParams.set(key, String(value))
  })
  return url.toString().replace(window.location.origin, '')
}

async function request(path, { params, method = 'GET', body, signal } = {}) {
  let response
  try {
    response = await fetch(buildUrl(path, params), {
      method,
      signal,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError(
      'Cannot reach the Daily Morning Brief API. Check that the backend is running.',
      { kind: 'network' },
    )
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`
    try {
      const payload = await response.json()
      if (payload?.detail) detail = payload.detail
    } catch {
      /* keep the default message */
    }
    throw new ApiError(detail, { status: response.status })
  }

  return response.json()
}

export const api = {
  health: (signal) => request('/api/health', { signal }),

  summary: (date, { refresh = false, signal } = {}) =>
    request('/api/daily/summary', { params: { date, refresh: refresh || undefined }, signal }),

  details: (date, signal) => request('/api/daily/details', { params: { date }, signal }),

  /**
   * Wells and tasks behind one summary figure. The filtering is done by the
   * backend against its own classifications -- React never decides which rows
   * belong to a status.
   */
  groupDetails: ({ date, status, wbs, activityCode, uom, refresh = false }, signal) =>
    request('/api/daily/group-details', {
      params: { date, status, wbs, activity_code: activityCode, uom, refresh: refresh || undefined },
      signal,
    }),

  wellDetail: (wellId, date, signal) =>
    request(`/api/daily/well/${wellId}`, { params: { date }, signal }),

  recentDates: (limit, signal) =>
    request('/api/daily/dates', { params: { limit }, signal }),

  /**
   * Live wells approaching (or past) a pegging / FLAF / rig-on / rig-off
   * deadline. Evaluated against today, independent of the selected report date.
   */
  wellMilestones: (windowDays, signal) =>
    request('/api/daily/milestones', { params: { window_days: windowDays }, signal }),

  explain: (payload, signal) =>
    request('/api/daily/explain', { method: 'POST', body: payload, signal }),

  exportUrl: (date) => buildUrl('/api/daily/export', { date }),
}

export default api
