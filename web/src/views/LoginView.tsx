import { useEffect, useState } from 'react'
import { api } from '../api'
import { HeroArt, Icon } from '../components/LandingArt'
import type { AccessStatus } from '../types'

const FEATURES = [
  {
    icon: 'match',
    title: 'Pooling done properly',
    body: 'Same-day matching, the 30-day bed-and-breakfast rule and the Section 104 pool, applied the way HMRC’s manual describes them.',
  },
  {
    icon: 'explain',
    title: 'Every figure explained',
    body: 'Open any number and you get the disposals behind it, the exchange rates used, and the box it belongs in.',
  },
  {
    icon: 'planner',
    title: 'Plan before 5 April',
    body: 'What allowance is still unused, what losses are about to expire, and what a disposal today would cost you.',
  },
  {
    icon: 'lock',
    title: 'Yours only',
    body: 'One instance, one owner, an invite list you control. Every uploaded statement is encrypted at rest.',
  },
] as const

const STEPS = [
  [
    'Upload',
    'Drop in the CSVs your broker already gives you — Schwab, Freetrade, or a plain bank export.',
  ],
  [
    'Reconcile',
    'The report flags what it can’t be sure of: missing reporting income, PIDs typed as dividends, gaps in coverage.',
  ],
  ['File', 'Copy the finished figures straight into the SA100 and SA108 boxes on HMRC’s site.'],
] as const

export default function LoginView() {
  // Set when this browser signed in with Google using an email that isn't
  // allowed (yet): the backend leaves a short-lived tx_access cookie behind.
  const [access, setAccess] = useState<AccessStatus | null>(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The ask-first form, for visitors who haven't signed in with Google at all.
  const [asking, setAsking] = useState(false)
  const [askEmail, setAskEmail] = useState('')
  const [askName, setAskName] = useState('')
  const [askNote, setAskNote] = useState('')
  const [askState, setAskState] = useState<'idle' | 'sending' | 'sent'>('idle')
  const [askError, setAskError] = useState<string | null>(null)

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

  const sendRequest = async (e: React.FormEvent) => {
    e.preventDefault()
    setAskState('sending')
    setAskError(null)
    try {
      await api.post('/api/access/request', {
        email: askEmail.trim(),
        name: askName.trim(),
        note: askNote.trim(),
      })
      setAskState('sent')
    } catch (err) {
      setAskError(err instanceof Error ? err.message : 'Could not send your request')
      setAskState('idle')
    }
  }

  // Anyone who signed in with Google already has a request on file (or a verdict
  // on it), so the status block below covers them — don't offer the form as well.
  const canAsk = !access

  return (
    <div className="landing">
      <div className="landing-glow" aria-hidden="true" />

      <header className="landing-nav">
        <span className="landing-brand">
          <img src="/favicon.svg" alt="" className="logo-mark small" />
          taxes.gerra.sh
        </span>
        <a className="btn" href="/oauth/google/start">
          Sign in
        </a>
      </header>

      <main className="landing-hero">
        <div className="hero-copy">
          <span className="hero-eyebrow">
            <span className="hero-dot" />
            Private instance · UK Self Assessment
          </span>
          <h1>
            Investment tax figures,{' '}
            {/* the break is dropped on narrow screens — see .hero-copy h1 br */}
            <br />
            <em>worked out for you.</em>
          </h1>
          <p className="hero-sub">
            Capital gains, dividends, interest and foreign tax credit relief — computed from your
            own broker statements, box by box, with the workings shown for every single number.
          </p>

          <div className="hero-cta">
            <a className="btn primary big" href="/oauth/google/start">
              {access?.status === 'pending' ? 'Try signing in again' : 'Sign in with Google'}
            </a>
            {canAsk && askState !== 'sent' && !asking && (
              <button className="btn big" type="button" onClick={() => setAsking(true)}>
                Ask for access
              </button>
            )}
          </div>
          <p className="hero-fine">
            Invite only — if you’re not on the list yet, ask and the owner adds your address. No
            sign-in needed to ask.
          </p>

          {access?.status === 'pending' && (
            <div className="access-status card" role="status">
              <p className="error-text">
                <strong>{access.email}</strong> isn’t on the allowed list yet.
              </p>
              <p>
                Your request has been sent to the owner. Once it’s approved, sign in again and
                you’re in.
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
            <p className="access-status card error-text" role="status">
              The request for <strong>{access.email}</strong> was declined. If you think that’s a
              mistake, get in touch with the owner.
            </p>
          )}

          {access?.status === 'approved' && (
            <p className="access-status card access-approved" role="status">
              <strong>{access.email}</strong> has been approved — sign in to get started.
            </p>
          )}

          {canAsk && askState === 'sent' && (
            <p className="access-status card access-approved" role="status">
              Request sent. The owner will see <strong>{askEmail.trim()}</strong> in their access
              list — once it’s approved, sign in with Google above.
            </p>
          )}

          {canAsk && askState !== 'sent' && asking && (
            <form className="access-ask card" onSubmit={sendRequest}>
              <p className="muted small">
                Leave your Google address and the owner can add it to the allowed list — then you
                sign in as usual.
              </p>
              <label className="access-note">
                Your Google email
                <input
                  type="email"
                  required
                  maxLength={254}
                  autoFocus
                  value={askEmail}
                  placeholder="you@gmail.com"
                  onChange={(e) => setAskEmail(e.target.value)}
                />
              </label>
              <label className="access-note">
                Your name (optional)
                <input
                  type="text"
                  maxLength={100}
                  value={askName}
                  onChange={(e) => setAskName(e.target.value)}
                />
              </label>
              <label className="access-note">
                Anything the owner should know (optional)
                <textarea
                  rows={3}
                  maxLength={500}
                  value={askNote}
                  placeholder="e.g. It’s Fedor — we talked about this last week"
                  onChange={(e) => setAskNote(e.target.value)}
                />
              </label>
              {askError && <p className="error-text small">{askError}</p>}
              <div className="access-note-actions">
                <button className="link" type="button" onClick={() => setAsking(false)}>
                  Cancel
                </button>
                <button
                  className="btn"
                  type="submit"
                  disabled={askState === 'sending' || !askEmail.trim()}
                >
                  {askState === 'sending' ? 'Sending…' : 'Send request'}
                </button>
              </div>
            </form>
          )}
        </div>

        <div className="hero-art">
          <HeroArt />
        </div>
      </main>

      <section className="landing-steps">
        {STEPS.map(([title, body], i) => (
          <div className="step" key={title}>
            <span className="step-no">{String(i + 1).padStart(2, '0')}</span>
            <h3>{title}</h3>
            <p>{body}</p>
          </div>
        ))}
      </section>

      <section className="landing-feats">
        {FEATURES.map((f) => (
          <div className="feat card" key={f.title}>
            <span className="feat-badge">
              <Icon name={f.icon} />
            </span>
            <h3>{f.title}</h3>
            <p>{f.body}</p>
          </div>
        ))}
      </section>

      <footer className="landing-foot">
        <span>
          Built for one household’s tax return. The figures are yours to check — this isn’t tax
          advice.
        </span>
        <span className="muted">taxes.gerra.sh</span>
      </footer>
    </div>
  )
}
