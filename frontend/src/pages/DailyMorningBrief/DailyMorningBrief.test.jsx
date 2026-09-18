/**
 * The page itself: that Refresh reloads every part of the front page at once.
 *
 * The well row's own figures come from two calls -- the day's rollup and the
 * well's task activity -- and a refresh that reloaded one but not the other
 * would leave two halves of the same row describing different loads. Every
 * API call is stubbed here; this asserts what the page asks for, not what
 * comes back.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DailyMorningBrief from './DailyMorningBrief'
import api from '../../services/api'

vi.mock('../../services/api', () => ({
  default: {
    health: vi.fn(),
    summary: vi.fn(),
    groupDetails: vi.fn(),
    wellActivity: vi.fn(),
    wellDetail: vi.fn(),
    recentDates: vi.fn(),
    wellMilestones: vi.fn(),
    explain: vi.fn(),
    exportUrl: vi.fn(() => '/api/daily/export'),
  },
}))

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset?.())
  api.exportUrl.mockReturnValue('/api/daily/export')
  api.health.mockResolvedValue({ status: 'ok', database: {}, llm: {}, config: {} })
  api.recentDates.mockResolvedValue({ dates: [] })
  api.wellMilestones.mockResolvedValue({
    generated_at: '', window_days: 7, upcoming: [], overdue_count: 0, overdue: [],
  })
  api.summary.mockResolvedValue({
    report_date: '2026-08-01',
    generated_at: '',
    totals: { task_count: 1, well_count: 1, status_counts: { ON_PLAN: 1 } },
    data_quality: {},
    status_groups: [],
    view_mode: 'detail',
    detail_view_task_threshold: 25,
    tasks: [],
  })
  api.groupDetails.mockResolvedValue({
    report_date: '2026-08-01',
    filters: {},
    task_count: 1,
    well_count: 1,
    wells: [{ well_id: 101, task_count: 1, status_counts: { ON_PLAN: 1 } }],
    tasks: [
      {
        well_id: 101,
        task_code: 'FLME1180-101',
        activity_description: 'Pipe Stringing',
        quantity_status: 'ON_PLAN',
      },
    ],
  })
  api.wellActivity.mockResolvedValue({
    report_date: '2026-08-01',
    well_count: 1,
    wells: [
      {
        well_id: 101,
        today_reported_task_count: 1,
        has_task_on_report_date: true,
        incomplete_task_count: 6,
        ongoing_task_count: 4,
        not_started_task_count: 1,
        ended_not_completed_task_count: 1,
        completed_task_count: 3,
        logical_task_count: 9,
        task_state_counts: {},
        last_task_date: '2026-08-01',
      },
    ],
    tasks: [],
  })
})

describe('the front page', () => {
  it('asks for both halves of the well row', async () => {
    render(<DailyMorningBrief />)
    await waitFor(() => expect(api.groupDetails).toHaveBeenCalled())
    await waitFor(() => expect(api.wellActivity).toHaveBeenCalled())
    expect(await screen.findByText('Well 101')).toBeInTheDocument()
    expect(screen.getByText('Incomplete')).toBeInTheDocument()
  })

  it('reloads the task-activity figures when Refresh is pressed', async () => {
    render(<DailyMorningBrief />)
    await screen.findByText('Well 101')
    const before = api.wellActivity.mock.calls.length

    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() =>
      expect(api.wellActivity.mock.calls.length).toBeGreaterThan(before),
    )
    // Refreshed explicitly, exactly like the day's own rollup beside it --
    // never left showing the previous load while the rest of the page updates.
    const refreshed = api.wellActivity.mock.calls.at(-1)[0]
    expect(refreshed.refresh).toBe(true)
    expect(api.groupDetails.mock.calls.at(-1)[0].refresh).toBe(true)
    expect(api.summary.mock.calls.at(-1)[1].refresh).toBe(true)
  })
})
