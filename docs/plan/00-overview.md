# High-level plan — taxes.gerra.sh

## What this is

A private (invite-only, effectively single-user) web app that turns broker/bank documents
into ready-to-file UK Self Assessment investment figures:

- **Computes** capital gains (same-day / bed-and-breakfast / Section 104), dividends and
  interest for a chosen tax year, using a pinned fork of `cgt-calc`.
- **Explains** every number — short but clear — down to per-disposal matching-rule
  breakdowns, and maps totals to the exact SA100 / SA106 / SA108 boxes.
- **Requests** exactly the documents needed for a given tax year, per account, with
  export instructions and gap detection (v1: manual upload only).
- **Suggests** practical wins with estimated £ amounts (pension contributions,
  60% trap, unused allowances, bed-and-ISA, …) via a planner fed by the report plus a
  few manually entered income figures.

## Locked decisions

| Decision | Choice |
|---|---|
| Scope | Investment figures + planner (not a full SA100 draft) |
| Access | Google sign-in, gated by `allowed_emails` (fintrack pattern); single-tenant assumptions OK |
| cgt-calc | Fork under own GitHub with the 3 local mods committed; pip-installed from a pinned git ref; used **as a library** |
| Connectors | v1 is manual upload for everything (Schwab, Freetrade, banks); Schwab Trader API connector is the first post-v1 phase |
| Stack | fintrack playbook: Flask + gunicorn + systemd, React 18 + TS + Vite, SQLite, nginx + certbot on the Hetzner box (`hetzner_gb`, 195.201.94.84) |
| Domain | `taxes.gerra.sh` canonical (precedent: `vpn.gerra.sh`); no `.london`/`.kz` mirrors unless wanted later |

## Architecture

```
browser (React SPA)
   │ /api/*  (JWT cookie, Google OAuth)
nginx :443 taxes.gerra.sh ──► gunicorn 127.0.0.1:5002 ──► Flask
                                                            │
        ┌───────────────┬───────────────┬───────────────────┤
        ▼               ▼               ▼                   ▼
   [3] Documents   [2] Engine      [4] Report          [5] Planner
   accounts,       cgt-calc fork   ReportBundle →      income inputs +
   uploads,        in a worker     UI + SA boxes +     ReportBundle →
   coverage        subprocess      explanations + PDF  tips with £ wins
        │               │
        ▼               ▼
   /var/lib/taxes  SQLite: users, accounts, documents,
   (files, db)     calc_runs, planner_inputs
```

Data flow: **Documents** owns what the user has uploaded and whether it covers the
needed period → **Engine** consumes a document set + tax year and produces a
`ReportBundle` (JSON of every figure + calculation log + rendered PDF) → **Report**
renders it with explanations and SA box mapping → **Planner** combines the bundle's
totals with manually entered income to produce tips. **Connectors** (later) feed the
Documents module automatically; nothing downstream changes.

## Modules as interfaces

Each module doc (`01`–`06`) starts with an **Interface** section: what it exposes
(API routes, data shapes, DB tables it owns) and what it consumes. This overview and
other modules rely only on those Interface sections. When implementing a module,
its "Detailed plan" section may be rewritten freely; changing its Interface requires
updating the dependents listed here.

| # | Module | Depends on | Provides to |
|---|--------|-----------|-------------|
| 1 | [Foundation](01-foundation.md) | — | everything (auth, DB, deploy, logging) |
| 2 | [Engine](02-engine.md) | 1; fork repo | 3 (parse-validation), 4, 5 (ReportBundle) |
| 3 | [Documents](03-documents.md) | 1, 2 | 2 (document sets), 4 (coverage status) |
| 4 | [Report](04-report.md) | 1, 2, 3 | 5 (figures), user |
| 5 | [Planner](05-planner.md) | 1, 4 | user |
| 6 | [Connectors](06-connectors.md) | 1, 3 | 3 (auto-ingested documents) |

## Phases

Each phase ends deployed and usable, not just merged.

- **Phase 0 — Foundation** (module 1): `taxes.gerra.sh` live behind Google sign-in,
  CI green, deploy pipeline + smoke test working, `/status` shows the unit's logs.
  *Done when: you can sign in on the real domain and see an empty dashboard.*
- **Phase 1 — Engine** (module 2): fork created and pinned; API can run a calculation
  against the CSV exports currently sitting in `../capital-gains-calculator` and return
  the full JSON + PDF. *Done when: numbers match a local `cgt-calc` run of the same files.*
- **Phase 2 — Documents** (module 3): accounts, uploads with instant parse validation,
  per-year checklist with coverage gaps. *Done when: uploading your real Schwab +
  Freetrade exports yields a green checklist for 2025/26.*
- **Phase 3 — Report** (module 4): tax-year page with headline figures, SA box table
  with copy buttons, per-disposal drill-down, explanations, PDF download.
  *Done when: you could fill the investment parts of a return from this page alone.*
- **Phase 4 — Planner** (module 5): income inputs + tips with estimated £ wins.
  *Done when: the pension tip shows a correct, explained number for your situation.*
- **Phase 5 — Connectors** (module 6): Schwab Trader API first (spike gate), TrueLayer
  optional after.

## Cross-cutting risks & facts

- **cgt-calc is server-unsafe out of the box**: `SpinOffHandler` calls `input()` in a
  loop, `main()` mutates the global decimal context, `SchwabParser.awards_prices` is a
  class-level mutable, and it writes cache files and calls HMRC/OpenFIGI/yfinance at
  runtime. Mitigation (module 2): run every calculation in a short-lived worker
  subprocess with injected FX data and pre-seeded spin-offs; never import it in the
  web process.
- **Allowance tables end**: fork's `const.py` has CGT allowances through tax year 2025
  and dividend allowances through 2024 — the fork must extend them (and this becomes a
  small yearly maintenance task).
- **Server runtime**: `cgt-calc` needs Python ≥3.12 (fintrack runs 3.10) — install via
  `uv` on the box; PDF needs `pdflatex` (`apt install texlive-latex-base`, as the
  upstream Dockerfile does).
- **Section 104 needs full history**, not just the tax year: coverage tracking must
  span from the first-ever acquisition (Schwab exports max ~4 years per file, Freetrade
  12 months — multiple chunks are normal and must union cleanly).
- **Tax content accuracy**: SA box numbers and allowance/rate figures change per tax
  year (e.g. the mid-year CGT rate change on 30 Oct 2024). All such constants live in
  one per-tax-year data file, verified against the actual HMRC forms during modules 4–5.
- **Privacy**: financial documents at rest on the box are Fernet-encrypted (module 3);
  `secrets/.env` never in git or rsync (fintrack pattern); this app is for the account
  owner only — not tax advice for others.

## Repo conventions (inherited from fintrack/www)

Flask app on port **5002**; all SQL in `core/repo.py`; paths from `core/paths.py` keyed
off `TAXES_DATA_DIR` (prod `/var/lib/taxes`, dev `./data`); blueprints are HTTP-only;
logging via `logging.basicConfig` to stdout → journald (`journalctl -u taxes`);
`deploy/nginx/` + `scripts/push-conf.sh`; systemd unit installed by CI (www pattern);
CI = fintrack's gated workflow (python + frontend jobs → rsync deploy → smoke test →
failure-log artifacts); secrets pushed by `scripts/deploy_secrets.sh`; code at
`/root/Projects/taxes` on the server.
