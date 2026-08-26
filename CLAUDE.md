# taxes — project rules

Private web app (taxes.gerra.sh) computing UK Self Assessment investment figures
via a fork of cgt-calc, plus a planner. Plan docs: `docs/plan/` (module docs are
interfaces — read `00-overview.md` first).

## Architecture at a glance

- Flask (`app.py`, port 5002) + React/Vite SPA (`web/`), SQLite, single user.
- `core/` = business logic; `blueprints/` = HTTP only; **all SQL in `core/repo.py`**;
  all filesystem paths from `core/paths.py` (`TAXES_DATA_DIR`).
- `engine/worker.py` is the ONLY module that imports `cgt_calc`, and it always
  runs as a subprocess (the library mutates global state and can block on
  input()). `engine/runner.py` (web side) builds document sets and spawns it.
- Uploaded documents are Fernet-encrypted at rest (`core/crypto.py`).
- Per-tax-year constants (allowances, rates, SA boxes) live ONLY in
  `core/tax_years.py` — yearly maintenance: extend it and the fork's `const.py`.

## Hard rules

- Never import `cgt_calc` in the web process.
- Money figures cross the API as strings (Decimal precision); the frontend formats.
- `secrets/` is never committed or rsynced; deploy via `scripts/deploy_secrets.sh`.
- Every figure shown in the report UI must carry an `explain` string.
- Tips are pure functions in `core/tips.py` with unit tests for their arithmetic.

## Dev

- `make venv install` (uv, Python 3.12), `make test`, `make lint`, `make format`.
- Run: `.venv/bin/python app.py` + `cd web && npm run dev`.
- `.reported-figures.md` (git-ignored, laptop only): figures from the returns already
  filed for 2022/23–2024/25, for regression-checking the tool. Never commit or deploy.
- cgt-calc dep: fork at github.com/gerra/capital-gains-calculator, branch `gerra`
  (locally: `../capital-gains-calculator`, installed editable into `.venv`, so the
  checkout IS the local engine; the server installs `@gerra` from GitHub).
  Upgrades: `git fetch origin && git rebase origin/main gerra`, fix conflicts, run
  the fork's tests, `uv pip install --python .venv/bin/python -e ../capital-gains-calculator`,
  run `make test` here, then `git push --force-with-lease gerra gerra` (the branch
  pin means the next taxes deploy picks it up).

## Deploy

Push to main → GitHub Actions lint/test → rsync to hetzner_gb
(`/root/Projects/taxes`) → build web on server → install systemd unit →
restart → smoke test. nginx conf via `scripts/push-conf.sh`. Logs:
`journalctl -u taxes` (also visible at gerra.sh/status).
