import { useCallback, useEffect, useState } from 'react'
import Header from '../../components/MorningBrief/Header'
import DayStrip from '../../components/DayStrip/DayStrip'
import WellList from '../../components/WellList/WellList'
import WellDetail from '../../components/WellDetail/WellDetail'
import ExplainPanel from '../../components/ExplainPanel/ExplainPanel'
import MilestonesPage from '../../components/MilestoneBanner/MilestonesPage'
import { ErrorState, LoadingBlock } from '../../components/common'
import useApiResource from '../../hooks/useApiResource'
import useDailyBrief from '../../hooks/useDailyBrief'
import useTheme from '../../hooks/useTheme'
import api from '../../services/api'

/**
 * The drill-down journey:
 *
 *   Daily Morning Brief -> Well -> Task -> Explain
 *
 * One row per well is the whole front page; everything else is one click
 * away. This component routes between levels and keeps Back navigation
 * honest; it performs no business calculation.
 */
export default function DailyMorningBrief() {
  const {
    reportDate,
    selectDate,
    refresh,
    refreshToken,
    summary,
    health,
    recentDates,
    current,
    breadcrumbs,
    drillTo,
    goBack,
    goToLevel,
  } = useDailyBrief()

  const { theme, toggle: toggleTheme } = useTheme()

  const [explainRequest, setExplainRequest] = useState(null)

  // An open explanation always describes one specific selection on one
  // specific date. Changing the date makes every currently-open one stale
  // at a glance -- rather than leave it sitting open describing a date the
  // operator has since navigated away from, close it the moment the date
  // changes, the same way the drill-down path already resets.
  useEffect(() => {
    setExplainRequest(null)
  }, [reportDate])

  const milestones = useApiResource((signal) => api.wellMilestones(undefined, signal), [])

  /**
   * The per-well rollup for the whole day: the same `/group-details` endpoint
   * used everywhere a slice of the day is drilled into, called with no filter
   * at all. That is a well-defined query, not a special case -- it selects
   * every task for the date, from the same cached dataset the summary call
   * already resolved, so this costs a second cheap request rather than a
   * second database round trip.
   *
   * Depends on `refreshToken`, not just `reportDate`: this is the data behind
   * the main dashboard, so pressing "Refresh" must reload it exactly the same
   * way it reloads `summary` -- otherwise Refresh would silently leave the
   * well list showing the previous load while everything else updated.
   */
  const wellsForDay = useApiResource(
    (signal) => api.groupDetails({ date: reportDate, refresh: refreshToken > 0 }, signal),
    [reportDate, refreshToken],
  )

  /**
   * The other half of each well row: its task activity as of the selected
   * date -- incomplete tasks, ongoing tasks, whether it reported anything on
   * the date, and when it was last seen in the task records. Computed
   * entirely by the backend over the live well universe, not over one date's
   * task rows, which is why a well with nothing to report today is still on
   * the page.
   *
   * Depends on `refreshToken` for exactly the same reason `wellsForDay` does:
   * these figures sit on the same rows, so "Refresh" must reload both or the
   * two halves of a row would be from different loads.
   */
  const wellActivity = useApiResource(
    (signal) => api.wellActivity({ date: reportDate, refresh: refreshToken > 0 }, signal),
    [reportDate, refreshToken],
  )

  const openWell = useCallback(
    (wellId) => {
      setExplainRequest(null)
      drillTo({ type: 'well', label: `Well ${wellId}`, wellId })
    },
    [drillTo],
  )

  const openMilestones = useCallback(() => {
    setExplainRequest(null)
    drillTo({ type: 'milestones', label: 'Upcoming Milestones' })
  }, [drillTo])

  const explainCurrent = useCallback(() => {
    const request = { report_date: reportDate, scope: 'day' }
    if (current?.type === 'well') {
      Object.assign(request, { scope: 'well', well_id: current.wellId })
    }
    setExplainRequest(request)
  }, [current, reportDate])

  return (
    <div className="app">
      <Header
        reportDate={reportDate}
        onSelectDate={selectDate}
        onRefresh={refresh}
        loading={summary.loading}
        recentDates={recentDates.data?.dates}
        health={health.loading ? null : health.data}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <main className="app__main">
        {!current && summary.data ? (
          <DayStrip
            totals={summary.data.totals}
            milestones={milestones}
            onOpenMilestones={openMilestones}
          />
        ) : null}

        <Breadcrumbs crumbs={breadcrumbs} onNavigate={goToLevel} />

        <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
          {current ? (
            <button type="button" className="btn" onClick={goBack}>
              ← Back
            </button>
          ) : null}
          {current?.type !== 'milestones' ? (
            <button type="button" className="btn" onClick={explainCurrent}>
              Explain this view
            </button>
          ) : null}
        </div>

        <ExplainPanel request={explainRequest} onClose={() => setExplainRequest(null)} />

        {!current ? (
          <SummaryLevel
            resource={wellsForDay}
            activityResource={wellActivity}
            reportDate={reportDate}
            onSelectWell={openWell}
          />
        ) : current.type === 'milestones' ? (
          <MilestonesPage resource={milestones} />
        ) : (
          <WellLevel step={current} reportDate={reportDate} />
        )}
      </main>
    </div>
  )
}

function Breadcrumbs({ crumbs, onNavigate }) {
  return (
    <nav className="breadcrumbs" aria-label="Drill-down path">
      {crumbs.map((crumb, index) => {
        const isLast = index === crumbs.length - 1
        return (
          <span key={`${crumb.label}-${index}`} style={{ display: 'inline-flex', alignItems: 'center' }}>
            {index > 0 ? <span className="breadcrumbs__sep">›</span> : null}
            <button
              type="button"
              className={`breadcrumbs__crumb${isLast ? ' breadcrumbs__crumb--current' : ''}`}
              onClick={isLast ? undefined : () => onNavigate(crumb.level)}
              aria-current={isLast ? 'page' : undefined}
            >
              {crumb.label}
            </button>
          </span>
        )
      })}
    </nav>
  )
}

function SummaryLevel({ resource, activityResource, reportDate, onSelectWell }) {
  if (resource.loading) return <LoadingBlock />
  if (resource.error) return <ErrorState error={resource.error} onRetry={resource.reload} />
  if (!resource.data) return null

  // The day's own rollup decides whether this level can render at all; the
  // task-activity call is additive, so its own loading/error state is reported
  // inside the list rather than replacing the whole page with an error.
  return (
    <WellList
      resource={resource}
      activityResource={activityResource}
      reportDate={reportDate}
      onSelectWell={onSelectWell}
    />
  )
}

function WellLevel({ step, reportDate }) {
  const resource = useApiResource(
    (signal) => api.wellDetail(step.wellId, reportDate, signal),
    [reportDate, step.wellId],
  )

  if (resource.loading) return <LoadingBlock message="Loading well detail…" />
  if (resource.error) return <ErrorState error={resource.error} onRetry={resource.reload} />
  if (!resource.data) return null

  return <WellDetail result={resource.data} />
}
