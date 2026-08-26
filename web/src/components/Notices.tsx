import { useState } from 'react'
import type { Notice } from '../types'

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

const ICONS: Record<Notice['kind'], JSX.Element> = {
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
}

const KIND_LABEL: Record<Notice['kind'], string> = {
  info: 'note',
  warning: 'warning',
  error: 'error',
}

export default function Notices({ notices }: { notices: Notice[] }) {
  if (notices.length === 0) return null
  const counts = notices.reduce<Record<string, number>>((acc, n) => {
    acc[n.kind] = (acc[n.kind] ?? 0) + 1
    return acc
  }, {})
  const summary = (['error', 'warning', 'info'] as const)
    .filter((k) => counts[k])
    .map((k) => `${counts[k]} ${KIND_LABEL[k]}${counts[k] === 1 ? '' : 's'}`)
    .join(' · ')

  return (
    <section className="notices">
      <div className="notices-head">
        <h3>Things to know</h3>
        <span className="muted small">{summary}</span>
      </div>
      {notices.map((n, i) => (
        <NoticeCard key={i} notice={n} />
      ))}
    </section>
  )
}

function NoticeCard({ notice }: { notice: Notice }) {
  const [open, setOpen] = useState(false)
  const hasMore = Boolean(notice.why || notice.action || notice.raw.length)
  return (
    <div className={`notice notice-${notice.kind}`}>
      <div className="notice-icon">{ICONS[notice.kind]}</div>
      <div className="notice-body">
        <div className="notice-title">
          <Hl text={notice.title} />
          {notice.count > 1 && <span className="notice-count">×{notice.count}</span>}
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
        {notice.action && (
          <div className="notice-action">
            <Hl text={notice.action} />
          </div>
        )}
        {hasMore && (
          <button className="link notice-more" onClick={() => setOpen(!open)}>
            {open ? 'Less' : 'Why this matters'}
          </button>
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
