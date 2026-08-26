import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import Notices, { Hl } from '../components/Notices'
import type { Notice } from '../types'

const base: Omit<Notice, 'key' | 'kind' | 'category' | 'title'> = {
  summary: 'x',
  occurrences: [],
  why: null,
  action: null,
  count: 1,
  raw: [],
  resolution: null,
  verification: { intro: '', docs: [], fields: [] },
}

test('Hl renders [[tokens]] as highlight pills', () => {
  const { container } = render(<Hl text="Sold [[10 May 2023]], bought [[16 May 2023]]" />)
  const pills = container.querySelectorAll('.hl')
  expect(pills).toHaveLength(2)
  expect(pills[0]).toHaveTextContent('10 May 2023')
  expect(container.textContent).not.toContain('[[')
})

test('Notices summarises counts and colors by kind', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'withholding__META',
      kind: 'warning',
      category: 'withholding',
      title: '[[META]] dividends taxed above the treaty rate',
      occurrences: ['a', 'b'],
      why: 'because',
      action: 'do this',
      count: 2,
      raw: ['raw1', 'raw2'],
    },
    {
      ...base,
      key: 'bed_and_breakfast__META',
      kind: 'info',
      category: 'bed_and_breakfast',
      title: '30-day rule applied to [[META]]',
    },
  ]
  const { container } = render(<Notices notices={notices} />)
  expect(screen.getByText('1 warning · 1 note')).toBeInTheDocument()
  expect(container.querySelector('.notice-warning')).not.toBeNull()
  expect(container.querySelector('.notice-info')).not.toBeNull()
  expect(screen.getByText('×2')).toBeInTheDocument()
})

test('verified notice renders green with graded checks and evidence link', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'amount_adjusted__META__2025-02-25',
      kind: 'warning',
      category: 'amount_adjusted',
      title: 'META sale — tax withheld',
      resolution: {
        note: 'backup withholding',
        data: { withholding: '10966.96', principal: '45695.65', reason: 'backup' },
        evidence_name: 'trade.pdf',
        created_at: '2026-08-26 10:00:00',
        status: 'verified',
        checks: [
          { label: 'Principal matches quantity × price', status: 'ok', detail: '70 × $652.795' },
          { label: 'Withholding explains the missing amount', status: 'ok', detail: 'matches' },
          { label: 'Tax treatment', status: 'info', detail: 'reclaim via 1040-NR' },
        ],
        missing: [],
        verified: true,
        check: 'matches',
      },
    },
  ]
  const { container } = render(<Notices notices={notices} onChange={() => {}} />)
  expect(container.querySelector('.notice-resolved')).not.toBeNull()
  expect(screen.getByText('1 verified')).toBeInTheDocument()
  expect(container.querySelectorAll('.check-ok')).toHaveLength(2)
  expect(container.querySelector('.check-info')).not.toBeNull()
  expect(screen.getByRole('link', { name: /trade\.pdf/ })).toHaveAttribute(
    'href',
    '/api/notices/amount_adjusted__META__2025-02-25/evidence',
  )
})

test('mismatch renders as error with missing answers listed', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'amount_adjusted__X__2025-01-01',
      kind: 'warning',
      category: 'amount_adjusted',
      title: 'X sale',
      resolution: {
        note: '',
        data: { withholding: '100' },
        evidence_name: null,
        created_at: '2026-08-26 10:00:00',
        status: 'mismatch',
        checks: [
          { label: 'Withholding explains the missing amount', status: 'fail', detail: 'off by $9' },
        ],
        missing: ['Principal (gross value on the trade details)'],
        verified: false,
        check: 'off by $9',
      },
    },
  ]
  const { container } = render(<Notices notices={notices} onChange={() => {}} />)
  expect(container.querySelector('.notice-error')).not.toBeNull()
  expect(screen.getByText(/Still needed/)).toHaveTextContent('Principal')
})

test('Notices renders nothing when empty', () => {
  const { container } = render(<Notices notices={[]} />)
  expect(container.innerHTML).toBe('')
})

test('notices from other tax years are hidden until "All years" is chosen', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'amount_adjusted__META__2025-02-25',
      kind: 'warning',
      category: 'amount_adjusted',
      title: 'META sale — tax withheld',
      tax_year: 2024,
    },
    {
      ...base,
      key: 'balance',
      kind: 'warning',
      category: 'balance',
      title: 'Cash balance didn’t reconcile',
      tax_year: null,
    },
  ]
  render(<Notices notices={notices} taxYear={2021} />)
  expect(screen.queryByText('META sale — tax withheld')).toBeNull()
  expect(screen.getByText('Cash balance didn’t reconcile')).toBeInTheDocument()
  expect(screen.getByText('1 warning')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'All years (+1)' }))
  expect(screen.getByText('META sale — tax withheld')).toBeInTheDocument()
  expect(screen.getByText('2024/25')).toBeInTheDocument() // year chip on the foreign card
  expect(screen.getByText('2 warnings')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'This year' }))
  expect(screen.queryByText('META sale — tax withheld')).toBeNull()
})

test('no year switcher when everything belongs to the selected year', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'amount_adjusted__META__2025-02-25',
      kind: 'warning',
      category: 'amount_adjusted',
      title: 'META sale',
      tax_year: 2024,
    },
  ]
  render(<Notices notices={notices} taxYear={2024} />)
  expect(screen.getByText('META sale')).toBeInTheDocument()
  expect(screen.queryByRole('group')).toBeNull()
})

test('only foreign-year notices shows an empty line plus the switcher', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'amount_adjusted__META__2025-02-25',
      kind: 'warning',
      category: 'amount_adjusted',
      title: 'META sale',
      tax_year: 2024,
    },
  ]
  render(<Notices notices={notices} taxYear={2021} />)
  expect(screen.getByText(/Nothing flagged for 2021\/22/)).toBeInTheDocument()
  expect(screen.queryByText('META sale')).toBeNull()
})

test('long occurrence lists collapse to a preview until expanded', () => {
  const items = Array.from({ length: 12 }, (_, i) => `item ${i}`)
  const notices: Notice[] = [
    {
      ...base,
      key: 'exempt_securities',
      kind: 'info',
      category: 'exempt',
      title: 'Gilts and T-bills treated as exempt from capital gains tax',
      occurrences: items,
    },
  ]
  const { container } = render(<Notices notices={notices} />)
  expect(container.querySelectorAll('.notice-occurrences li')).toHaveLength(5)
  expect(screen.queryByText('item 11')).toBeNull()

  fireEvent.click(screen.getByText('Show all 12'))
  expect(container.querySelectorAll('.notice-occurrences li')).toHaveLength(12)
  expect(screen.getByText('item 11')).toBeInTheDocument()

  fireEvent.click(screen.getByText('Show fewer'))
  expect(container.querySelectorAll('.notice-occurrences li')).toHaveLength(5)
})

test('short occurrence lists show in full with no toggle', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'k',
      kind: 'info',
      category: 'exempt',
      title: 'A note',
      occurrences: ['a', 'b', 'c'],
    },
  ]
  const { container } = render(<Notices notices={notices} />)
  expect(container.querySelectorAll('.notice-occurrences li')).toHaveLength(3)
  expect(container.querySelector('.occurrences-more')).toBeNull()
})

test('copy buttons put a plain-text notice on the clipboard', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.assign(navigator, { clipboard: { writeText } })
  const notices: Notice[] = [
    {
      ...base,
      key: 'exempt_securities',
      kind: 'info',
      category: 'exempt',
      title: 'Gilts treated as [[exempt]]',
      summary: 'Left out of the SA108 figures.',
      occurrences: ['[[TN28]] — 1/8% Gilt 2028'],
      action: 'Check your statements.',
      why: 'Gilt-edged securities are exempt assets.',
      tax_year: 2024,
      count: 2,
    },
    {
      ...base,
      key: 'other',
      kind: 'info',
      category: 'x',
      title: 'Second note',
      summary: '',
      tax_year: 2024,
    },
  ]
  render(<Notices notices={notices} taxYear={2024} />)

  fireEvent.click(screen.getAllByText('Copy')[0])
  await screen.findAllByText('Copied')
  expect(writeText).toHaveBeenCalledWith(
    [
      'Gilts treated as exempt (×2) [2024/25]',
      'Left out of the SA108 figures.',
      '- TN28 — 1/8% Gilt 2028',
      '→ Check your statements.',
      'Why: Gilt-edged securities are exempt assets.',
    ].join('\n'),
  )

  fireEvent.click(screen.getByText('Copy all (2)'))
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2))
  expect(writeText.mock.calls[1][0]).toContain('Second note')
  expect(writeText.mock.calls[1][0]).toContain('Gilts treated as exempt')
})
