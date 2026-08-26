# Module 6 — Connectors (post-v1)

Automatic document ingestion. Deliberately out of v1 (decision 2026-08-26): everything
ships manual-first, and connectors only ever *feed module 3* — they produce the same
document records uploads do, so nothing downstream changes when they land.

Priority: **Schwab first** (the account that matters most), TrueLayer (Revolut/HSBC)
only if typing two interest totals a year ever feels worth automating away.

## Interface

**Provides**
- Per-account "Connect" flow (OAuth start/callback routes) + "Sync now" action +
  last-sync status on module 3's account cards.
- Synced data lands as generated documents in module 3 (`source: connector` instead of
  `source: upload`), rendered in the fork's `raw`/native formats, coverage-tracked
  identically. Manual upload always remains available as override/fallback.
- Tables owned: `connector_tokens` (Fernet-encrypted), `sync_runs`.

**Consumes** — modules 1, 3; fintrack's proven client code as the starting point
(`../fintrack/parsers/schwab_api.py`, `truelayer.py`, `core/oauth_client.py`,
`core/credentials.py` — port, don't import across repos).

## Schwab (phase 5a)

Existing asset: fintrack already has a working Schwab Trader API app + OAuth client
(`api.schwabapi.com`, token refresh, `fetch_schwab_transactions` pulling TRADE +
DIVIDEND_OR_INTEREST for ~2 years).

**Spike gate — answer before building** (half a day with real API access):
1. Does the Trader API expose the **Equity Award account** or only the Individual
   brokerage account? (Expected: individual only; vest FMV keeps coming from the
   manual EAC export.)
2. Do API transaction records carry everything the CSV parser needs (action taxonomy,
   fees, "as of" dates), and how far back does history really go? (Docs say date-range
   parameterised; verify multi-year pulls.)
3. Can API-fetched transactions be rendered losslessly into the Schwab CSV format the
   fork already parses (preferred: reuse the battle-tested parser + its NRA fix), or
   is a new API-native parser in the fork needed?

**Build (if spike passes)**: port the OAuth client, encrypted token store, and a sync
job that fetches since the last covered date, renders to CSV chunks, and files them
into module 3. History older than the API's floor stays manual — coverage view shows
the seam. Second OAuth app registration (or shared credentials with fintrack —
decide at build time; separate is cleaner).

## TrueLayer — Revolut + HSBC (phase 5b, optional)

Existing asset: fintrack's TrueLayer client (accounts + cards, 90-day transaction
window, per-bank token stores).

The 90-day window means a connector must sync periodically (systemd timer / cron
hitting a sync endpoint) rather than pull a year on demand — reuse fintrack's
sync-scheduler pattern. Transactions filter to interest rows → `raw` format INTEREST
entries. Given module 3's "type one number per bank" alternative, only build this if
the manual path actually annoys.

## Not planned

- Freetrade: no API exists — permanently manual (their export is easy).
- Screen-scraping any broker: no.
- New aggregators (Plaid etc.): the GoCardless/Nordigen free tier is gone (wound down
  2025); TrueLayer via the existing fintrack access is the only sane aggregator path.

## Acceptance (Schwab)

- "Connect Schwab" → OAuth → sync produces documents that make the Schwab Individual
  account's recent coverage green with zero manual steps, and a subsequent calc run
  matches one built from a manual CSV export of the same period.
