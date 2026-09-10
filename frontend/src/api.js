const API_URL = (
  import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
).replace(/\/$/, '')

async function request(path) {
  let response

  try {
    response = await fetch(`${API_URL}${path}`)
  } catch (error) {
    throw new Error(
      `Cannot reach the backend at ${API_URL}. Make sure FastAPI is running.`
    )
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`

    try {
      const body = await response.json()
      if (body.detail) {
        detail = body.detail
      }
    } catch {
      // response body was not JSON — keep the status text
    }

    throw new Error(detail)
  }

  return response.json()
}

export function getSummary() {
  return request('/api/wells/summary')
}

export function getSlippedWells() {
  return request('/api/slipped-wells')
}

// Every well on record — id and category only — for the picker.
export function getWellList() {
  return request('/api/wells/list')
}

export function getWellInvestigation(wellId) {
  return request(`/api/well/${wellId}/investigation`)
}

export function getPortfolioInsight() {
  return request('/api/insights/portfolio')
}

export function getWellInsight(wellId) {
  return request(`/api/insights/well/${wellId}`)
}
