import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { useConfirm } from '../components/ConfirmDialog'
import Notices from '../components/Notices'
import type {
  BalanceLedgerRow,
  CalcRun,
  DisposalEvent,
  ErrorTransaction,
  Report,
  TaxDue,
} from '../types'
import { gbp, num, pct, shortDate } from '../utils/format'

const RULE_EXPLAIN: Record<string, string> = {
  SAME_DAY:
    'Same-day rule: shares sold are first matched against shares bought the same day, so those never touch the pool.',
  BED_AND_BREAKFAST:
    '30-day (bed & breakfast) rule: sold shares are matched against purchases made in the following 30 days, at that later cost.',
  SECTION_104:
    'Section 104 pool: everything else is matched against your pooled holding at its average cost.',
  SPIN_OFF: 'Spin-off: cost apportioned from the parent holding.',
}

const EXEMPT_EXPLAIN =
  'Exempt: gilts and UK Treasury bills are outside capital gains tax (TCGA 1992 s115). The matching above is shown for the record; the gain or loss is neither chargeable nor allowable and is left out of every SA108 figure.'

export default function ReportView({ year }: { year: number }) {
  const [report, setReport] = useState<Report | null>(null)
  const [running, setRunning] = useState(false)
  const [calcError, setCalcError] = useState<CalcRun['error'] | null>(null)
  const [noRun, setNoRun] = useState(false)

  const load = useCallback(() => {
    setReport(null)
    setNoRun(false)
    api
      .get<Report>(`/api/report/${year}`)
      .then(setReport)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) setNoRun(true)
      })
  }, [year])

  useEffect(load, [load])

  const run = async (force = false, balanceCheck = true) => {
    setRunning(true)
    setCalcError(null)
    try {
      const result = await api.post<CalcRun>('/api/calc/run', {
        year,
        force,
        balance_check: balanceCheck,
      })
      if (result.status === 'ok') load()
      else setCalcError(result.error ?? { type: 'unknown', message: 'Calculation failed' })
    } catch (e) {
      setCalcError({ type: 'request', message: String(e) })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      <div className="page-head">
        <h2>
          Report {year}/{String((year + 1) % 100).padStart(2, '0')}
        </h2>
        <button className="btn primary" disabled={running} onClick={() => run(true)}>
          {running ? 'Calculating…' : report ? 'Recalculate' : 'Calculate'}
        </button>
        {report?.has_pdf && (
          <a className="btn" href={`/api/calc/runs/${report.run_id}/pdf`}>
            Download computation PDF
          </a>
        )}
      </div>

      {running && (
        <p className="muted">
          Replaying your full transaction history and fetching HMRC exchange rates — can take a
          minute or two on first run.
        </p>
      )}

      {calcError && (
        <CalcErrorCard
          error={calcError}
          onFixed={() => run(true)}
          onWaiveBalanceCheck={() => run(true, false)}
        />
      )}

      {noRun && !running && !calcError && (
        <p className="muted">No calculation yet for this year — hit Calculate.</p>
      )}

      {report && <ReportBody report={report} onChange={load} />}
    </div>
  )
}

function CalcErrorCard({
  error,
  onFixed,
  onWaiveBalanceCheck,
}: {
  error: NonNullable<CalcRun['error']>
  onFixed: () => void
  onWaiveBalanceCheck: () => void
}) {
  const [src, setSrc] = useState('')
  if (error.type === 'negative_balance') {
    return <BalanceErrorCard error={error} onWaive={onWaiveBalanceCheck} />
  }
  if (error.type === 'unknown_spin_off') {
    return (
      <section className="card warn-card">
        <b>Spin-off needs one input:</b> which company did <code>{error.symbol}</code> spin off
        from?
        <div className="card-actions">
          <input
            placeholder="Source ticker, e.g. GE"
            value={src}
            onChange={(e) => setSrc(e.target.value.toUpperCase())}
          />
          <button
            className="btn primary"
            disabled={!src}
            onClick={async () => {
              await api.post('/api/spin-offs', { dst: error.symbol, src })
              onFixed()
            }}
          >
            Save & recalculate
          </button>
        </div>
      </section>
    )
  }
  return (
    <section className="card error-card">
      <b>Calculation failed ({error.type})</b>
      <ErrorMessage text={error.message} />
      {error.transaction && <ErrorTransactionTable tx={error.transaction} />}
    </section>
  )
}

// Engine messages are usually a sentence, but some (parser dumps, tracebacks)
// run to hundreds of lines — those stay folded away until asked for.
const MESSAGE_INLINE_LIMIT = 240

function ErrorMessage({ text }: { text: string }) {
  const [first, ...rest] = text.split('\n')
  if (rest.length === 0 && text.length <= MESSAGE_INLINE_LIMIT) {
    return <p className="error-message">{text}</p>
  }
  return (
    <>
      <p className="error-message">{first.slice(0, MESSAGE_INLINE_LIMIT)}</p>
      <details className="error-details">
        <summary>Show the full engine message</summary>
        <pre>{text}</pre>
      </details>
    </>
  )
}

// The cash-balance check is the engine's only guard against a document set that
// is silently short of rows, so its failure is reported rather than worked
// around; waiving it is a deliberate, single-run choice made here.
function BalanceErrorCard({
  error,
  onWaive,
}: {
  error: NonNullable<CalcRun['error']>
  onWaive: () => void
}) {
  const confirm = useConfirm()
  const ledger = error.ledger ?? []
  const broker = error.broker ?? 'the broker'
  const currency = error.currency ?? 'GBP'

  const waive = async () => {
    const { ok } = await confirm({
      title: 'Recalculate without the cash-balance check?',
      danger: true,
      confirmLabel: 'Run without the check',
      message: (
        <>
          <p>
            The balance check is the one thing that notices a document set missing whole rows. Turn
            it off and a sale or dividend your export never included is simply absent: the report
            still renders, the figures come out too low, and nothing says so.
          </p>
          <p>
            Only do this if you have looked at the ledger and the account is short of{' '}
            <b>deposits or withdrawals</b> — money moving in or out, which affects no figure on your
            return. The run is marked, and the report carries a warning.
          </p>
        </>
      ),
    })
    if (ok) onWaive()
  }

  return (
    <section className="card error-card">
      <b>Cash balance check failed</b>
      <p className="error-message">{error.message}</p>
      <p className="error-hint">
        Most often the export doesn&rsquo;t reach back to the account&rsquo;s first deposit, or the
        broker posts no cash row for something that funded a purchase — a maturing T-bill, a
        transfer in. Gains, dividends and interest don&rsquo;t depend on this balance; they depend
        only on every buy, sell, dividend and interest row being present.
      </p>
      {ledger.length > 0 && (
        <details className="error-details">
          <summary>
            Cash ledger: the last {ledger.filter((r) => !r.note).length} {broker} {currency} rows
          </summary>
          <BalanceLedgerTable rows={ledger} currency={currency} />
        </details>
      )}
      <div className="card-actions">
        <button className="btn primary danger" onClick={waive}>
          Recalculate without the balance check
        </button>
      </div>
    </section>
  )
}

function BalanceLedgerTable({ rows, currency }: { rows: BalanceLedgerRow[]; currency: string }) {
  return (
    <table className="balance-ledger">
      <thead>
        <tr>
          <th>Date</th>
          <th>Transaction</th>
          <th className="right">Amount ({currency})</th>
          <th className="right">Balance</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) =>
          r.note ? (
            <tr key={i} className="ledger-note">
              <td colSpan={4}>{r.note}</td>
            </tr>
          ) : (
            <tr key={i} className={Number(r.balance) < 0 ? 'ledger-negative' : undefined}>
              <td>{shortDate(r.date)}</td>
              <td>
                {r.description || r.symbol || '—'}
                {r.action && <span className="ledger-action">{r.action.toLowerCase()}</span>}
              </td>
              <td className="right">{num(r.amount)}</td>
              <td className="right">{num(r.balance)}</td>
            </tr>
          ),
        )}
      </tbody>
    </table>
  )
}

function ErrorTransactionTable({ tx }: { tx: ErrorTransaction }) {
  const money = (v: string | null, decimals = 2) =>
    v === null ? '—' : `${num(v, decimals)} ${tx.currency}`
  const rows: [string, string][] = [
    ['Date', shortDate(tx.date)],
    ['Action', tx.action],
    ['Symbol', tx.symbol ?? '—'],
    ['ISIN', tx.isin ?? '—'],
    ['Description', tx.description],
    ['Quantity', num(tx.quantity, 8)],
    ['Price', money(tx.price, 6)],
    ['Fees', money(tx.fees)],
    ['Amount', money(tx.amount)],
    ['Broker', tx.broker],
  ]
  return (
    <table className="error-transaction">
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <th>{k}</th>
            <td>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ReportBody({ report, onChange }: { report: Report; onChange: () => void }) {
  const { view, bundle } = report
  return (
    <div>
      {report.provisional && (
        <div className="banner warn">
          Documents are incomplete ({report.coverage_overall}) — these figures are provisional. Fill
          the gaps in the Documents tab.
        </div>
      )}
      <Notices notices={view.notices ?? []} taxYear={view.tax_year} onChange={onChange} />

      <TaxDueCard taxDue={view.tax_due} deadline={view.filing_deadline} />

      <div className="cards-row">
        <StatCard
          title="Taxable capital gain"
          value={gbp(view.cards.taxable_gain.value)}
          sub={view.cards.taxable_gain.sub ?? undefined}
          tax={view.cards.taxable_gain.estimated_tax}
        />
        <StatCard
          title="Taxable dividends"
          value={gbp(view.cards.dividends_taxable.value)}
          sub={view.cards.dividends_taxable.sub}
          tax={view.cards.dividends_taxable.estimated_tax}
        />
        <StatCard
          title="UK interest"
          value={gbp(view.cards.uk_interest.value)}
          tax={view.cards.interest_estimated_tax}
        />
        <StatCard title="Foreign interest" value={gbp(view.cards.foreign_interest.value)} />
        {view.cards.other_income.value > 0 && (
          <StatCard
            title="Other UK income"
            value={gbp(view.cards.other_income.value)}
            sub={`REIT PIDs and share lending — ${gbp(view.cards.other_income.tax_taken_off)} tax already taken off`}
            tax={view.cards.other_income.estimated_tax}
          />
        )}
      </div>
      {view.exempt_disposals && (
        <div className="banner info">
          <b>
            {view.exempt_disposals.count} CGT-exempt disposal
            {view.exempt_disposals.count === 1 ? '' : 's'} (
            {view.exempt_disposals.symbols.join(', ')}
            ): {gbp(view.exempt_disposals.proceeds)} proceeds, {gbp(view.exempt_disposals.gain)}{' '}
            notional gain.
          </b>{' '}
          {view.exempt_disposals.explain}
        </div>
      )}
      {view.rate_change_split && (
        <div className="banner info">
          CGT rates changed on {shortDate(view.rate_change_split.date)}: gains before that date{' '}
          {gbp(view.rate_change_split.before)} (10%/20%), on or after{' '}
          {gbp(view.rate_change_split.after)} (18%/24%). HMRC’s return has an adjustment box for
          this — the computation PDF shows each disposal date.
        </div>
      )}

      <h3>What goes on the return</h3>
      <table className="sa-table">
        <thead>
          <tr>
            <th>Form</th>
            <th>Box</th>
            <th>Figure</th>
            <th className="num">Value</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {view.sa_boxes.map((b) => (
            <SARow key={`${b.form}-${b.box}-${b.label}`} box={b} />
          ))}
        </tbody>
      </table>

      <h3>
        Disposals ({bundle.disposals.filter((d) => !d.exempt).length}
        {bundle.disposals.some((d) => d.exempt) &&
          ` chargeable + ${bundle.disposals.filter((d) => d.exempt).length} exempt`}
        )
      </h3>
      <DisposalsTable disposals={bundle.disposals} />

      {bundle.dividends.length > 0 && (
        <>
          <h3>Dividends</h3>
          <table className="sa-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Symbol</th>
                <th className="num">Gross (GBP)</th>
                <th className="num">Withheld</th>
                <th className="num">Treaty relief</th>
              </tr>
            </thead>
            <tbody>
              {bundle.dividends.map((d, i) => (
                <tr key={i}>
                  <td>{shortDate(d.date)}</td>
                  <td>{d.symbol}</td>
                  <td className="num">{gbp(d.amount_gbp)}</td>
                  <td className="num">{gbp(d.tax_at_source_gbp)}</td>
                  <td className="num">{d.treaty ? gbp(d.treaty.relief_gbp) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {(bundle.other_income?.length ?? 0) > 0 && (
        <>
          <h3>Other UK income</h3>
          <p className="muted small">
            REIT property income distributions (under the REIT’s ticker, with the 20% tax it
            withheld) and share-lending fees (under the broker). Goes in SA100 box 17, tax in box 19
            — not dividends, not interest.
          </p>
          <table className="sa-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Source</th>
                <th className="num">Gross (GBP)</th>
                <th className="num">Tax taken off</th>
              </tr>
            </thead>
            <tbody>
              {bundle.other_income!.map((r, i) => (
                <tr key={i}>
                  <td>{shortDate(r.date)}</td>
                  <td>{r.source}</td>
                  <td className="num">{gbp(r.amount_gbp)}</td>
                  <td className="num">{parseFloat(r.tax_gbp) > 0 ? gbp(r.tax_gbp) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {bundle.interest_by_source.length > 0 && (
        <>
          <h3>Interest by source</h3>
          <table className="sa-table">
            <tbody>
              {bundle.interest_by_source.map((r, i) => (
                <tr key={i}>
                  <td>{r.broker}</td>
                  <td>{r.currency === 'GBP' ? 'UK' : `Foreign (${r.currency})`}</td>
                  <td className="num">{gbp(r.amount_gbp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {bundle.portfolio_eoy.length > 0 && (
        <>
          <h3>Holdings at 5 April</h3>
          <table className="sa-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="num">Quantity</th>
                <th className="num">Pooled cost</th>
              </tr>
            </thead>
            <tbody>
              {bundle.portfolio_eoy.map((p) => (
                <tr key={p.symbol}>
                  <td>{p.symbol}</td>
                  <td className="num">{num(p.quantity, 4)}</td>
                  <td className="num">{gbp(p.pool_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

function TaxDueCard({ taxDue, deadline }: { taxDue: TaxDue | undefined; deadline: string }) {
  if (!taxDue?.available) {
    return (
      <div className="total-card">
        <div>
          <div className="stat-title">Estimated tax to pay</div>
          <div className="stat-value">—</div>
        </div>
        <div className="total-note">
          Enter your income (P60 pay, pension contributions) in the Planner tab — the tax on these
          figures depends on your marginal rate, so it can't be estimated without it.
        </div>
      </div>
    )
  }
  const rates = taxDue.cgt_rates
  const cgtDetail =
    rates && (taxDue.cgt_at_basic ?? 0) > 0 && (taxDue.cgt_at_higher ?? 0) > 0
      ? `${gbp(taxDue.cgt_at_basic, 0)} @ ${pct(rates.basic)} + ${gbp(taxDue.cgt_at_higher, 0)} @ ${pct(rates.higher)}`
      : rates && (taxDue.cgt_at_higher ?? 0) > 0
        ? `@ ${pct(rates.higher)}`
        : rates && (taxDue.cgt_at_basic ?? 0) > 0
          ? `@ ${pct(rates.basic)}`
          : 'within exempt amount'
  return (
    <div className="total-card">
      <div>
        <div className="stat-title">Estimated tax to pay via Self Assessment</div>
        <div className="stat-value">{gbp(taxDue.total)}</div>
      </div>
      <div className="total-breakdown">
        <div>
          Capital gains
          <b>{gbp(taxDue.cgt)}</b>
          {cgtDetail}
        </div>
        <div>
          Dividends
          <b>{gbp(taxDue.dividends)}</b>
          after {gbp(taxDue.dividend_allowance, 0)} allowance
        </div>
        <div>
          Interest
          <b>{gbp(taxDue.interest)}</b>
          after {gbp(taxDue.psa, 0)} savings allowance
        </div>
        {(taxDue.other_income ?? 0) !== 0 && (
          <div>
            Other UK income
            <b>{gbp(taxDue.other_income)}</b>
            at your marginal rate, less tax already withheld
          </div>
        )}
      </div>
      <div className="total-note">
        On these investment figures only, at your {taxDue.marginal_band}-rate position (personal
        allowance {gbp(taxDue.personal_allowance, 0)}). Employment tax is already collected via
        PAYE. If this exceeds £1,000, HMRC will also ask for payments on account towards next year
        (excluding the CGT part). Due {shortDate(deadline)}.
      </div>
    </div>
  )
}

function StatCard({
  title,
  value,
  sub,
  tax,
}: {
  title: string
  value: string
  sub?: string
  tax?: number | null
}) {
  return (
    <div className="stat-card">
      <div className="stat-title">{title}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="muted small">{sub}</div>}
      {tax != null && <div className="stat-tax">≈ {gbp(tax)} tax at your rates</div>}
    </div>
  )
}

function SARow({ box }: { box: Report['view']['sa_boxes'][number] }) {
  const [open, setOpen] = useState(false)
  const display = box.format === 'int' ? String(box.value) : gbp(box.value)
  const copyValue = box.format === 'int' ? String(box.value) : box.value.toFixed(2)
  return (
    <>
      <tr className="sa-row" onClick={() => setOpen(!open)}>
        <td>{box.form}</td>
        <td>{box.box}</td>
        <td>{box.label}</td>
        <td className="num">
          <b>{display}</b>
        </td>
        <td>
          <button
            className="link"
            onClick={(e) => {
              e.stopPropagation()
              navigator.clipboard.writeText(copyValue)
            }}
            title="Copy value"
          >
            copy
          </button>
        </td>
      </tr>
      {open && (
        <tr className="explain-row">
          <td colSpan={5}>{box.explain}</td>
        </tr>
      )}
    </>
  )
}

function DisposalsTable({ disposals }: { disposals: DisposalEvent[] }) {
  const [open, setOpen] = useState<number | null>(null)
  if (disposals.length === 0) return <p className="muted">No disposals this year.</p>
  return (
    <table className="sa-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Symbol</th>
          <th className="num">Proceeds</th>
          <th className="num">Gain / loss</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {disposals.map((d, i) => (
          <DisposalRow
            key={i}
            d={d}
            open={open === i}
            toggle={() => setOpen(open === i ? null : i)}
          />
        ))}
      </tbody>
    </table>
  )
}

function DisposalRow({ d, open, toggle }: { d: DisposalEvent; open: boolean; toggle: () => void }) {
  const gain = parseFloat(d.gain ?? '0')
  return (
    <>
      <tr className={`sa-row${d.exempt ? ' muted' : ''}`} onClick={toggle}>
        <td>{shortDate(d.date)}</td>
        <td>
          {d.symbol}
          {d.exempt && (
            <span className="badge" title={EXEMPT_EXPLAIN}>
              {' '}
              CGT-exempt
            </span>
          )}
        </td>
        <td className="num">{gbp(d.amount)}</td>
        <td className={`num ${d.exempt ? '' : gain >= 0 ? 'gain' : 'loss'}`}>
          {gbp(d.gain)}
          {d.exempt && ' (not chargeable)'}
        </td>
        <td className="muted">{open ? '▾' : '▸'}</td>
      </tr>
      {open && (
        <tr className="explain-row">
          <td colSpan={5}>
            {d.exempt && <div className="entry-line">{EXEMPT_EXPLAIN}</div>}
            {d.entries.map((e, i) => (
              <div key={i} className="entry-line">
                <b>{e.rule.replace(/_/g, ' ')}</b>
                {e.bnb_date && <> (matched purchase on {shortDate(e.bnb_date)})</>}:{' '}
                {num(e.quantity, 4)} units, proceeds {gbp(e.amount)}, allowable cost{' '}
                {gbp(e.allowable_cost)}
                {parseFloat(e.fees ?? '0') > 0 && <>, fees {gbp(e.fees)}</>} → gain {gbp(e.gain)}.
                Pool after: {num(e.new_quantity, 4)} units at {gbp(e.new_pool_cost)}.
                <div className="muted small">{RULE_EXPLAIN[e.rule] ?? ''}</div>
              </div>
            ))}
          </td>
        </tr>
      )}
    </>
  )
}
