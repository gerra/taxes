# Module 2 — Calculation engine (cgt-calc fork wrapper)

Owns the fork of `capital-gains-calculator` and a safe, structured way to run it from
the web app. Everything downstream (report UI, planner) consumes this module's
`ReportBundle`; nothing else imports `cgt_calc`.

## Interface

**Provides**
- `POST /api/calc/run {year}` → runs a calculation over the current document set for
  that tax year; returns `{run_id, status}`. Runs are cached by
  `(tax_year, hash_of_document_set, fork_version)` — unchanged inputs return the
  existing run instantly.
- `GET /api/calc/runs/{id}` → status + `ReportBundle` JSON;
  `GET /api/calc/runs/{id}/pdf` → the LaTeX-rendered computation PDF.
- `validate_document(account_type, file_path) -> {ok, transaction_count, date_min,
  date_max, errors[]}` — internal function used by module 3 at upload time (runs the
  matching fork parser only, no full calculation).
- **`ReportBundle`** (JSON, versioned `schema_version`):
  - `capital_gains`: per-disposal entries (date, symbol, quantity, proceeds, gain/loss,
    and the per-rule breakdown: SAME_DAY / BED_AND_BREAKFAST / SECTION_104 / SPIN_OFF
    with quantity, allowable cost, fees, pool state after) — serialised from
    `calculation_log`.
  - `totals`: disposal_count, disposal_proceeds, allowable_costs, gain_before_losses,
    losses, gain_after_losses, annual_exempt_amount, taxable_gain.
  - `dividends`: per-event list + totals (gross, withheld, treaty relief, allowance,
    taxable); `interest`: UK vs foreign, per (broker, month); `interest_tax`; `eri` events
    if any.
  - `other_income`: per-payment rows `{date, source, amount_gbp, tax_gbp}` for income that is
    neither interest nor dividends — REIT property income distributions (under the REIT's
    ticker, grossed up, with the 20% withheld as `tax_gbp`) and share-lending fees (under
    the broker) — from the fork's `OTHER_INCOME`/`OTHER_INCOME_TAX` actions; totals
    `other_income`, `other_income_tax`.
  - Exempt securities (TCGA 1992 s115): the worker recognises gilts and UK T-bills by name
    + GB ISIN and merges the user's `exempt_securities` table (ticker/ISIN, API
    `/api/exempt-securities`), passing them to the fork's `--exempt-securities`. Their
    disposals appear in `disposals` with `exempt: true` and are excluded from every total
    (`exempt_disposal_count`/`exempt_disposal_proceeds` say how many). `exempt` carries the
    detected list, the accrued interest the engine noted on dirty-price gilt trades, and the
    peak gilt nominal held for the Accrued Income Scheme £5,000 test (`ais_applies`).
  - `portfolio_eoy`: per-symbol quantity + pooled cost at 5 April.
  - `warnings[]`: balance-check failures, missing allowances, unknown spin-offs, etc.
- Tables owned: `calc_runs` (inputs hash, status, bundle JSON, pdf path, log excerpt).

**Consumes** — module 1 (app/db/paths); the fork repo; document file paths + account
types from module 3 (as plain arguments — no import of module 3 code).

## The fork

- Push the local clone's 3 uncommitted mods as proper commits to
  `github.com/gerra/capital-gains-calculator`, branch `gerra` tracking upstream `main`:
  1. `main.py`: sell-to-cover amount-discrepancy downgraded to warning + recalculated
     amount (keep, but **surface the warning into `ReportBundle.warnings`** so it is
     visible in the UI, not silent).
  2. `parsers/freetrade.py`: Stock Split columns, MONTHLY_STATEMENT/TAX_CERTIFICATE
     skips, PROPERTY→INTEREST, ISIN fallback, relaxed header validation.
  3. `parsers/schwab.py`: symbol-less NRA Tax Adj → ADJUSTMENT.
- Add to the fork: extend `CAPITAL_GAIN_ALLOWANCES` / `DIVIDEND_ALLOWANCES` for
  2025/26 (£3,000 / £500) and onward as years pass.
- Pin in `requirements.txt` as `cgt-calc @ git+https://github.com/gerra/capital-gains-calculator@<sha>`.
  Upgrades = rebase `gerra` on upstream, re-pin, run golden tests.

## Detailed plan

1. **Worker subprocess** (`engine/worker.py`): the web process never imports
   `cgt_calc`. A run spawns `python -m engine.worker <job.json>` (the 3.12 venv) with
   a timeout (~120 s), which:
   - builds parsers per account type → `BrokerTransaction` lists,
   - constructs `CurrencyConverter(exchange_rates_file=<shared cache in /var/lib/taxes>)`
     — HMRC monthly-rate fetches allowed but cached persistently; OpenFIGI/yfinance off
     (`--unrealized-gains` off in v1; ISIN translation seeded from cache file),
   - constructs `SpinOffHandler` with `handler.cache` pre-seeded from a
     `spin_offs` DB table — **never lets it reach `input()`**: unseen spin-offs raise,
     and the error surfaces as an actionable warning ("tell me the source ticker for X"),
     which the UI turns into a small form writing the mapping back,
   - runs `convert_to_hmrc_transactions` + `calculate_capital_gain`,
   - serialises `CapitalGainsReport` + `calculation_log` → `ReportBundle` JSON on
     stdout; renders the PDF via `render_pdf` into the run's directory,
   - all file output under `/var/lib/taxes/tmp/<run_id>/` (pdflatex needs a writable
     cwd), moved into the run's permanent dir on success.
2. **Serialiser**: a dedicated `engine/serialize.py` mapping model objects → JSON with
   `Decimal` as strings; unit-tested against fixtures so fork upgrades that change the
   model break loudly.
3. **Run manager** (`core/` + blueprint): job table, single-flight lock (one calc at a
   time is fine), input hashing, warning extraction from worker stderr/exit codes;
   `CgtError` subclasses mapped to readable messages (e.g. `ExchangeRateMissingError` →
   "HMRC hasn't published rates for <month> yet").
4. **Golden tests**: fixtures from the real exports currently in
   `../capital-gains-calculator` (sanitised) + expected totals produced by the CLI;
   `pytest` asserts the wrapper's bundle matches the CLI's stdout summary numbers.
   This is the safety net for every fork upgrade.

## Acceptance

- Running year 2025 over the same files as a manual `cgt-calc` invocation produces
  identical totals (proceeds, gains, losses, dividends, interest) and a PDF.
- A document set containing an unknown spin-off fails with an actionable warning, not
  a hang.
- Killing the worker mid-run leaves no corrupt state; re-running works.

## Open questions

- Whether to also serialise an `explain` string per figure here or leave all prose to
  module 4 (leaning: engine emits only structured facts; module 4 owns wording).
