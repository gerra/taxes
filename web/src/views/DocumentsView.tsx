import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { Account, AccountCoverage, AccountType, Checklist, MappingNeeded } from '../types'
import { shortDate } from '../utils/format'

const TYPE_LABELS: Record<AccountType, string> = {
  schwab_individual: 'Schwab — Individual brokerage',
  schwab_awards: 'Schwab — Equity Awards',
  freetrade_gia: 'Freetrade — GIA',
  bank_generic: 'Bank statement (interest)',
  raw_csv: 'Raw CSV (cgt-calc format)',
}

const STATUS: Record<string, { label: string; cls: string }> = {
  ok: { label: 'Complete', cls: 'ok' },
  gaps: { label: 'Gaps', cls: 'warn' },
  missing: { label: 'No documents', cls: 'bad' },
}

export default function DocumentsView({ year }: { year: number }) {
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [error, setError] = useState('')
  const [adding, setAdding] = useState(false)

  const reload = useCallback(() => {
    api
      .get<Checklist>(`/api/checklist/${year}`)
      .then(setChecklist)
      .catch((e) => setError(String(e)))
  }, [year])

  useEffect(reload, [reload])

  if (error) return <div className="error-text">{error}</div>
  if (!checklist) return <div>Loading…</div>

  return (
    <div>
      <div className="page-head">
        <h2>Documents for {checklist.label}</h2>
        <span className="muted">
          covers 6 Apr {checklist.tax_year} – 5 Apr {checklist.tax_year + 1} · file online by{' '}
          {shortDate(checklist.filing_deadline)}
        </span>
      </div>
      <p className="muted">
        Capital gains need your <b>full history</b> (the Section 104 pool replays every purchase),
        not just this tax year — upload export chunks until each account shows Complete.
      </p>
      {checklist.accounts.map((c) => (
        <AccountCard key={c.account.id} coverage={c} onChange={reload} />
      ))}
      {adding ? (
        <AddAccountForm
          onDone={() => {
            setAdding(false)
            reload()
          }}
          onCancel={() => setAdding(false)}
        />
      ) : (
        <button className="btn" onClick={() => setAdding(true)}>
          + Add account
        </button>
      )}
    </div>
  )
}

function AccountCard({ coverage, onChange }: { coverage: AccountCoverage; onChange: () => void }) {
  const { account } = coverage
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [mappingNeeded, setMappingNeeded] = useState<MappingNeeded | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const pendingFile = useRef<File | null>(null)
  const status = STATUS[coverage.status]

  const upload = async (file: File) => {
    setBusy(true)
    setMessage('')
    const form = new FormData()
    form.append('file', file)
    try {
      await api.post(`/api/accounts/${account.id}/documents`, form)
      setMessage(`Uploaded ${file.name}`)
      onChange()
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && (e.body as MappingNeeded)?.needs_mapping) {
        pendingFile.current = file
        setMappingNeeded(e.body as MappingNeeded)
      } else {
        setMessage(String(e))
      }
    } finally {
      setBusy(false)
    }
  }

  const remove = async (docId: number) => {
    if (!confirm('Delete this document?')) return
    await api.del(`/api/documents/${docId}`)
    onChange()
  }

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <b>{account.name}</b>
          {account.name !== TYPE_LABELS[account.type] && (
            <span className="muted"> · {TYPE_LABELS[account.type]}</span>
          )}
        </div>
        <span className={`badge ${status.cls}`}>{status.label}</span>
      </div>

      {coverage.gaps.length > 0 && (
        <div className="gaps">
          {coverage.gaps.map((g, i) => (
            <div key={i} className="gap-row">
              Missing <b>{shortDate(g.start)}</b> → <b>{shortDate(g.end)}</b>
            </div>
          ))}
        </div>
      )}
      {coverage.status !== 'ok' && <p className="muted small">{coverage.instructions}</p>}

      {coverage.documents.length > 0 && (
        <table className="doc-table">
          <tbody>
            {coverage.documents.map((d) => (
              <tr key={d.id}>
                <td>{d.filename}</td>
                <td className="muted">
                  {shortDate(d.date_min)} → {shortDate(d.date_max)}
                </td>
                <td className="muted">{d.tx_count} rows</td>
                <td>
                  {d.warnings.length > 0 && (
                    <span className="badge warn" title={d.warnings.join('\n')}>
                      {d.warnings.length}⚠
                    </span>
                  )}
                </td>
                <td>
                  <button className="link danger" onClick={() => remove(d.id)}>
                    delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="card-actions">
        <input
          ref={fileRef}
          type="file"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) upload(f)
            e.target.value = ''
          }}
        />
        <button className="btn" disabled={busy} onClick={() => fileRef.current?.click()}>
          {busy ? 'Validating…' : 'Upload export'}
        </button>
        {message && <span className="muted small">{message}</span>}
      </div>

      {mappingNeeded && (
        <MappingForm
          accountId={account.id}
          preview={mappingNeeded}
          onDone={() => {
            setMappingNeeded(null)
            const f = pendingFile.current
            pendingFile.current = null
            if (f) upload(f)
          }}
          onCancel={() => setMappingNeeded(null)}
        />
      )}
    </section>
  )
}

function MappingForm({
  accountId,
  preview,
  onDone,
  onCancel,
}: {
  accountId: number
  preview: MappingNeeded
  onDone: () => void
  onCancel: () => void
}) {
  const [dateCol, setDateCol] = useState('')
  const [amountCol, setAmountCol] = useState('')
  const [descCol, setDescCol] = useState('')
  const [filter, setFilter] = useState('interest')

  const save = async () => {
    await api.put(`/api/accounts/${accountId}/mapping`, {
      date_col: dateCol,
      amount_col: amountCol,
      desc_col: descCol || null,
      include_contains: filter || null,
      currency: 'GBP',
    })
    onDone()
  }

  const pick = (value: string, set: (v: string) => void) => (
    <select value={value} onChange={(e) => set(e.target.value)}>
      <option value="">—</option>
      {preview.headers.map((h) => (
        <option key={h} value={h}>
          {h}
        </option>
      ))}
    </select>
  )

  return (
    <div className="mapping-form">
      <h4>Map this bank’s CSV columns</h4>
      <p className="muted small">
        Only rows matching the filter are imported, as interest. Saved once per account.
      </p>
      <div className="mapping-grid">
        <label>Date column {pick(dateCol, setDateCol)}</label>
        <label>Amount column {pick(amountCol, setAmountCol)}</label>
        <label>Description column {pick(descCol, setDescCol)}</label>
        <label>
          Row filter (contains)
          <input value={filter} onChange={(e) => setFilter(e.target.value)} />
        </label>
      </div>
      {preview.sample.length > 0 && (
        <div className="sample-scroll">
          <table>
            <thead>
              <tr>
                {preview.headers.map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.sample.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="card-actions">
        <button className="btn primary" disabled={!dateCol || !amountCol} onClick={save}>
          Save & retry upload
        </button>
        <button className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}

function AddAccountForm({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [type, setType] = useState<AccountType>('schwab_individual')
  const [name, setName] = useState('')
  const [firstActivity, setFirstActivity] = useState('')
  const [error, setError] = useState('')

  const save = async () => {
    try {
      await api.post<Account>('/api/accounts', {
        type,
        name: name || TYPE_LABELS[type],
        first_activity_date: firstActivity || null,
      })
      onDone()
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <section className="card">
      <h3>New account</h3>
      <div className="mapping-grid">
        <label>
          Type
          <select value={type} onChange={(e) => setType(e.target.value as AccountType)}>
            {Object.entries(TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={TYPE_LABELS[type]}
          />
        </label>
        <label>
          First activity (optional)
          <input
            type="date"
            value={firstActivity}
            onChange={(e) => setFirstActivity(e.target.value)}
            title="When this account first traded — sets how far back documents are needed"
          />
        </label>
      </div>
      {error && <p className="error-text">{error}</p>}
      <div className="card-actions">
        <button className="btn primary" onClick={save}>
          Add
        </button>
        <button className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  )
}
