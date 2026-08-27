# taxes

Private web app at **taxes.gerra.sh** for working out what a UK Self Assessment
return will actually cost: the investment figures (capital gains, dividends, interest)
from broker documents, **plus whatever PAYE under- or over-collected on salary**, with
explanations for every number and a planner that suggests concrete tax wins.

Built on a fork of [KapJI/capital-gains-calculator](https://github.com/KapJI/capital-gains-calculator)
(`cgt-calc`), following the fintrack/www deployment playbook (Hetzner + nginx + systemd +
GitHub Actions).

## Status

v1 live at https://taxes.gerra.sh. Open items: [TODO.md](TODO.md).

## The headline is the whole bill, not just the investments

The tool used to answer "what do my investments cost me", show that as
**Estimated tax to pay via Self Assessment**, and state that employment tax was
already collected via PAYE. For a PAYE employee that assumption is the thing
most likely to be wrong, and when it is wrong it is usually the larger half of
the bill.

The worked example is 2023/24. The P60 showed £220,031.43 of pay, £84,533.40 of
tax deducted, and final tax code **151T** — a code granting about £1,519 of
personal allowance. At £220k the allowance is nil (it tapers £1 for every £2
over £100,000 and runs out at £125,140), so PAYE taxed £218,512 instead of
£220,031 and under-collected **£683.55**. The tool showed £40.40 for the year.
The real bill was £621.45.

So the headline is now **Estimated Self Assessment bill for [year]**, built as:

```
  income tax on ALL income (employment + benefits + interest + dividends)
− tax deducted at source (every P60, plus tax withheld on other income)
− foreign tax credit relief
= income tax shortfall            (negative = refund)
+ capital gains tax
− anything already paid to HMRC for the year
= Self Assessment bill
```

**Investment income alone** is kept as a second line — it is the old headline,
and the difference between the two is PAYE catch-up. With no P60 entered the
headline falls back to that sub-total and says what it is leaving out, rather
than quietly presenting a partial figure as the bill.

Two other things changed with it:

- **The payments-on-account test** now uses the real balancing payment (the
  income tax shortfall after everything collected at source, capital gains tax
  and student loan excluded) rather than the tax on interest, and computes the
  80%-collected-at-source share from the actual liability. Without a P60 it
  assumes PAYE collected the right tax — and labels the assumption.
- **The additional-rate threshold** is applied to taxable income at £125,140,
  not to the standard allowance plus the higher-rate band. The two only agree
  while the personal allowance is intact; on a £220k salary the old form moved
  £12,570 from 40% to 45% and overstated the tax by about £628.

## New inputs (Planner → Employment & PAYE)

All optional. Skip the section and you get today's behaviour with a visible
caveat; fill in the first two and the reconciliation runs.

| Input | Why it matters |
|---|---|
| **Total pay for the year (P60)** | The income the bill is computed on. Required. |
| **Total tax deducted (P60)** | What PAYE actually collected. Required. Taken from the P60 and *never* derived from the tax code — the gap between the two is the whole point. |
| Final tax code (P60) | Diagnostic only. Decoded as number × 10 + 9 (151T → £1,519; K codes negative; BR/D0/D1 flat), then PAYE is re-run with it. If it reproduces the P60, the shortfall is fully explained by the code and the tool says so; if not, it lists the likely causes. Also the only cross-check on a mistyped "tax deducted". |
| Benefits in kind (P11D) | Taxable, and often only partly collected through the code, so usually adds to the shortfall. |
| Other PAYE employments | Repeat the pay/tax pair. Summed; with more than one, no single code can be re-run against a single P60 and the tool says why. |
| Student loan / postgraduate plan | 9% (6% postgraduate) of income over the plan's threshold. Unearned income over £2,000 counts *in full*, not just the excess. Never part of a payment on account. |
| Self-employment / other untaxed income | Not taxed here — asked so the estimate can warn that it is incomplete rather than silently omitting it. |
| Payments on account already made | Comes off the bill. |
| Tax already paid on gains | Only for tax actually paid through HMRC's real-time CGT service. Warns on any non-zero value, because the taxable gain gets typed into this box and HMRC credits it as tax. |
| Losses as you'll enter them | Optional check: HMRC rounds losses **up**, and entering the rounded-down figure gives away relief. |
| What HMRC actually charged | Not used in any calculation — drives the History tab. |
| Rounding | HMRC rounding (each income source down, losses up) is the default, because matching the real bill is the point. Pence-precise is available as a secondary figure and says it is not what will be charged. |

## History

A **History** tab compares, per year, the estimated bill against what HMRC
actually charged, with the PAYE shortfall broken out. A gap means either the
return went in on different figures or this tool has something wrong; both are
worth knowing. The "actually charged" figure has to be typed in — HMRC exposes
no way to read it, and deriving it from the tool's own estimate would make the
comparison circular.

## Scope

England, Northern Ireland and Wales. **Scottish income tax is not modelled** —
it has five bands of its own, and a Scottish taxpayer's non-savings income would
be charged wrongly here. Scottish tax codes (`S` prefix) are recognised and
refused rather than mis-computed. Class 1/2/4 National Insurance is out of scope.

## Plan

The high-level plan lives in [docs/plan/00-overview.md](docs/plan/00-overview.md).
It composes independent modules, each with its own plan doc that starts with an
**Interface** section — the overview depends only on those interfaces, so modules can be
implemented (and re-planned) individually without touching the rest.

| # | Module | Doc |
|---|--------|-----|
| 1 | Foundation (app skeleton, auth, deploy, CI, logging) | [01-foundation.md](docs/plan/01-foundation.md) |
| 2 | Calculation engine (cgt-calc fork wrapper) | [02-engine.md](docs/plan/02-engine.md) |
| 3 | Documents (accounts, uploads, coverage checklist) | [03-documents.md](docs/plan/03-documents.md) |
| 4 | Tax year report (numbers, explanations, SA boxes) | [04-report.md](docs/plan/04-report.md) |
| 5 | Planner & tips | [05-planner.md](docs/plan/05-planner.md) |
| 6 | Connectors (Schwab API, TrueLayer) — later phase | [06-connectors.md](docs/plan/06-connectors.md) |
