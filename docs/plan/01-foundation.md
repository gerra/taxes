# Module 1 — Foundation

App skeleton, auth, database, deploy pipeline, logging. Everything other modules stand on.
Almost all of this is a deliberate copy of fintrack (with www's "CI installs the systemd
unit" improvement), so implementation is mostly transplanting known-good patterns.

## Interface

**Provides**
- Flask app (`app.py`) with blueprint registration, SPA fallback serving `web/dist`,
  and auth middleware: every `/api/*` route requires a valid `tx_auth` JWT cookie and
  gets `g.user_id` / `g.email`; `GET /api/auth/me` is the unauthenticated probe.
- Auth routes: `/oauth/google/start`, `/oauth/google/callback`, `/logout`.
  Google only (no password/passkey/GitHub) — sign-ups rejected unless the email is in
  `allowed_emails`.
- `core/db.py` (`ensure_db()` idempotent migrations at startup), `core/repo.py`
  (all SQL lives here), `core/paths.py` (`TAXES_DATA_DIR` → prod `/var/lib/taxes`,
  dev `./data`; subdirs `docs/`, `logs/`, `tmp/`).
- Tables owned: `users`, `allowed_emails`.
- React 18 + TS + Vite SPA in `web/` with `useAuth` hook, login view, empty
  authenticated dashboard shell with nav for the future modules.
- Working pipeline: push to `main` → lint/test → deploy → `https://taxes.gerra.sh` updated.

**Consumes** — nothing (root module).

## Detailed plan

1. **Repo skeleton**: `app.py`, `gunicorn.conf.py` (bind `127.0.0.1:5002`, workers 2,
   logs to stdout), `Makefile` (install/lint/format/test/ci — fintrack's), `pyproject.toml`
   (ruff + pytest config), `requirements.txt` / `requirements-dev.txt`, `web/` via
   `npm create vite@latest` matched to fintrack's eslint/prettier/vitest setup, Vite dev
   proxy `/api|/oauth|/logout` → `localhost:5002`. `CLAUDE.md` with the architecture
   rules (SQL only in repo.py, blueprints HTTP-only, paths from core/paths.py).
2. **Python**: target **3.12+** from day one (the engine's fork requires it) — manage
   with `uv` locally and on the server (`uv venv --python 3.12`), unlike fintrack's 3.10.
3. **Auth**: port fintrack's `core/auth.py` stripped to Google + JWT cookie
   (`tx_auth`, HttpOnly, SameSite=Lax, 7-day expiry, sliding re-issue after 4 days),
   `allowed_emails` gate, `ADMIN_EMAIL` auto-allowed. New Google Cloud OAuth client with
   redirect `https://taxes.gerra.sh/oauth/google/callback` (+ localhost for dev).
4. **Secrets**: fintrack's layered dotenv — `secrets/.env` (deployed) +
   `secrets/.env.local` (dev override), `secrets/README.md` documenting every var:
   `FLASK_SECRET`, `JWT_SECRET`, `FERNET_KEY`, `GOOGLE_CLIENT_ID/SECRET`, `BASE_URL`,
   `ADMIN_EMAIL`, `TAXES_DATA_DIR`, `LOG_LEVEL`. `scripts/deploy_secrets.sh` (backup +
   scp + restart).
5. **Logging**: `logging.basicConfig(stream=sys.stdout, format="%(asctime)s %(levelname)-8s %(name)s %(message)s")`
   before project imports; gunicorn access/error to `-`; systemd →
   journald (`SyslogIdentifier=taxes`) so it appears in gerra.sh `/status` under "Yours".
6. **nginx + TLS**: `deploy/nginx/taxes.gerra.sh.conf` modeled on fintrack's vhost
   (proxy to 5002, `client_max_body_size 50M` for statement uploads,
   `proxy_read_timeout 300s`, the `/opt/ssl-manager` well-known include, letsencrypt
   options + dhparam, IPv6 listeners, :80 → :443 redirect scoped to `location /`).
   `scripts/push-conf.sh` (scp → sites-available, symlink, `nginx -t && reload`).
   Cert: `certbot certonly --nginx -d taxes.gerra.sh` (never bare `certbot --nginx`).
7. **systemd**: `deploy/taxes.service` checked into the repo and installed by CI
   (www pattern), `ExecStart=/root/Projects/taxes/.venv/bin/gunicorn -c gunicorn.conf.py app:app`,
   `Restart=on-failure`, journald output.
8. **CI/CD**: single `.github/workflows/ci.yml` cloned from fintrack: `python` job
   (ruff check + format, pytest) and `frontend` job (eslint, prettier, tsc, vitest)
   gate a `deploy` job (skipped on PRs) that rsyncs (excluding `.venv`, `secrets`,
   `data`, `web/dist`, caches), installs deps + builds `web/` **on the server**,
   installs the unit, restarts, `systemctl is-active`, then curl smoke test against
   `https://taxes.gerra.sh/api/auth/me`, with journalctl artifact upload on failure.
   Secrets: reuse `DEPLOY_HOST`/`DEPLOY_USER`/`DEPLOY_KEY` values (new GitHub repo
   `gerra/taxes`, environment `default`).
9. **Server prep** (manual, once): `uv` + Python 3.12 on the box,
   `texlive-latex-base` (for module 2), `/var/lib/taxes` created, DNS A record
   `taxes.gerra.sh` → 195.201.94.84, cert issued.

## Acceptance

- Sign in with Google on https://taxes.gerra.sh; a non-allowed Google account is
  rejected with a clear message.
- A pushed commit that breaks a test does not deploy; a good one deploys and passes
  the smoke test.
- `journalctl -u taxes -f` shows structured request logs; the unit appears in `/status`.

## Open questions

- None blocking. (If multi-user ever becomes real, revisit rate limiting and
  per-user encryption keys — out of scope now.)
