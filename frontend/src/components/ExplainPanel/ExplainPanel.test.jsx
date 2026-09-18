/**
 * The explanation panel: what it shows, what it says about where the text
 * came from, and how many times it asks for it.
 *
 * The fresh/cached tone is the point of most of these. A reused answer is
 * green; a freshly generated one keeps the panel's ordinary styling; and a
 * first generation must never be able to look reused, which is what the
 * single-flight test below protects -- React's development StrictMode mounts
 * the panel twice, and the second request used to come back marked cached.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ExplainPanel from './ExplainPanel'
import api from '../../services/api'

vi.mock('../../services/api', () => ({
  default: { explain: vi.fn() },
}))

const REQUEST = { report_date: '2026-08-01', scope: 'well', well_id: 101 }

function response(overrides = {}) {
  return {
    report_date: '2026-08-01',
    scope: 'well',
    available: true,
    cached: false,
    explanation: 'Well `101` has `6` incomplete tasks.',
    error: null,
    model: 'test-model',
    evidence: { well_id: 101, task_activity: { ongoing_task_count: 4 } },
    evidence_withheld_from_model: [],
    sql_sources: [
      {
        label: 'Counts on the well row (incomplete, ongoing, last task date)',
        file: 'backend/sql/well_task_activity.sql',
        parameters: ['? 1  report date = 2026-08-01'],
        sql: 'WITH params AS (SELECT CAST(? AS date) AS report_date) SELECT 1',
      },
    ],
    proof: [
      {
        well_id: 101,
        task_code: 'FLME1030-101',
        schedule_id: 12,
        activity_code: 'F-M-SLW-PWD-45',
        description: 'Pipe Stringing',
        wbs: 'Straightline Welding incl. supports',
        task_state: 'ONGOING',
        counts_as_incomplete: false,
        counts_as_ongoing: true,
        completed: false,
        actual_start: '2026-07-02',
        actual_end: null,
        last_task_date: '2026-07-14',
        reason: 'Not completed (latest record 2026-07-14); actual start 2026-07-02 and no actual end recorded.',
      },
      {
        well_id: 101,
        task_code: 'FLME1040-101',
        schedule_id: 12,
        activity_code: null,
        description: null,
        wbs: null,
        task_state: 'NOT_STARTED',
        counts_as_incomplete: true,
        counts_as_ongoing: false,
        completed: false,
        actual_start: null,
        actual_end: null,
        last_task_date: '2026-07-10',
        reason: 'Not completed (latest record 2026-07-10); no actual start and no actual end recorded, so it is not counted as ongoing.',
      },
    ],
    proof_note: null,
    ...overrides,
  }
}

function panel() {
  return document.querySelector('.explain')
}

beforeEach(() => {
  api.explain.mockReset()
})

describe('where the text came from', () => {
  it('leaves a freshly generated explanation in the panel s ordinary styling', async () => {
    api.explain.mockResolvedValue(response({ cached: false }))
    render(<ExplainPanel request={REQUEST} onClose={vi.fn()} />)

    await screen.findByText(/incomplete tasks/)
    expect(panel()).not.toHaveClass('explain--cached')
  })

  it('marks a reused explanation green', async () => {
    api.explain.mockResolvedValue(response({ cached: true }))
    render(<ExplainPanel request={{ ...REQUEST, well_id: 102 }} onClose={vi.fn()} />)

    await screen.findByText(/incomplete tasks/)
    expect(panel()).toHaveClass('explain--cached')
  })

  it('carries no tone at all while it is still loading', () => {
    api.explain.mockReturnValue(new Promise(() => {}))
    render(<ExplainPanel request={{ ...REQUEST, well_id: 103 }} onClose={vi.fn()} />)

    expect(panel()).not.toHaveClass('explain--cached')
    expect(screen.getByText(/Generating an explanation/)).toBeInTheDocument()
  })

  it('carries no tone when the explanation is unavailable', async () => {
    api.explain.mockResolvedValue(
      response({ available: false, explanation: null, error: 'provider down', cached: false }),
    )
    render(<ExplainPanel request={{ ...REQUEST, well_id: 104 }} onClose={vi.fn()} />)

    await screen.findByText(/AI explanation unavailable/)
    expect(panel()).not.toHaveClass('explain--cached')
    // The deterministic data is never described as lost along with it.
    expect(screen.getByText(/still available and unchanged/)).toBeInTheDocument()
  })

  it('never invents text when the request itself fails', async () => {
    api.explain.mockRejectedValue(new Error('network down'))
    render(<ExplainPanel request={{ ...REQUEST, well_id: 105 }} onClose={vi.fn()} />)

    await screen.findByText(/AI explanation unavailable/)
    expect(screen.getByText(/network down/)).toBeInTheDocument()
  })
})

describe('how often it asks', () => {
  it('asks once even when development StrictMode mounts it twice', async () => {
    api.explain.mockResolvedValue(response({ cached: false }))
    render(
      <StrictMode>
        <ExplainPanel request={{ ...REQUEST, well_id: 106 }} onClose={vi.fn()} />
      </StrictMode>,
    )

    await screen.findByText(/incomplete tasks/)
    await waitFor(() => expect(api.explain).toHaveBeenCalledTimes(1))
    // ...and what it shows is the answer that was generated for it, not a
    // second request's report that the first one had already been cached.
    expect(panel()).not.toHaveClass('explain--cached')
  })

  it('asks again for a different well', async () => {
    api.explain.mockResolvedValue(response())
    const { rerender } = render(<ExplainPanel request={{ ...REQUEST, well_id: 107 }} onClose={vi.fn()} />)
    await screen.findByText(/incomplete tasks/)

    rerender(<ExplainPanel request={{ ...REQUEST, well_id: 108 }} onClose={vi.fn()} />)
    await waitFor(() => expect(api.explain).toHaveBeenCalledTimes(2))
  })

  it('asks again when the report date changes', async () => {
    api.explain.mockResolvedValue(response())
    const { rerender } = render(
      <ExplainPanel request={{ ...REQUEST, well_id: 109 }} onClose={vi.fn()} />,
    )
    await screen.findByText(/incomplete tasks/)

    rerender(
      <ExplainPanel
        request={{ ...REQUEST, well_id: 109, report_date: '2026-08-02' }}
        onClose={vi.fn()}
      />,
    )
    await waitFor(() => expect(api.explain).toHaveBeenCalledTimes(2))
  })
})

describe('what is sent to the AI model', () => {
  it('shows the structured evidence payload, not a query', async () => {
    api.explain.mockResolvedValue(response())
    render(<ExplainPanel request={{ ...REQUEST, well_id: 110 }} onClose={vi.fn()} />)
    await screen.findByText(/incomplete tasks/)

    await userEvent.click(screen.getByText('What is sent to AI model for summary'))
    const payload = document.querySelector('.explain pre').textContent
    expect(payload).toContain('"task_activity"')
    expect(payload).toContain('"ongoing_task_count": 4')
    expect(payload.toLowerCase()).not.toContain('select ')
  })

  it('says plainly when part of the evidence was not sent to the model', async () => {
    api.explain.mockResolvedValue(
      response({ evidence_withheld_from_model: ['crew_suggestion'] }),
    )
    render(<ExplainPanel request={{ ...REQUEST, well_id: 111 }} onClose={vi.fn()} />)
    await screen.findByText(/incomplete tasks/)

    await userEvent.click(screen.getByText('What is sent to AI model for summary'))
    expect(screen.getByText(/deliberately not sent to the model/)).toHaveTextContent(
      'crew_suggestion',
    )
  })
})

describe('closing', () => {
  it('closes on the panel s own control', async () => {
    api.explain.mockResolvedValue(response())
    const onClose = vi.fn()
    render(<ExplainPanel request={{ ...REQUEST, well_id: 112 }} onClose={onClose} />)
    await screen.findByText(/incomplete tasks/)

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('renders nothing at all without a request', () => {
    render(<ExplainPanel request={null} onClose={vi.fn()} />)
    expect(panel()).toBeNull()
    expect(api.explain).not.toHaveBeenCalled()
  })
})


describe('showing the working', () => {
  it('offers the evidence, the SQL and the proof, all collapsed', async () => {
    api.explain.mockResolvedValue(response())
    render(<ExplainPanel request={{ ...REQUEST, well_id: 200 }} onClose={vi.fn()} />)
    await screen.findByText('What is sent to AI model for summary')

    expect(screen.getByText('What is sent to AI model for summary')).toBeInTheDocument()
    expect(screen.getByText('SQL')).toBeInTheDocument()
    expect(screen.getByText(/Proof — the 2 open tasks behind these counts/)).toBeInTheDocument()
    // Collapsed: the panel is for reading, the working is there when wanted.
    document.querySelectorAll('details').forEach((drawer) => expect(drawer.open).toBe(false))
  })

  it('shows the query with the date as a bound parameter, not spliced in', async () => {
    api.explain.mockResolvedValue(response())
    render(<ExplainPanel request={{ ...REQUEST, well_id: 201 }} onClose={vi.fn()} />)
    await screen.findByText('What is sent to AI model for summary')

    await userEvent.click(screen.getByText('SQL'))
    expect(screen.getByText('backend/sql/well_task_activity.sql')).toBeInTheDocument()
    expect(screen.getByText(/report date = 2026-08-01/)).toBeInTheDocument()
    const sql = [...document.querySelectorAll('.explain__pre')].map((el) => el.textContent).join('')
    expect(sql).toContain('CAST(? AS date)')
  })

  it('proves each count with the task records behind it', async () => {
    api.explain.mockResolvedValue(response())
    render(<ExplainPanel request={{ ...REQUEST, well_id: 202 }} onClose={vi.fn()} />)
    await screen.findByText('What is sent to AI model for summary')

    await userEvent.click(screen.getByText(/Proof —/))
    const table = document.querySelector('.proof-table')
    expect(within(table).getByText('FLME1030-101')).toBeInTheDocument()
    expect(within(table).getByText('Pipe Stringing')).toBeInTheDocument()
    expect(within(table).getByText(/actual start 2026-07-02 and no actual end/)).toBeInTheDocument()
    // ...on its own full-width line, under the row it explains.
    expect(document.querySelectorAll('.proof-table__why')).toHaveLength(2)
    // Which figure each row counts toward is stated per row, and exactly one
    // of the two is ever Yes -- that is what makes them add up.
    const ongoingRow = within(table).getByText('FLME1030-101').closest('tr')
    expect(within(ongoingRow).getAllByText('Yes')).toHaveLength(1)
    expect(within(ongoingRow).getAllByText('No')).toHaveLength(1)
    const notStartedRow = within(table).getByText('FLME1040-101').closest('tr')
    expect(within(notStartedRow).getAllByText('Yes')).toHaveLength(1)
    expect(within(notStartedRow).getAllByText('No')).toHaveLength(1)
  })

  it('says a task is not mapped rather than inventing a description', async () => {
    api.explain.mockResolvedValue(response())
    render(<ExplainPanel request={{ ...REQUEST, well_id: 203 }} onClose={vi.fn()} />)
    await screen.findByText('What is sent to AI model for summary')

    await userEvent.click(screen.getByText(/Proof —/))
    // The last task row -- each one is now followed by its own reason row.
    const rows = [...document.querySelectorAll('.proof-table tbody tr')].filter(
      (row) => !row.classList.contains('proof-table__why'),
    )
    expect(within(rows.at(-1)).getByText('Not mapped')).toBeInTheDocument()
  })

  it('says so when the proof table is only part of the tasks', async () => {
    api.explain.mockResolvedValue(
      response({ proof_note: 'Showing the first 300 of 412 incomplete tasks.' }),
    )
    render(<ExplainPanel request={{ ...REQUEST, well_id: 204 }} onClose={vi.fn()} />)
    await screen.findByText('What is sent to AI model for summary')

    await userEvent.click(screen.getByText(/Proof —/))
    expect(screen.getByText(/Showing the first 300 of 412/)).toBeInTheDocument()
  })

  it('shows no SQL or proof section when the scope has none', async () => {
    api.explain.mockResolvedValue(response({ sql_sources: [], proof: [] }))
    render(<ExplainPanel request={{ ...REQUEST, well_id: 205 }} onClose={vi.fn()} />)
    await screen.findByText('What is sent to AI model for summary')

    expect(screen.queryByText('SQL')).not.toBeInTheDocument()
    expect(screen.queryByText(/Proof —/)).not.toBeInTheDocument()
    expect(screen.getByText('What is sent to AI model for summary')).toBeInTheDocument()
  })
})
