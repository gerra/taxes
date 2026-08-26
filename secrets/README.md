# Secrets

`secrets/.env` is never in git and never in the CI rsync — it is pushed to the
server only by `scripts/deploy_secrets.sh`. Dev-only overrides go in
`secrets/.env.local` (loaded after `.env` with override, git-ignored, never
deployed).

| Var | Kind | How to get / notes |
|---|---|---|
| `FLASK_SECRET` | random | `python -c "import secrets; print(secrets.token_hex(32))"` — signs the Flask session (OAuth state). Must match prod across restarts. |
| `JWT_SECRET` | random | same generator — signs auth cookies; rotating it signs everyone out. |
| `FERNET_KEY` | random | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — encrypts stored documents. **Losing it loses every uploaded document**; keep a copy in your password manager. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | static | Google Cloud console → APIs & Services → Credentials → OAuth client (Web application). Authorized redirect URIs: `https://taxes.gerra.sh/oauth/google/callback` and `http://localhost:5002/oauth/google/callback` (dev). |
| `BASE_URL` | env-specific | `https://taxes.gerra.sh` in prod, `http://localhost:5002` in dev (set in `.env.local`). Drives OAuth redirect URI and cookie `secure` flag. |
| `ADMIN_EMAIL` | static | Your Google account email — always allowed to sign in, and the only account that gets the **Admin** tab (approve/decline other people's access requests). |
| `TAXES_DATA_DIR` | env-specific | `/var/lib/taxes` in prod; `./data` in dev (set in `.env.local`). |
| `LOG_LEVEL` | optional | default `INFO`. |
