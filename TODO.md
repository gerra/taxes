# TODO

## Now (operational gaps)

- [ ] **Backups** — nothing backs up `/var/lib/taxes` (SQLite DB + encrypted documents
  + run PDFs). Plan: nightly on-server snapshot (`sqlite3 .backup` + tar of docs/,
  rotated ~14 days) via systemd timer, plus `make backup` to pull the latest to the
  laptop. Template: `../fintrack/scripts/backup.py`.
- [ ] **Copy `FERNET_KEY` to a password manager** — losing it loses every uploaded
  document (it lives only in `secrets/.env` on laptop + server).
- [ ] **Rotate the Google OAuth client secret** (it passed through a chat transcript)
  and **retire/rotate the shared deploy key** sitting in plaintext at
  `../www/.github/workflows/secrets.env` (at minimum `chmod 600` it).

## Next (before filing with this tool)

- [ ] **Verify SA box numbers against the real form PDFs** for the year being filed
  (`core/tax_years.py` + `core/report_view.py` follow the 2024/25 layout; yearly task).
- [ ] **Interest-fund tickers** — cgt-calc's `--interest-fund-tickers` reclassifies
  bond-fund "dividends" as interest, but the UI doesn't expose it. Likely relevant:
  ERNS (ultrashort bond ETF) distributions should probably be interest, not dividends.
  Add a per-user setting and pass it through the engine job.
- [ ] **Excess Reported Income review** — Irish-domiciled ETFs held (VGOV, VUSC, ERNS)
  are offshore reporting funds; bundled ERI data covers Vanguard Funds Plc only through
  2024. Check the fund reports for later years and feed `--eri-raw-file` if needed.
- [ ] **2024/25 mid-year CGT rates** — the report shows the pre/post 30 Oct 2024 gain
  split, but the tax estimate applies post-change rates to everything; refine the AEA
  allocation if actually filing 2024/25 through the planner numbers.

## Later

- [ ] Schwab Trader API connector (spike-gated — `docs/plan/06-connectors.md`);
  TrueLayer for Revolut/HSBC only if manual interest entry ever annoys.
- [ ] Drag-and-drop upload zones on account cards.
- [ ] Dark mode (design is light-only).
- [ ] Login rate limiting (invite-only makes this low-risk; fintrack uses flask-limiter).
- [ ] Deadline reminders (31 Jan / 5 Apr) — cron + email, or just a banner when close.
