# taxes

Private web app at **taxes.gerra.sh** for preparing UK Self Assessment investment figures
(capital gains, dividends, interest) from broker documents, with explanations for every
number and a planner that suggests concrete tax wins.

Built on a fork of [KapJI/capital-gains-calculator](https://github.com/KapJI/capital-gains-calculator)
(`cgt-calc`), following the fintrack/www deployment playbook (Hetzner + nginx + systemd +
GitHub Actions).

## Status

v1 live at https://taxes.gerra.sh. Open items: [TODO.md](TODO.md).

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
