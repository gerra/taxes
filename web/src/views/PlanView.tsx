import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import Section from '../components/Section'
import StepHeader from '../components/StepHeader'
import type { PlannerData, StepKey, Tip, YearParameterGroup, YearStatus } from '../types'
import { currentTaxYear, gbp, pct, shortDate, taxYearLabel } from '../utils/format'

/** What to do about the year, in order of how much it saves.
 *
 *  This is the half of the old Planner that was worth looking at, and it sat
 *  under twenty input fields, a bill card and a parameter table. The inputs
 *  moved to the Income step; what is left is the advice, with the figures it
 *  was derived from behind it. */
export default function PlanView({
  year,
  status,
  onGoTo,
}: {
  year: number
  status: YearStatus | null
  onGoTo: (key: StepKey) => void
}) {
  const [data, setData] = useState<PlannerData | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setData(null)
    api
      .get<PlannerData>(`/api/planner/${year}`)
      .then(setData)
      .catch((e) => setError(String(e)))
  }, [year])

  useEffect(load, [load])

  if (error) return <p className="error-text">{error}</p>

  const running = year === currentTaxYear()
  const tips = data?.tips ?? []
  const totalWin = tips.reduce((sum, t) => sum + (t.estimated_win_gbp ?? 0), 0)

  return (
    <div>
      <StepHeader
        step="plan"
        status={status}
        title={`Plan ${taxYearLabel(year)}`}
        onGoTo={onGoTo}
      />

      {!data && <p className="muted">Loading…</p>}

      {data && (
        <>
          <div className={`banner ${running ? 'info' : 'muted-banner'}`}>
            {running ? (
              <>
                <b>{taxYearLabel(year)} is still running.</b> Everything below is still yours to
                take — allowances unused by 5 April {year + 1} don&rsquo;t carry forward.
              </>
            ) : (
              <>
                <b>{taxYearLabel(year)} has closed.</b> This is the record of what was and
                wasn&rsquo;t used, not a to-do list. Switch the year picker to{' '}
                <b>{taxYearLabel(currentTaxYear())}</b> for what you can still act on.
              </>
            )}
          </div>

          {!data.has_report && (
            <div className="banner warn">
              <b>No calculation for this year yet</b>, so investment figures are treated as zero and
              every tip below is priced too low.{' '}
              <button className="link" onClick={() => onGoTo('report')}>
                Run the report first
              </button>
              .
            </div>
          )}

          <BillStrip data={data} onGoTo={onGoTo} />

          <div className="page-head plan-head">
            <h3>
              {tips.length === 0
                ? 'Tips'
                : `${tips.length} tip${tips.length === 1 ? '' : 's'}${
                    totalWin > 0 ? ` · worth about ${gbp(totalWin, 0)}` : ''
                  }`}
            </h3>
          </div>
          {tips.length === 0 && (
            <p className="muted">
              Nothing actionable found.{' '}
              <button className="link" onClick={() => onGoTo('income')}>
                Add your income figures
              </button>{' '}
              if you haven&rsquo;t — most tips need a marginal rate to be worth anything.
            </p>
          )}
          {tips.map((t) => (
            <TipCard key={t.id} tip={t} />
          ))}

          <ProfileSummary data={data} />
          <YearParameters groups={data.year_parameters} label={data.label} />
        </>
      )}
    </div>
  )
}

/** The bill, as one line with a way through to it.
 *
 *  The bill has one home — the Report — and this page needs only enough of it
 *  to say what the tips are shrinking. Rendering the whole breakdown here as
 *  well is what made the same number look like three different answers. */
function BillStrip({ data, onGoTo }: { data: PlannerData; onGoTo: (key: StepKey) => void }) {
  const sa = data.profile.self_assessment
  return (
    <div className="bill-strip">
      <div>
        <div className="stat-title">
          {sa.reconciled ? `Estimated bill, ${sa.label}` : `Investment income only, ${sa.label}`}
        </div>
        <div className="stat-value">{gbp(sa.reconciled ? sa.sa_bill : sa.investment_only)}</div>
        <div className="muted small">due {shortDate(sa.due_date)}</div>
      </div>
      <div className="bill-strip-note muted small">
        {sa.reconciled ? (
          <>
            Investment income alone is <b>{gbp(sa.investment_only)}</b>; the rest is PAYE catch-up
            on salary.
          </>
        ) : (
          <>
            No P60 entered, so this covers investment income only.{' '}
            <button className="link" onClick={() => onGoTo('income')}>
              Add it
            </button>{' '}
            to see the whole bill.
          </>
        )}
        <br />
        <button className="link" onClick={() => onGoTo('report')}>
          See the full breakdown on the Report
        </button>
      </div>
    </div>
  )
}

function ProfileSummary({ data }: { data: PlannerData }) {
  const p = data.profile
  const y = data.year
  const reliefs = p.income.total - p.income.adjusted_net_income
  const aniTip =
    `Non-savings income (employment + other) ${gbp(p.income.non_savings, 0)}\n` +
    `+ interest ${gbp(p.income.savings, 0)}\n` +
    `+ dividends ${gbp(p.income.dividends, 0)}\n` +
    `= total income ${gbp(p.income.total, 0)}\n` +
    `− gross pension (SIPP) & Gift Aid relief ${gbp(reliefs, 0)}\n` +
    `= adjusted net income ${gbp(p.income.adjusted_net_income, 0)}\n\n` +
    `Investment figures come from this year's report; your P60 pay comes from the Income step.`
  const paTip =
    `Standard allowance ${gbp(y.personal_allowance, 0)}, reduced by £1 for every £2 of adjusted net income above ${gbp(y.pa_taper_start, 0)}.\n` +
    (p.bands.in_pa_taper
      ? `Yours is tapered: ${gbp(p.income.adjusted_net_income, 0)} is ${gbp(p.income.adjusted_net_income - y.pa_taper_start, 0)} over the threshold.`
      : `Yours (${gbp(p.income.adjusted_net_income, 0)}) is below the threshold, so you keep the full allowance.`)
  const taxTip =
    `Income is stacked in HMRC order — non-savings, then interest, then dividends, then gains — and each slice taxed at the band it lands in.\n\n` +
    `Dividends: ${gbp(p.tax.dividend_tax)} after the ${gbp(y.dividend_allowance, 0)} dividend allowance (rates ${pct(y.dividend_rates.basic)} / ${pct(y.dividend_rates.higher)} / ${pct(y.dividend_rates.additional)}).\n` +
    `Interest: ${gbp(p.tax.savings_tax)} after your ${gbp(p.allowances.psa, 0)} personal savings allowance${p.allowances.starting_rate_used > 0 ? ` and ${gbp(p.allowances.starting_rate_used, 0)} starting-rate band` : ''}.\n` +
    `CGT: ${gbp(p.tax.cgt_total)} after the ${gbp(y.cgt_allowance, 0)} annual exempt amount, ` +
    // A year whose rates changed mid-year has a slice at each rate; naming one
    // pair of rates would be wrong for half the disposals.
    (p.cgt.buckets.length > 0
      ? p.cgt.buckets
          .map(
            (b) =>
              `${b.label.toLowerCase()}: ${gbp(b.net)} at ${pct(b.basic_rate)}/${pct(b.higher_rate)}`,
          )
          .join('; ')
      : `${pct(y.cgt_rates_shares.basic)} within the basic band, ${pct(y.cgt_rates_shares.higher)} above`) +
    `.\n` +
    (p.tax.cgt_note ? `${p.tax.cgt_note}\n` : '') +
    `\n` +
    (p.tax.reconciled
      ? `This card is investment income only. Your P60 figures are entered, so the bill adds ${gbp(p.tax.sa_bill - p.tax.investment_only)} of PAYE catch-up on salary to it.`
      : `This card is investment income only, and assumes employment tax was collected correctly via PAYE. Enter your P60 on the Income step to find out whether it was.`)
  const marginalTip =
    `Your taxable income (${gbp(p.bands.taxable_income, 0)}) sits in the ${p.bands.marginal_band} band → ${pct(p.marginal.income_rate)} relief on pension contributions.` +
    (p.bands.in_pa_taper
      ? `\n\nYou're in the ${gbp(y.pa_taper_start, 0)}–${gbp(y.pa_taper_end, 0)} zone where each £2 also restores £1 of personal allowance, so the effective relief is ~60%.`
      : '')
  return (
    <Section
      id="plan-profile"
      title="Where these numbers come from"
      meta="your position, as the tips see it"
      defaultOpen={false}
    >
      <div className="cards-row">
        <div className="stat-card tip-wrap" data-tip={aniTip}>
          <div className="stat-title">Adjusted net income</div>
          <div className="stat-value">{gbp(p.income.adjusted_net_income, 0)}</div>
          <div className="muted small">
            marginal band: {p.bands.marginal_band}
            {p.bands.in_pa_taper && ' · in the 60% zone'}
          </div>
        </div>
        <div className="stat-card tip-wrap" data-tip={paTip}>
          <div className="stat-title">Personal allowance</div>
          <div className="stat-value">{gbp(p.allowances.personal_allowance, 0)}</div>
          <div className="muted small">{p.bands.in_pa_taper ? 'tapered' : 'full allowance'}</div>
        </div>
        <div className="stat-card tip-wrap" data-tip={taxTip}>
          <div className="stat-title">Est. tax on investments</div>
          <div className="stat-value">
            {gbp(p.tax.dividend_tax + p.tax.savings_tax + p.tax.cgt_total)}
          </div>
          <div className="muted small">
            dividends {gbp(p.tax.dividend_tax, 0)} · interest {gbp(p.tax.savings_tax, 0)} · CGT{' '}
            {gbp(p.tax.cgt_total, 0)}
          </div>
        </div>
        <div className="stat-card tip-wrap" data-tip={marginalTip}>
          <div className="stat-title">Marginal relief rate</div>
          <div className="stat-value">{pct(p.marginal.effective_rate)}</div>
          <div className="muted small">what £1 of pension contribution saves</div>
        </div>
        <p className="muted small" style={{ gridColumn: '1 / -1', margin: 0 }}>
          Hover any card to see exactly how it was computed.
        </p>
      </div>
    </Section>
  )
}

/** Every allowance, threshold and rate the year's figures were computed from,
 *  with the gov.uk page each group was checked against.
 *
 *  It is built server-side from the year table itself rather than restated
 *  here, so what this shows is what the bill was actually computed with — the
 *  point of the panel is to make a wrong parameter visible without reading the
 *  source, which is how 2022/23 ran for a year with the wrong additional rate
 *  threshold. */
function YearParameters({ groups, label }: { groups: YearParameterGroup[] | null; label: string }) {
  if (!groups?.length) return null
  return (
    <Section
      id="year-parameters"
      title={`${label} tax year parameters`}
      meta="what these figures were computed with"
      defaultOpen={false}
    >
      <p className="muted small">
        Checked against gov.uk on 27 Aug 2026. Each group links to the page it came from — worth a
        look when a figure in the bill seems off by a band.
      </p>
      <div className="year-params">
        {groups.map((g) => (
          <div key={g.title}>
            <h4>
              {g.title}{' '}
              <a className="small" href={g.source} target="_blank" rel="noreferrer">
                source
              </a>
            </h4>
            <table className="sa-table">
              <tbody>
                {g.rows.map((r) => (
                  <tr key={r.label}>
                    <td>{r.label}</td>
                    <td className="num">
                      {r.kind === 'money' ? gbp(r.value as number, 0) : r.value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </Section>
  )
}

// A benefit that is gone reads red; one still saveable but on a clock reads orange.
const STATUS_BADGE = {
  lost: { cls: 'bad', label: 'benefit lost' },
  expiring: { cls: 'warn', label: 'expiring' },
} as const

function TipCard({ tip }: { tip: Tip }) {
  const [open, setOpen] = useState(false)
  const badge = tip.status ? STATUS_BADGE[tip.status] : null
  return (
    <section
      className={`card tip-card ${tip.status ? `tip-${tip.status}` : ''} ${open ? 'open' : ''}`}
      onClick={() => setOpen(!open)}
    >
      <div className="card-head">
        <b>{tip.title}</b>
        <span className="tip-badges">
          {badge && <span className={`badge ${badge.cls}`}>{badge.label}</span>}
          {tip.estimated_win_gbp != null && (
            <span className="badge ok">save ~{gbp(tip.estimated_win_gbp, 0)}</span>
          )}
        </span>
      </div>
      {tip.status_note && <p className={`tip-status ${tip.status}`}>{tip.status_note}</p>}
      <p>{tip.what_to_do}</p>
      {tip.warnings.length > 0 && (
        <ul className="tip-warnings">
          {tip.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {open && (
        <>
          <p className="muted">{tip.why}</p>
          {tip.how_to_execute.length > 0 && (
            <>
              <p className="tip-steps-head">How to do it</p>
              <ol className="tip-steps">
                {tip.how_to_execute.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </>
          )}
          {tip.detail && <pre className="tip-detail">{tip.detail}</pre>}
          {tip.deadline && <p className="muted small">Deadline: {shortDate(tip.deadline)}</p>}
        </>
      )}
    </section>
  )
}
