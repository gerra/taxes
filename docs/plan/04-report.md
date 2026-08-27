# Module 4 — Tax year report (numbers, explanations, SA boxes)

The payoff page: every figure for the chosen tax year, each with a short-but-clear
explanation, mapped to the exact Self Assessment boxes, with drill-down to the
per-disposal computation and the official-style PDF attachment.

## Interface

**Provides**
- Report page per tax year (SPA route `/report/<year>`), rendered from module 2's
  `ReportBundle` + module 3's coverage status (an incomplete document set shows a
  prominent "figures are provisional — missing X" banner, never silently wrong numbers).
- SA box mapping table (`sa_boxes` in the bundle view model): each row = form + box
  number + value + one-tap copy + explanation popover.
- Explanation registry: static prose keyed by figure id, interpolated with the year's
  values (content, not code — a single `content/explanations.<year>.ts` + shared base).
- Figures feed for module 5: `GET /api/report/{year}/summary` (taxable gain, taxable
  dividends, UK/foreign interest, allowances used/remaining).

**Consumes** — modules 1, 2 (ReportBundle, PDF), 3 (coverage), and a per-tax-year
constants file (allowances, rates, box numbers) shared with module 5.

## Page structure

1. **Headline cards**: taxable capital gain (after AEA), taxable dividends, UK
   interest, foreign interest — each with an "estimated tax at your rates" secondary
   line (rates from module 5's inputs when available; otherwise shown at both
   basic/higher rate with a note).
2. **SA boxes** (the "what do I actually type into the return" table) — initial mapping,
   every box number to be verified against the actual year's forms during implementation:
   - **SA108 "Listed shares and securities"**: number of disposals; disposal proceeds;
     allowable costs; gains before losses; losses in the year. Plus the note that the
     computation PDF must be attached, and (for 2024/25) the pre/post 30 Oct 2024
     gain split if HMRC's adjustment box applies.
   - **SA100**: untaxed UK interest; UK dividends (Freetrade GBP dividends);
     small-amounts foreign dividend/interest boxes where eligible; **other UK income**
     box 17 (REIT PIDs gross + share-lending fees) with the REITs' 20% withholding in
     box 19 and the description for box 21 in the explanation — shown only when non-zero.
   - **Exempt disposals** (gilts, T-bills): summarised in a banner with an explanation and
     badged in the disposals table; never in the SA108 boxes. An Accrued Income Scheme
     notice flags gilt trades when more than £5,000 nominal was held (not computed).
   - **SA106**: foreign dividends (Schwab USD), foreign tax taken off (capped at the
     treaty rate — 15% for the US), foreign interest, bond-fund interest distributions,
     and Foreign Tax Credit Relief. FTCR is a credit against the tax due, capped at the
     lower of the tax withheld, the treaty rate and the UK tax on that same income; it
     never reduces the taxable amount.
   - **SA108 box 51** in a year whose CGT rates changed mid-year (2024/25 from 30 Oct):
     the return's own calculation charges the whole year at the pre-change rates, so the
     extra due on later disposals is entered by hand. The report shows the return's
     figure, the adjustment, and what is actually due.
   - **ERI** (if present): offshore-fund excess reported income per HS265.
3. **Capital gains drill-down**: table of disposals (date, symbol, quantity, proceeds,
   gain/loss) expanding to the rule-by-rule breakdown from `calculation_log` — the
   same-day/B&B/S104 matches, allowable cost, fees, and the pool state after. This IS
   the "explanation of every number" for gains: each line links its rule to a
   two-sentence plain-English description (what the rule is, why it applied here).
4. **Distributions, classified**: every distribution itemised — date, ticker, gross in
   the payment currency, the HMRC rate used, GBP amount, tax withheld — against what it
   is for UK tax rather than what the broker called it. REIT property income
   distributions (20% withheld) become property income, distributions from funds holding
   >60% interest-bearing assets become savings income, and neither uses the dividend
   allowance. Each row expands to the reasoning. `core.estimator` owns the rules; an
   offshore fund whose reporting-fund status is unknown gets a notice rather than a
   guess. Below it, the raw per-event dividend and interest lists as the broker sent
   them, monthly-grouped interest per broker.
5. **Warnings**: everything from `ReportBundle.warnings` (balance-check, recalculated
   sell-to-cover amounts, missing allowance for a future year) rendered as first-class
   cards — nothing the engine noticed stays hidden.
6. **Downloads**: the cgt-calc PDF (attach to the return); CSV of the SA box table.

## Explanation style

Every number gets: *what it is* (one sentence), *how it was computed here* (with this
year's actual values), *where it goes* (form + box). Example: "Disposal proceeds
£48,210 — the GBP sum of everything you sold this tax year, converted at HMRC monthly
rates on each sale date. Goes in SA108 box 24." Keep each under ~3 sentences; deeper
detail lives in the drill-down.

## Detailed plan

1. View-model builder (`core/report_view.py`): ReportBundle + tax-year constants →
   sa_boxes + cards + drill-down structures; unit-tested with a golden bundle.
2. Per-tax-year constants file (shared with module 5): allowances, CGT/dividend rates
   incl. the 30 Oct 2024 mid-year change, box numbers, filing deadlines. One file per
   year, verified against the real HMRC forms/notes for that year.
3. Explanation content pass: write the registry for all ~25 figure ids.
4. UI: report route, cards, tables, popovers, copy buttons, provisional banner,
   PDF/CSV downloads. Chart.js only if something genuinely benefits (e.g. gains
   timeline) — not required for acceptance.

## Acceptance

- For the last filed year, the page's SA box values match what was actually submitted
  (or differences are explained by known fixes).
- Every displayed number has a working explanation popover; no figure renders without one.
- With a document gap present, the provisional banner shows and names the gap.

## Open questions

- Whether to add a side-by-side "what changed vs last year" view (nice, not v1).
