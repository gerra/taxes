# Module 3 — Documents (accounts, uploads, coverage checklist)

The "request all needed documents" experience: the user declares their accounts once,
and per tax year the app tells them exactly what to export, from where, validates each
upload instantly, and shows what's still missing.

## Interface

**Provides**
- Account registry: `GET/POST /api/accounts` — one type per broker cgt-calc parses
  (`core.repo.ACCOUNT_TYPES`): `schwab_individual`, `schwab_awards` (CSV or JSON),
  `freetrade_gia`, `hl_fund_share`, `interactive_brokers`, `morgan_stanley_awards`,
  `sharesight`, `trading212_invest`, `vanguard_gia`, plus `bank_generic`
  (Revolut, HSBC — interest via mapped CSV) and `raw_csv` (escape hatch).
  Each account stores display name + first-activity date (drives coverage-needed range).
- Uploads: `POST /api/documents` (multipart) → parse-validated via module 2's
  `validate_document` before being accepted; response includes transaction count,
  detected date range, and per-row errors on failure. `GET/DELETE /api/documents`.
- Checklist: `GET /api/checklist/{year}` → per account: required range
  (first-activity date → 5 Apr of the year), covered ranges (union of accepted
  documents), **gaps**, and step-by-step export instructions for filling each gap.
- Document set resolver: `document_set(year) -> [(account_type, file_path)]` — what
  module 2 consumes; its hash is the calc-run cache key.
- Extra inputs (small forms, not uploads): spin-off mappings, initial-prices additions,
  optional ERI raw rows — stored in tables module 2 reads.
- Tables owned: `accounts`, `documents` (+ encrypted blobs on disk), `coverage`
  (derived, cached), `spin_offs`, `initial_prices_extra`, `column_mappings`.

**Consumes** — module 1 (auth/db/paths), module 2 (`validate_document`).

## Detailed plan

1. **Storage**: originals are immutable and authoritative — stored Fernet-encrypted at
   `/var/lib/taxes/docs/<account_id>/<doc_id>` with metadata (original filename, sha256,
   uploaded_at, parsed stats) in SQLite. Calc runs decrypt to the run's tmp dir.
   Re-uploading an identical file (same sha256) dedupes silently.
2. **Parse-on-upload**: run the fork's parser for the account type immediately; reject
   with readable errors (bad header → show which columns are missing vs expected;
   encoding issues; empty file). Warn (not reject) on overlap with an existing
   document's date range — overlaps are normal with chunked exports; the engine
   dedupes nothing, so **overlapping documents for the same account must be
   trimmed/merged at document-set build time** (design detail to settle during
   implementation: prefer "newest document wins for its full range").
3. **Coverage model**: required range per account = `[first_activity, min(today, 5 Apr year+1)]`
   (Section 104 needs full history, not just the tax year). Covered = union of
   accepted documents' ranges. Gaps rendered as concrete asks:
   *"Schwab Individual: missing 6 Apr 2022 – 14 Mar 2024 — export chunk 2 of 2"*.
4. **Export instructions** (static content per account type, shown next to each gap):
   - **Schwab individual**: schwab.com → Accounts → Transaction history → select
     period (max ~4 years) → Search → Download as .csv; multiple chunks for full
     history.
   - **Schwab equity awards**: same Transaction history flow on the equity award
     account; explains why it's needed (vest FMV prices).
   - **Freetrade**: the APP (GIA → Activity → Share button, exports from 2020);
     the website only covers the last 12 months.
   - **Revolut / HSBC**: statement CSV export; only interest matters for the return —
     see column mapper below.
   - **Hargreaves Lansdown**: Tax Centre → Transaction Summary CSV, *plus* the PDF
     contract note behind every buy and sell (the CSV has no ticker, quantity or unit
     price). Notes are matched to trades by filename prefix, so they upload to the same
     account and keep their `<reference>_*.pdf` names.
   - **Interactive Brokers**: Client Portal → Transaction History → Custom period →
     CSV. GBP base currency only; not an Activity Statement or Flex Query.
   - **Morgan Stanley at Work / Sharesight**: report sets whose filenames are what
     identifies each report (`Releases Report.csv`, `All Trades Report*.csv`, …), so
     uploads keep their names and reach the parser as a directory.
   - **Trading 212**: History → export, one CSV per date range; overlaps are
     deduplicated by the export's own transaction IDs.
   - **Vanguard**: Report Generator → Client Transactions Listing, saved as CSV. One
     worksheet holds two differently-shaped tables, so exports cannot be stitched
     together — the newest upload is the one used.
5. **How a document set reaches the engine** — three shapes, in `engine.runner`:
   merged CSV (Schwab, Freetrade, IBKR: chunks concatenated, duplicate rows dropped),
   directory (HL, Morgan Stanley, Sharesight, Trading 212: originals written out under
   their own filenames, newest wins on a repeat), and single file (Vanguard). The
   filename is therefore part of a run's inputs, not just a label.
6. **Bank column mapper**: Revolut/HSBC CSVs aren't cgt-calc formats. A small UI maps
   their columns → the fork's `raw` format (`date,action,symbol,quantity,price,fees,currency`),
   with an interest-row filter (e.g. "description contains 'interest'"). Mapping saved
   per account (`column_mappings`) so future uploads auto-convert. (This also covers
   any future broker with no parser.)
7. **Checklist UI**: one page per tax year — accounts as cards, green/amber/red
   coverage bar, gap list with instructions, drag-and-drop upload zone per account,
   instant validation feedback, and "extra inputs needed" section (spin-offs the
   engine flagged, etc.).

## Acceptance

- Uploading the real Schwab (individual + awards) and Freetrade exports produces a
  fully green 2025/26 checklist, and `document_set(2025)` reproduces the manual CLI
  file arguments.
- A deliberately truncated CSV is rejected with an error naming the missing columns.
- Deleting a middle chunk turns the coverage bar amber with the exact missing range.

## Open questions

- Overlap resolution policy (see step 2) — decide with real chunked exports in hand.
- Whether bank interest is worth importing at all vs typing one number per bank into
  the planner (HSBC/Revolut interest totals are also on their annual statements);
  the mapper can be deferred if so.
