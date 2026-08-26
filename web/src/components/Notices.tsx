import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useConfirm } from './ConfirmDialog'
import type { Notice, VerificationCheck } from '../types'
import { shortDate, taxYearLabel } from '../utils/format'

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

const CHECK_GLYPH: Record<VerificationCheck['status'], string> = {
  ok: '✓',
  fail: '✗',
  warn: '!',
  info: 'i',
  pending: '…',
}

function toneFor(notice: Notice): Tone {
  const status = notice.resolution?.status
  if (status === 'verified') return 'resolved'
  if (status === 'mismatch') return 'error'
  return notice.kind
}

const plain = (text: string) => text.replace(/\[\[(.*?)\]\]/g, '$1')

// One notice as plain text, for pasting into an email to an accountant.
export function noticeText(notice: Notice): string {
  const head = [plain(notice.title)]
  if (notice.count > 1) head.push(`(×${notice.count})`)
  if (notice.tax_year != null) head.push(`[${taxYearLabel(notice.tax_year)}]`)
  const lines = [head.join(' ')]
  if (notice.summary) lines.push(plain(notice.summary))
  for (const o of notice.occurrences) lines.push(`- ${plain(o)}`)
  if (notice.action) lines.push(`→ ${plain(notice.action)}`)
  if (notice.why) lines.push(`Why: ${notice.why}`)
  return lines.join('\n')
}

function CopyButton({
  text,
  label = 'Copy',
  className = 'link',
}: {
  text: () => string
  label?: string
  className?: string
}) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => () => clearTimeout(timer.current), [])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text())
    } catch {
      return // no clipboard permission — say nothing rather than claim success
    }
    setCopied(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setCopied(false), 1600)
  }

  return (
    <button type="button" className={className} onClick={copy}>
      {copied ? 'Copied' : label}
    </button>
  )
}

type Scope = 'year' | 'all'

// The engine replays every year's transactions on each run, so dated notices
// arrive for all years. Show the selected year's by default; "All years" is
// one click away and labels each foreign-year card.
export default function Notices({
  notices,
  taxYear,
  onChange,
}: {
  notices: Notice[]
  taxYear?: number
  onChange?: () => void
}) {
  const [scope, setScope] = useState<Scope>('year')
  if (notices.length === 0) return null

  const otherYear = (n: Notice) =>
    taxYear !== undefined && n.tax_year != null && n.tax_year !== taxYear
  const hidden = notices.filter(otherYear).length
  const shown = scope === 'all' ? notices : notices.filter((n) => !otherYear(n))

  const verified = shown.filter((n) => n.resolution?.status === 'verified')
  const open = shown.filter((n) => n.resolution?.status !== 'verified')
  const counts = open.reduce<Record<string, number>>((acc, n) => {
    acc[n.kind] = (acc[n.kind] ?? 0) + 1
    return acc
  }, {})
  const parts = (['error', 'warning', 'info'] as const)
    .filter((k) => counts[k])
    .map((k) => `${counts[k]} ${KIND_LABEL[k]}${counts[k] === 1 ? '' : 's'}`)
  if (verified.length) parts.push(`${verified.length} verified`)

  return (
    <section className="notices">
      <div className="notices-head">
        <h3>Things to know</h3>
        <span className="muted small">{parts.join(' · ')}</span>
        <div className="notices-head-right">
          {hidden > 0 && (
            <div className="seg" role="group" aria-label="Which tax years to show">
              <button
                type="button"
                className={scope === 'year' ? 'active' : ''}
                aria-pressed={scope === 'year'}
                onClick={() => setScope('year')}
              >
                This year
              </button>
              <button
                type="button"
                className={scope === 'all' ? 'active' : ''}
                aria-pressed={scope === 'all'}
                onClick={() => setScope('all')}
              >
                All years (+{hidden})
              </button>
            </div>
          )}
          {shown.length > 0 && (
            <CopyButton
              className="link copy-all"
              label={`Copy all (${shown.length})`}
              text={() => shown.map(noticeText).join('\n\n')}
            />
          )}
        </div>
      </div>
      {shown.length === 0 && taxYear !== undefined && (
        <p className="muted small notices-empty">
          Nothing flagged for {taxYearLabel(taxYear)} — {hidden} notice{hidden === 1 ? '' : 's'}{' '}
          from other years.
        </p>
      )}
      {shown.map((n) => (
        <NoticeCard key={n.key} notice={n} onChange={onChange} otherYear={otherYear(n)} />
      ))}
    </section>
  )
}

function NoticeCard({
  notice,
  onChange,
  otherYear = false,
}: {
  notice: Notice
  onChange?: () => void
  otherYear?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const confirmDialog = useConfirm()
  const res = notice.resolution ?? null
  const tone = toneFor(notice)
  const hasMore = Boolean(notice.why || notice.raw.length)
  const canVerify = Boolean(onChange) && notice.kind !== 'info'

  const remove = async () => {
    const { ok } = await confirmDialog({
      title: 'Remove this verification?',
      message:
        'Your answers and the attached evidence will be deleted; the notice goes back to unverified.',
      confirmLabel: 'Remove',
      danger: true,
    })
    if (!ok) return
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
          {otherYear && notice.tax_year != null && (
            <span className="badge year" title="From a different tax year">
              {taxYearLabel(notice.tax_year)}
            </span>
          )}
          {res?.status === 'verified' && <span className="badge ok">Verified</span>}
          {res?.status === 'mismatch' && <span className="badge bad">Doesn’t add up</span>}
          {res?.status === 'partial' && <span className="badge warn">Partially checked</span>}
        </div>
        {notice.summary && (
          <div className="notice-summary">
            <Hl text={notice.summary} />
          </div>
        )}
        {notice.occurrences.length > 0 && <Occurrences items={notice.occurrences} />}
        {!res && notice.action && (
          <div className="notice-action">
            <Hl text={notice.action} />
          </div>
        )}

        {res && !editing && (
          <div className="notice-resolution">
            <ul className="checks">
              {res.checks.map((c, i) => (
                <li key={i} className={`check-${c.status}`}>
                  <span className="check-glyph">{CHECK_GLYPH[c.status]}</span>
                  <span>
                    <b>{c.label}</b>
                    {c.detail && <> — {c.detail}</>}
                    {c.status === 'pending' && <> — not answered yet</>}
                  </span>
                </li>
              ))}
            </ul>
            {res.missing.length > 0 && (
              <div className="muted small">Still needed: {res.missing.join(', ')}</div>
            )}
            {res.note && <div className="resolution-note">{res.note}</div>}
            <div className="meta">
              <span>Checked {shortDate(res.created_at.slice(0, 10))}</span>
              {res.evidence_name ? (
                <a href={`/api/notices/${notice.key}/evidence`} target="_blank" rel="noreferrer">
                  📎 {res.evidence_name}
                </a>
              ) : (
                <span>no evidence attached</span>
              )}
            </div>
          </div>
        )}

        <div className="notice-actions">
          {canVerify && !editing && (
            <button className={`link ${res ? '' : 'primary'}`} onClick={() => setEditing(true)}>
              {res ? 'Edit answers' : 'Verify this'}
            </button>
          )}
          {res && !editing && onChange && (
            <button className="link danger" onClick={remove}>
              Remove verification
            </button>
          )}
          {hasMore && (
            <button className="link notice-more" onClick={() => setOpen(!open)}>
              {open ? 'Less' : 'Why this matters'}
            </button>
          )}
          <CopyButton className="link notice-copy" text={() => noticeText(notice)} />
        </div>

        {editing && (
          <VerifyForm
            notice={notice}
            onDone={() => {
              setEditing(false)
              onChange?.()
            }}
            onCancel={() => setEditing(false)}
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

// Long lists (every exempt gilt, every missing price) bury the rest of the card,
// so only the first few show until asked for.
const OCCURRENCE_PREVIEW = 5

function Occurrences({ items }: { items: string[] }) {
  const [expanded, setExpanded] = useState(false)
  const overflow = items.length - OCCURRENCE_PREVIEW
  const shown = expanded || overflow <= 0 ? items : items.slice(0, OCCURRENCE_PREVIEW)

  return (
    <>
      <ul className="notice-occurrences">
        {shown.map((o, i) => (
          <li key={i}>
            <Hl text={o} />
          </li>
        ))}
      </ul>
      {overflow > 0 && (
        <button
          className="link occurrences-more"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? 'Show fewer' : `Show all ${items.length}`}
        </button>
      )}
    </>
  )
}

function VerifyForm({
  notice,
  onDone,
  onCancel,
}: {
  notice: Notice
  onDone: () => void
  onCancel: () => void
}) {
  const spec = notice.verification ?? { intro: '', docs: [], fields: [] }
  const [values, setValues] = useState<Record<string, string>>({
    ...(notice.resolution?.data ?? {}),
  })
  const [note, setNote] = useState(notice.resolution?.note ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const set = (key: string, value: string) => setValues({ ...values, [key]: value })

  const save = async () => {
    setSaving(true)
    setError('')
    const form = new FormData()
    form.append('note', note)
    for (const [k, v] of Object.entries(values)) if (v !== '') form.append(k, v)
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
      {spec.intro && <p className="verify-intro">{spec.intro}</p>}

      {spec.docs.length > 0 && (
        <div className="verify-docs">
          <div className="verify-heading">What to get</div>
          <ol>
            {spec.docs.map((d, i) => (
              <li key={i}>
                <b>{d.title}</b>
                <span className="muted"> — {d.where}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {spec.fields.length > 0 && (
        <>
          <div className="verify-heading">What it says</div>
          <div className="mapping-grid">
            {spec.fields.map((f) =>
              f.type === 'checkbox' ? (
                <label key={f.key} className="verify-checkbox">
                  <input
                    type="checkbox"
                    checked={values[f.key] === 'true'}
                    onChange={(e) => set(f.key, e.target.checked ? 'true' : 'false')}
                  />
                  {f.label}
                </label>
              ) : (
                <label key={f.key}>
                  <span className="label-text">
                    {f.label}
                    {f.required && <span className="req">*</span>}
                  </span>
                  {f.type === 'choice' ? (
                    <select
                      value={values[f.key] ?? ''}
                      onChange={(e) => set(f.key, e.target.value)}
                    >
                      <option value="">—</option>
                      {(f.options ?? []).map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={f.type === 'date' ? 'date' : 'text'}
                      inputMode={f.type === 'money' ? 'decimal' : undefined}
                      placeholder={f.type === 'money' ? '0.00' : undefined}
                      value={values[f.key] ?? ''}
                      onChange={(e) => set(f.key, e.target.value)}
                    />
                  )}
                </label>
              ),
            )}
          </div>
        </>
      )}

      <div className="mapping-grid">
        <label>
          Evidence (PDF or screenshot)
          <input ref={fileRef} type="file" accept=".pdf,image/*" />
        </label>
        <label>
          Note
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Anything else you checked"
          />
        </label>
      </div>
      {error && <p className="error-text small">{error}</p>}
      <div className="card-actions">
        <button className="btn primary" disabled={saving} onClick={save}>
          {saving ? 'Checking…' : 'Save & check'}
        </button>
        <button className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}
