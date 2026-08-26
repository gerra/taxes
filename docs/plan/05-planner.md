# Module 5 — Planner & tips

Turns the report plus a few manually entered income figures into concrete, quantified
actions: "pay £X into your pension before 5 April and save ~£Y". Also the place where
"estimated tax at your rates" for the report comes from.

## Interface

**Provides**
- Inputs form + storage (`planner_inputs` per tax year): employment income (P60 box 1),
  tax deducted, payroll pension contributions (with method: net pay vs relief at
  source), personal SIPP contributions, Gift Aid, student loan plan (if any), other
  income. Investment figures auto-filled from module 4's summary feed (overridable).
- Derived profile: total income, adjusted net income, marginal-rate bands actually
  occupied, personal-allowance taper position, remaining basic-rate band.
- `GET /api/planner/{year}` → profile + ordered tips list; each tip:
  `{id, title, what_to_do, why (rule, 2-3 sentences), estimated_win_gbp,
  deadline, confidence, how_to_execute, status, status_note}`.
- `how_to_execute`: ordered, concrete steps for claiming a tip, rendered when the card
  is expanded. For the pension tip these name the actual route — an AVC through the
  workplace scheme (salary sacrifice: employer contribution, no earnings cap, saves NI,
  but added back to threshold income) or a personal SIPP/AVC (RAS, capped at relevant UK
  earnings, does reduce threshold income) — state that the year's own allowance is spent
  before any carry-forward, and that money must reach the provider by 5 April. For a
  charge: SA101 box 10, check the prior years, and Scheme Pays (mandatory only where the
  input to one scheme beat the *standard* allowance; election by 31 July of the year
  after the tax year).
- Use-it-or-lose-it status (`core/tips.py`): `status` is `"lost"` (red) when the
  benefit is already gone, `"expiring"` (orange) when it still can be taken but
  is on a clock, else `null`; `status_note` says what and by when, in money.
  Allowances that never carry forward (CGT annual exempt amount, ISA, the
  personal allowance a contribution would restore) are lost once the selected
  year has closed and expiring inside its last `EXPIRING_DAYS` (60); pension
  carry-forward is per-slice — only the year that has aged out of the three-year
  window expires. A lost tip drops its `estimated_win_gbp` and its `what_to_do`
  stops proposing an action that is no longer possible. Tips sort expiring
  first, then lost, then by estimated win.
- Works for the tax year now running as well as finished ones: that year has no report
  yet, so investment figures start at zero and the manual overrides carry it. This is
  the tab where "expiring" tips are actionable.
- Estimated-tax service used by module 4's headline cards (CGT at 18/24%, dividends at
  8.75/33.75/39.35%, interest at marginal rate after PSA — per the year's constants file).
- Tables owned: `planner_inputs`.

**Consumes** — module 1, module 4's summary feed, the per-tax-year constants file.

## Tip catalogue (v1)

Each is a pure function `(profile, year_constants) -> tip | None`, unit-tested:

1. **Pension headroom** (`core/pension_aa.py`, Decimal): each year's own allowance
   (£40k to 2022/23, £60k after) tapered with that year's parameters — only when both
   threshold income (> £200k) and adjusted income (> £240k/£260k) are exceeded, reduction
   rounded down to £1, floor £4k/£10k — minus that year's pension input; carry-forward
   from the 3 prior years, oldest first, replayed chronologically so a prior year's own
   excess consumes what was available to *it*; only years with scheme membership (a
   non-zero input) carry. Prior years' pension inputs come from the selected year's
   "Pension total, YYYY/YY" boxes (or that year's own saved planner); their income
   comes only from their own saved planner — without it the year is flagged unverified.
   Open year: suggest a contribution — workplace AVC or RAS SIPP — capped at relevant UK
   earnings, with the threshold-income hint when tapered; win = contribution × marginal
   relief rate; `how_to_execute` carries the steps.
   Closed year (today > 5 April after it): report the annual-allowance charge, if any
   (SA101 box 10), and what carries into the next year. The tip's `detail` block shows
   every step; `warnings` list the input gaps. Status: red for a charge that landed or
   for the oldest year's unused allowance that aged out; orange in the open year for a
   charge still avoidable and for carry-forward in its last year.
2. **60% trap**: if adjusted net income is in £100,000–£125,140, compute the exact
   pension/Gift Aid amount that restores the personal allowance and the effective
   relief rate (~60%+). Once the year has closed the pension route is gone but Gift Aid
   can still be carried back by electing on that year's return (ITA 2007 s426) up to its
   31 January deadline — orange until then, red after.
3. **CGT allowance harvesting**: unused AEA (£3,000) before 5 April + which current
   holdings (from `portfolio_eoy`) could realise that gain; warns about the 30-day
   rule making "sell and rebuy the same thing" ineffective → segue to tip 4.
4. **Bed & ISA / Bed & SIPP**: unused ISA allowance (£20k, manual input of what's
   used) + moving GIA holdings inside it kills future CGT/dividend tax; estimated
   ongoing yearly win from current dividend yield.
5. **Dividend allowance** (£500) and **PSA** (£1,000/£500/£0) usage — if exceeded,
   quantify the tax and point at tip 4 / interest-bearing cash inside ISA.
6. **Gift Aid**: basic-rate-band extension value for a higher-rate payer.
7. **Filing logistics**: online deadline 31 Jan, payments on account (whether they'll
   be triggered, estimated amounts), "attach the computation PDF".
8. **Sanity flags**: excess reported income present (offshore funds — HS265),
   US withholding at 30% instead of treaty 15% (W-8BEN expired?), interest from
   bond-ish funds that should be classified as interest not dividends
   (`--interest-fund-tickers`).

Each tip renders with its assumptions visible ("assumes P60 figure £X you entered").
A disclaimer footer: computed hints, not advice.

## Detailed plan

1. Extend the per-tax-year constants file with rate bands, taper thresholds, PSA/ISA
   figures (module 4 already created it).
2. `core/tax_profile.py`: income aggregation → adjusted net income, band occupancy,
   marginal rates. Unit tests against hand-computed examples (incl. taper edge cases,
   Scottish rates explicitly out of scope).
3. `core/tips/` — one module per tip, shared signature, registry ordered by
   estimated win.
4. Inputs UI (one compact form, saved per year) + tips list UI (cards with win
   amounts, expandable why/how).
5. Wire the estimated-tax service into module 4's headline cards.

## Acceptance

- With your real inputs, the pension and 60%-trap tips produce numbers you can verify
  by hand; each tip's arithmetic is covered by a unit test.
- Changing an input (e.g. +£10k salary) updates profile, tips and report tax
  estimates coherently.

## Open questions

- ~~Carry-forward needs 3 prior years of pension data~~ — resolved: 3 totals on the
  selected year's form, falling back to earlier years' own saved planners (which also
  supply the income for their taper test).
- Prior-year threshold income only sees the salary-sacrifice add-back when that year's
  own planner has the split; a bare "pension total" is treated as all-employer.
