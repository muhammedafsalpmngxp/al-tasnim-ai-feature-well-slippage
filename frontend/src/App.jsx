import { useEffect, useState } from 'react'

import {
  getSummary,
  getWellList,
  getWellInvestigation,
  getPortfolioInsight,
  getWellInsight
} from './api.js'
import SummaryCards from './components/SummaryCards.jsx'
import WellSelect from './components/WellSelect.jsx'
import WellDetail from './components/WellDetail.jsx'
import InsightPanel from './components/InsightPanel.jsx'

export default function App() {
  const [summary, setSummary] = useState(null)
  const [wells, setWells] = useState([])
  const [loadError, setLoadError] = useState(null)
  const [loading, setLoading] = useState(true)

  const [portfolioInsight, setPortfolioInsight] = useState(null)
  const [portfolioInsightError, setPortfolioInsightError] = useState(null)

  const [selectedWellId, setSelectedWellId] = useState('')
  const [detail, setDetail] = useState(null)
  const [detailError, setDetailError] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [wellInsight, setWellInsight] = useState(null)
  const [wellInsightError, setWellInsightError] = useState(null)
  const [wellInsightLoading, setWellInsightLoading] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [summaryData, wellListData] = await Promise.all([
          getSummary(),
          getWellList()
        ])

        if (cancelled) return

        setSummary(summaryData)
        setWells(wellListData.wells || [])
      } catch (error) {
        if (!cancelled) setLoadError(error.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()

    // The narrative is fetched separately so the counts render
    // immediately and a slow or unavailable model never blocks them.
    getPortfolioInsight()
      .then((data) => {
        if (!cancelled) setPortfolioInsight(data)
      })
      .catch((error) => {
        if (!cancelled) setPortfolioInsightError(error.message)
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function checkWell(wellId) {
    setSelectedWellId(wellId)
    setDetail(null)
    setDetailError(null)
    setWellInsight(null)
    setWellInsightError(null)

    if (!wellId) return

    setDetailLoading(true)
    setWellInsightLoading(true)

    getWellInsight(wellId)
      .then((data) => {
        // Ignore a response for a well the user already moved off.
        setWellInsight((current) =>
          String(data.well_id) === String(wellId) ? data : current
        )
      })
      .catch((error) => setWellInsightError(error.message))
      .finally(() => setWellInsightLoading(false))

    try {
      setDetail(await getWellInvestigation(wellId))
    } catch (error) {
      setDetailError(error.message)
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Well Slippage Dashboard</h1>
        <p>Well slippage monitoring, risk scoring and investigation</p>
      </header>

      {loading && <p className="muted">Loading wells…</p>}

      {loadError && (
        <div className="alert alert-error">
          <strong>Cannot load wells.</strong>
          <p>{loadError}</p>
          <code>python run.py</code>
        </div>
      )}

      {!loading && !loadError && (
        <>
          <SummaryCards summary={summary} />

          <InsightPanel
            title="Portfolio summary"
            insight={portfolioInsight}
            loading={!portfolioInsight && !portfolioInsightError}
            error={portfolioInsightError}
          />

          <section className="section">
            <h2>Select a well</h2>
            <p className="muted">
              Every well on record, by ascending well ID, coloured by state.
            </p>

            <WellSelect
              wells={wells}
              selectedWellId={selectedWellId}
              onSelect={checkWell}
            />
          </section>

          {detailLoading && <p className="muted">Checking well {selectedWellId}…</p>}

          {detailError && (
            <div className="alert alert-error">
              <strong>Investigation failed.</strong>
              <p>{detailError}</p>
            </div>
          )}

          {detail && (
            <WellDetail
              detail={detail}
              insight={wellInsight}
              insightLoading={wellInsightLoading}
              insightError={wellInsightError}
            />
          )}
        </>
      )}
    </div>
  )
}
