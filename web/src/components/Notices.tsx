import { useRef, useState } from 'react'
import { api } from '../api'
import type { Notice } from '../types'
import { shortDate } from '../utils/format'

// Renders text with [[value]] tokens as highlighted pills.
export function Hl({ text }: { text: string }) {
  const parts = text.split(/(\[\[.*?\]\])/g)
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith('[[') && p.endsWith(']]') ? (
          <span key={i} className="hl">
            {p.slice(2, -2)}
          </span>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  )
}

type Tone = Notice['kind'] | 'resolved'

const ICONS: Record<Tone, JSX.Element> = {
  info: (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
      <circle cx="10" cy="10" r="9" fill="currentColor" opacity="0.15" />
      <circle cx="10" cy="6.2" r="1.2" fill="currentColor" />
      <rect x="9" y="8.6" width="2" height="6" rx="1" fill="currentColor" />
    </svg>
  ),
  warning: (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
      <path d="M10 2.5 18.5 17H1.5L10 2.5z" fill="currentColor" opacity="0.18" />
      <path
        d="M10 2.5 18.5 17H1.5L10 2.5z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <rect x="9.1" y="7.2" width="1.8" height="5" rx="0.9" fill="currentColor" />
      <circle cx="10" cy="14.2" r="1.1" fill="currentColor" />
    </svg>
  ),
  error: (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
      <circle cx="10" cy="10" r="9" fill="currentColor" opacity="0.15" />
      <path d="M6.5 6.5l7 7M13.5 6.5l-7 7" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  ),
  resolved: (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
      <circle cx="10" cy="10" r="9" fill="currentColor" opacity="0.15" />
      <path
        d="M5.5 10.5l3 3 6-6.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
}

const KIND_LABEL: Record<Notice['kind'], string> = {
  info: 'note',
  warning: 'warning',
  error: 'error',
}

export default function Notices({
  notices,
  onChange,
}: {
  notices: Notice[]
  onChange?: () => void
}) {
  if (notices.length === 0) return null
  const open = notices.filter((n) => !n.resolution)
  const counts = open.reduce<Record<string, number>>((acc, n) => {
    acc[n.kind] = (acc[n.kind] ?? 0) + 1
    return acc
  }, {})
  const parts = (['error', 'warning', 'info'] as const)
    .filter((k) => counts[k])
    .map((k) => `${counts[k]} ${KIND_LABEL[k]}${counts[k] === 1 ? '' : 's'}`)
  const resolvedCount = notices.length - open.length
  if (resolvedCount) parts.push(`${resolvedCount} confirmed`)

  return (
    <section className="notices">
      <div className="notices-head">
        <h3>Things to know</h3>
        <span className="muted small">{parts.join(' · ')}</span>
      </div>
      {notices.map((n) => (
        <NoticeCard key={n.key} notice={n} onChange={onChange} />
      ))}
    </section>
  )
}

function NoticeCard({ notice, onChange }: { notice: Notice; onChange?: () => void }) {
  const [open, setOpen] = useState(false)
  const [resolving, setResolving] = useState(false)
  const res = notice.resolution ?? null
  const tone: Tone = res ? 'resolved' : notice.kind
  const hasMore = Boolean(notice.why || notice.raw.length)

  const remove = async () => {
    if (!confirm('Remove this confirmation and its attached evidence?')) return
    await api.del(`/api/notices/${notice.key}`)
    onChange?.()
  }

  return (
    <div className={`notice notice-${tone}`}>
      <div className="notice-icon">{ICONS[tone]}</div>
      <div className="notice-body">
        <div className="notice-title">
          <Hl text={notice.title} />
          {notice.count > 1 && <span className="notice-count">×{notice.count}</span>}
          {res && <span className="badge ok">Confirmed</span>}
        </div>
        {notice.summary && (
          <div className="notice-summary">
            <Hl text={notice.summary} />
          </div>
        )}
        {notice.occurrences.length > 0 && (
          <ul className="notice-occurrences">
            {notice.occurrences.map((o, i) => (
              <li key={i}>
                <Hl text={o} />
              </li>
            ))}
          </ul>
        )}
        {!res && notice.action && (
          <div className="notice-action">
            <Hl text={notice.action} />
          </div>
        )}

        {res && (
          <div className="notice-resolution">
            {res.check && <div className={`check ${res.verified ? 'ok' : 'bad'}`}>{res.check}</div>}
            {res.note && <div>{res.note}</div>}
            <div className="meta">
              <span>Confirmed {shortDate(res.created_at.slice(0, 10))}</span>
              {res.evidence_name && (
                <a href={`/api/notices/${notice.key}/evidence`} target="_blank" rel="noreferrer">
                  📎 {res.evidence_name}
                </a>
              )}
            </div>
          </div>
        )}

        <div className="notice-actions">
          {!res && notice.kind !== 'info' && !resolving && onChange && (
            <button className="link" onClick={() => setResolving(true)}>
              Confirm with evidence
            </button>
          )}
          {res && onChange && (
            <>
              <button className="link" onClick={() => setResolving(true)}>
                Edit
              </button>
              <button className="link danger" onClick={remove}>
                Remove confirmation
              </button>
            </>
          )}
          {hasMore && (
            <button className="link notice-more" onClick={() => setOpen(!open)}>
              {open ? 'Less' : 'Why this matters'}
            </button>
          )}
        </div>

        {resolving && (
          <ResolveForm
            notice={notice}
            onDone={() => {
              setResolving(false)
              onChange?.()
            }}
            onCancel={() => setResolving(false)}
          />
        )}

        {open && (
          <div className="notice-details">
            {notice.why && <p>{notice.why}</p>}
            {notice.raw.length > 0 && (
              <details>
                <summary>Engine message{notice.raw.length > 1 ? 's' : ''}</summary>
                {notice.raw.map((r, i) => (
                  <pre key={i}>{r}</pre>
                ))}
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function ResolveForm({
  notice,
  onDone,
  onCancel,
}: {
  notice: Notice
  onDone: () => void
  onCancel: () => void
}) {
  const [note, setNote] = useState(notice.resolution?.note ?? '')
  const [withholding, setWithholding] = useState(notice.resolution?.data?.withholding ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const isSellToCover = notice.category === 'amount_adjusted'

  const save = async () => {
    setSaving(true)
    setError('')
    const form = new FormData()
    form.append('note', note)
    if (isSellToCover) form.append('withholding', withholding)
    const file = fileRef.current?.files?.[0]
    if (file) form.append('file', file)
    try {
      await api.put(`/api/notices/${notice.key}`, form)
      onDone()
    } catch (e) {
      setError(String(e))
      setSaving(false)
    }
  }

  return (
    <div className="resolve-form">
      <div className="mapping-grid">
        {isSellToCover && (
          <label>
            Withholding taxes on this trade (from the broker’s trade details)
            <input
              inputMode="decimal"
              placeholder="e.g. 10966.96"
              value={withholding}
              onChange={(e) => setWithholding(e.target.value)}
            />
          </label>
        )}
        <label>
          Evidence (PDF or screenshot, optional)
          <input ref={fileRef} type="file" accept=".pdf,image/*" />
        </label>
      </div>
      <label className="muted small">
        Note
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={
            isSellToCover
              ? 'e.g. RSU vest sell-to-cover — Schwab withheld tax from the proceeds'
              : 'What you checked / why this is fine'
          }
        />
      </label>
      {error && <p className="error-text small">{error}</p>}
      <div className="card-actions">
        <button className="btn primary" disabled={saving} onClick={save}>
          {saving ? 'Saving…' : 'Save confirmation'}
        </button>
        <button className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}
