import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import type { AccessLists } from '../types'
import AdminView, { fmtWhen } from '../views/AdminView'

const lists: AccessLists = {
  pending: [
    {
      email: 'fedor.irodov@gmail.com',
      name: 'Fedor',
      status: 'pending',
      note: 'It’s me',
      attempts: 2,
      first_seen: '2026-08-25 09:00:00',
      last_seen: '2026-08-26 10:30:00',
      decided_at: null,
    },
  ],
  allowed: [
    {
      email: 'gerralizza@gmail.com',
      name: 'German',
      note: null,
      decided_at: null,
      first_seen: null,
      user_since: '2026-01-01 00:00:00',
      last_login_at: '2026-08-26 08:00:00',
      admin: true,
    },
  ],
  declined: [],
}

function mockFetch() {
  const calls: { url: string; body?: string }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body as string | undefined })
      const body = url === '/api/admin/access' ? lists : { ok: true }
      return { ok: true, status: 200, json: async () => body }
    }),
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

test('fmtWhen treats SQLite timestamps as UTC', () => {
  expect(fmtWhen(null)).toBe('—')
  expect(fmtWhen('2026-08-26 10:30:00')).toMatch(/26 Aug/)
})

test('lists pending requests and approves one', async () => {
  const calls = mockFetch()
  const onPending = vi.fn()
  render(<AdminView onPendingCount={onPending} />)
  await waitFor(() => expect(screen.getByText('fedor.irodov@gmail.com')).toBeInTheDocument())
  expect(onPending).toHaveBeenCalledWith(1)
  expect(screen.getByText('It’s me')).toBeInTheDocument()
  expect(screen.getByText('admin')).toBeInTheDocument()
  // The admin row has no Revoke button.
  expect(screen.queryByRole('button', { name: /revoke/i })).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: /approve/i }))
  await waitFor(() => expect(calls.some((c) => c.url === '/api/admin/access/approve')).toBe(true))
  const approve = calls.find((c) => c.url === '/api/admin/access/approve')!
  expect(JSON.parse(approve.body!)).toEqual({ email: 'fedor.irodov@gmail.com' })
})

test('pre-approve form posts the lower-cased email', async () => {
  const calls = mockFetch()
  render(<AdminView />)
  await waitFor(() => expect(screen.getByText('gerralizza@gmail.com')).toBeInTheDocument())
  const input = screen.getByLabelText(/email to pre-approve/i)
  fireEvent.change(input, { target: { value: ' Friend@Example.com ' } })
  fireEvent.click(screen.getByRole('button', { name: /^allow$/i }))
  await waitFor(() => expect(calls.some((c) => c.url === '/api/admin/access/approve')).toBe(true))
  const approve = calls.find((c) => c.url === '/api/admin/access/approve')!
  expect(JSON.parse(approve.body!)).toEqual({ email: 'friend@example.com' })
})
