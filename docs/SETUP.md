# One-time setup — things only you can do

Everything code-side is done; these six steps need your accounts. Order matters
only where noted.

## 1. GitHub repos (needed before CI works)

- Create **private repo `gerra/taxes`** (empty, no README) — then push:
  `git remote add origin git@github.com:gerra/taxes.git && git push -u origin main`
- **Fork `KapJI/capital-gains-calculator`** to your account (one click on GitHub).
  The `gerra` branch with your modifications is already committed locally — push it:
  `cd ../capital-gains-calculator && git push gerra gerra`
  (remote `gerra` → `git@github.com:gerra/capital-gains-calculator.git` is already set.)
  CI's python job installs from that branch, so it fails until this push happens.

## 2. GitHub Actions deploy secrets

In `gerra/taxes` → Settings:
- Create an **environment named `default`**.
- Add repo secrets: `DEPLOY_HOST` = `195.201.94.84`, `DEPLOY_USER` = `root`,
  `DEPLOY_KEY` = the same private deploy key your `www`/`ft` repos use.
  ⚠️ That key currently sits in **plaintext** at
  `www/.github/workflows/secrets.env` — consider generating a fresh keypair for
  this repo instead (`ssh-keygen -t ed25519`), adding the public half to the
  server's `authorized_keys`.

## 3. Google OAuth client

[console.cloud.google.com](https://console.cloud.google.com) → APIs & Services →
Credentials → Create credentials → OAuth client ID → **Web application**:
- Authorized redirect URIs:
  - `https://taxes.gerra.sh/oauth/google/callback`
  - `http://localhost:5002/oauth/google/callback`
- Put the client ID/secret into `secrets/.env` (`GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`). The random secrets are already generated there.

## 4. DNS record

Hetzner DNS console → zone `gerra.sh` → add **A record `taxes` → 195.201.94.84**
(same as vpn.gerra.sh).

## 5. TLS cert + nginx (after DNS resolves)

```
ssh hetzner_gb 'certbot certonly --nginx -d taxes.gerra.sh'
scripts/push-conf.sh
```

## 6. First deploy

```
scripts/deploy_secrets.sh      # pushes secrets/.env to the server
git push origin main           # CI tests + deploys + smoke-tests
```

Then open https://taxes.gerra.sh and sign in with your Google account
(`ADMIN_EMAIL` is pre-set to it).
