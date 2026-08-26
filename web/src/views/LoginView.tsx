import { useEffect, useState } from 'react'
import { api } from '../api'
import type { AccessStatus } from '../types'

export default function LoginView() {
  // Set when this browser signed in with Google using an email that isn't
  // allowed (yet): the backend leaves a short-lived tx_access cookie behind.
  const [access, setAccess] = useState<AccessStatus | null>(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<AccessStatus | null>('/api/access/me')
      .then((a) => {
        setAccess(a)
        setNote(a?.note ?? '')
      })
      .catch(() => setAccess(null))
  }, [])

  const saveNote = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.put('/api/access/me', { note })
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save your note')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="center-page">
      <div className="login-card">
        <img src="/favicon.svg" alt="" className="logo-mark" />
        <h1>taxes.gerra.sh</h1>
        <p>UK Self Assessment investment figures, explained.</p>

        {access?.status === 'pending' && (
          <div className="access-status" role="status">
            <p className="error-text">
              <strong>{access.email}</strong> isn’t on the allowed list — this is a private
              instance.
            </p>
            <p>
              Your request has been sent to the owner. Once it’s approved, sign in again and you’re
              in.
            </p>
            <label className="access-note">
              Optional: tell the owner who you are
              <textarea
                value={note}
                maxLength={500}
                rows={3}
                placeholder="e.g. It’s Fedor — we talked about this last week"
                onChange={(e) => {
                  setNote(e.target.value)
                  setSaved(false)
                }}
              />
            </label>
            <div className="access-note-actions">
              <button className="btn" disabled={saving || saved} onClick={saveNote}>
                {saved ? 'Note sent' : saving ? 'Sending…' : 'Send note'}
              </button>
            </div>
            {error && <p className="error-text small">{error}</p>}
          </div>
        )}

        {access?.status === 'declined' && (
          <p className="error-text" role="status">
            The request for <strong>{access.email}</strong> was declined. If you think that’s a
            mistake, get in touch with the owner.
          </p>
        )}

        {access?.status === 'approved' && (
          <p className="access-approved" role="status">
            <strong>{access.email}</strong> has been approved — sign in to get started.
          </p>
        )}

        <a className="btn primary" href="/oauth/google/start">
          {access?.status === 'pending' ? 'Try signing in again' : 'Sign in with Google'}
        </a>
      </div>
    </div>
  )
}
