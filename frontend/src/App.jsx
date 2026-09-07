import { useEffect, useState } from 'react'

import { getSummary, getSlippedWells, getWellInvestigation } from './api.js'
import SummaryCards from './components/SummaryCards.jsx'
import WellSelect from './components/WellSelect.jsx'
import WellDetail from './components/WellDetail.jsx'

export default function App() {
  const [summary, setSummary] = useState(null)
  const [wells, setWells] = useState([])
  const [loadError, setLoadError] = useState(null)
  const [loading, setLoading] = useState(true)

  const [selectedWellId, setSelectedWellId] = useState('')
  const [detail, setDetail] = useState(null)
  const [detailError, setDetailError] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [summaryData, slippedData] = await Promise.all([
          getSummary(),
          getSlippedWells()
        ])

        if (cancelled) return

        setSummary(summaryData)
        setWells(slippedData.wells || [])
      } catch (error) {
        if (!cancelled) setLoadError(error.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()

    return () => {
      cancelled = true
    }
  }, [])

  async function checkWell(wellId) {
    setSelectedWellId(wellId)
    setDetail(null)
    setDetailError(null)

    if (!wellId) return

    setDetailLoading(true)

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
          <code>cd backend &amp;&amp; uvicorn main:app --reload</code>
        </div>
      )}

      {!loading && !loadError && (
        <>
          <SummaryCards summary={summary} />

          <section className="section">
            <h2>Select a slipped well</h2>
            <p className="muted">Ranked by delay, most delayed first.</p>

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

          {detail && <WellDetail detail={detail} />}
        </>
      )}
    </div>
  )
}
