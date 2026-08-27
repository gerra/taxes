import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useConfirm } from '../components/ConfirmDialog'
import type { AccessLists } from '../types'

// SQLite's datetime('now') is UTC without a zone marker.
export function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso.length === 10 ? iso + 'T00:00:00Z' : iso.replace(' ', 'T') + 'Z')
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

interface Props {
  // Lets the top bar keep its pending-requests badge in sync.
  onPendingCount?: (n: number) => void
}

export default function AdminView({ onPendingCount }: Props) {
  const confirm = useConfirm()
  const [data, setData] = useState<AccessLists | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null) // email being acted on
  const [newEmail, setNewEmail] = useState('')

  const load = useCallback(async () => {
    try {
      const d = await api.get<AccessLists>('/api/admin/access')
      setData(d)
      setError(null)
      onPendingCount?.(d.pending.length)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [onPendingCount])

  useEffect(() => {
    load()
  }, [load])

  const act = async (action: 'approve' | 'decline' | 'forget', email: string) => {
    setBusy(email)
    setError(null)
    try {
      await api.post(`/api/admin/access/${action}`, { email })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusy(null)
    }
  }

  const revoke = async (email: string) => {
    const { ok } = await confirm({
      title: `Revoke access for ${email}?`,
      message:
        'They’ll be signed out immediately and can’t sign in again until you re-approve them. Their uploaded documents are kept.',
      confirmLabel: 'Revoke',
      danger: true,
    })
    if (ok) await act('decline', email)
  }

  const decline = async (email: string) => {
    const { ok } = await confirm({
      title: `Decline ${email}?`,
      message:
        'They’ll see that the request was declined next time they try. You can approve them later from the Declined list.',
      confirmLabel: 'Decline',
      danger: true,
    })
    if (ok) await act('decline', email)
  }

  const addEmail = async (e: React.FormEvent) => {
    e.preventDefault()
    const email = newEmail.trim().toLowerCase()
    if (!email) return
    await act('approve', email)
    setNewEmail('')
  }

  if (!data) {
    return <p className="muted">{error ?? 'Loading…'}</p>
  }

  const atLimit = !!data.pending_limit && data.pending.length >= data.pending_limit

  return (
    <div className="admin">
      <div className="page-head">
        <h2>Access</h2>
        <span className="muted">Who can sign in to this instance.</span>
      </div>
      {error && <p className="error-text">{error}</p>}

      <section className="card">
        <div className="card-head">
          <h3>Pending requests</h3>
          {data.pending.length > 0 && <span className="badge warn">{data.pending.length}</span>}
        </div>
        {atLimit && (
          <p className="error-text small">
            {data.pending.length} of {data.pending_limit} — the login page is turning new requests
            away until you clear some of these.
          </p>
        )}
        {data.pending.length === 0 ? (
          <p className="muted small">
            Nobody is waiting. People show up here when they ask for access from the login page, or
            when they sign in with Google and aren’t allowed.
          </p>
        ) : (
          <table className="sa-table admin-table">
            <thead>
              <tr>
                <th>Who</th>
                <th>Message</th>
                <th>When</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.pending.map((r) => (
                <tr key={r.email}>
                  <td>
                    <div className="admin-email">{r.email}</div>
                    {r.name && <div className="muted small">{r.name}</div>}
                  </td>
                  <td className="admin-note">{r.note || <span className="muted">—</span>}</td>
                  <td className="small">
                    {r.attempts === 0 ? (
                      <>asked {fmtWhen(r.last_seen)}</>
                    ) : (
                      <>
                        {r.attempts}× · last {fmtWhen(r.last_seen)}
                      </>
                    )}
                    {r.attempts > 1 && <div className="muted">first {fmtWhen(r.first_seen)}</div>}
                  </td>
                  <td className="admin-actions">
                    <button
                      className="btn primary small"
                      disabled={busy === r.email}
                      onClick={() => act('approve', r.email)}
                    >
                      Approve
                    </button>
                    <button
                      className="link danger"
                      disabled={busy === r.email}
                      onClick={() => decline(r.email)}
                    >
                      Decline
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <div className="card-head">
          <h3>Allowed</h3>
          <span className="badge ok">{data.allowed.length}</span>
        </div>
        <table className="sa-table admin-table">
          <thead>
            <tr>
              <th>Who</th>
              <th>Last sign-in</th>
              <th>Approved</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.allowed.map((r) => (
              <tr key={r.email}>
                <td>
                  <div className="admin-email">
                    {r.email}
                    {r.admin && <span className="badge year">admin</span>}
                  </div>
                  {r.name && <div className="muted small">{r.name}</div>}
                  {r.note && <div className="admin-note small">“{r.note}”</div>}
                </td>
                <td className="small">
                  {r.last_login_at ? (
                    fmtWhen(r.last_login_at)
                  ) : (
                    <span className="muted">never</span>
                  )}
                </td>
                <td className="small">
                  {r.decided_at ? fmtWhen(r.decided_at) : <span className="muted">—</span>}
                </td>
                <td className="admin-actions">
                  {!r.admin && (
                    <button
                      className="link danger"
                      disabled={busy === r.email}
                      onClick={() => revoke(r.email)}
                    >
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <form className="admin-add" onSubmit={addEmail}>
          <input
            type="email"
            placeholder="Pre-approve an email…"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            aria-label="Email to pre-approve"
          />
          <button className="btn" type="submit" disabled={!newEmail.trim() || busy !== null}>
            Allow
          </button>
        </form>
      </section>

      {data.declined.length > 0 && (
        <section className="card">
          <div className="card-head">
            <h3>Declined</h3>
            <span className="badge bad">{data.declined.length}</span>
          </div>
          <table className="sa-table admin-table">
            <thead>
              <tr>
                <th>Who</th>
                <th>Message</th>
                <th>Declined</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.declined.map((r) => (
                <tr key={r.email}>
                  <td>
                    <div className="admin-email">{r.email}</div>
                    {r.name && <div className="muted small">{r.name}</div>}
                  </td>
                  <td className="admin-note">{r.note || <span className="muted">—</span>}</td>
                  <td className="small">
                    {fmtWhen(r.decided_at)}
                    {r.attempts > 0 && (
                      <div className="muted">
                        {r.attempts}× tried · last {fmtWhen(r.last_seen)}
                      </div>
                    )}
                  </td>
                  <td className="admin-actions">
                    <button
                      className="link primary"
                      disabled={busy === r.email}
                      onClick={() => act('approve', r.email)}
                    >
                      Approve
                    </button>
                    <button
                      className="link"
                      disabled={busy === r.email}
                      onClick={() => act('forget', r.email)}
                    >
                      Forget
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
