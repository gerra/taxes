import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import LoginView from '../views/LoginView'

function mockFetch(body: unknown) {
  const fn = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => body,
  }))
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => vi.unstubAllGlobals())

test('renders Google sign-in link', async () => {
  mockFetch(null)
  render(<LoginView />)
  const link = screen.getByRole('link', { name: /sign in with google/i })
  expect(link).toHaveAttribute('href', '/oauth/google/start')
  await act(async () => {})
  expect(screen.queryByRole('status')).toBeNull()
})

test('shows pending request with a note box after a rejected sign-in', async () => {
  const fetch = mockFetch({
    email: 'fedor.irodov@gmail.com',
    name: 'Fedor',
    status: 'pending',
    note: '',
  })
  render(<LoginView />)
  await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
  expect(screen.getByRole('status')).toHaveTextContent('fedor.irodov@gmail.com')
  expect(screen.getByRole('status')).toHaveTextContent(/sent to the owner/i)
  expect(screen.getByRole('textbox')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /try signing in again/i })).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledWith('/api/access/me', expect.anything())
})

test('shows declined state without a note box', async () => {
  mockFetch({ email: 'x@y.z', name: '', status: 'declined', note: '' })
  render(<LoginView />)
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/declined/i))
  expect(screen.queryByRole('textbox')).toBeNull()
})
