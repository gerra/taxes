"""Document-coverage computation: what date ranges each account's documents
cover vs what a tax year's calculation needs (full history from first activity —
the Section 104 pool replays everything). Users can confirm a gap as "no
activity" (coverage_overrides), which counts as covered."""

from datetime import date, timedelta

from core import repo, tax_years

# Static export instructions shown next to gaps, per account type.
INSTRUCTIONS = {
    "schwab_individual": (
        "schwab.com → Accounts → Transaction history → select period (max ~4 years "
        "per export) → Search → Download as .csv. Export multiple chunks to cover "
        "your full history; overlaps are fine. If you receive RSUs, the Equity Awards "
        "export is ALSO needed (separate account below) — vest rows in this file take "
        "their prices from it."
    ),
    "schwab_awards": (
        "Same flow, on the Equity Award account: schwab.com → Accounts → Transaction "
        "history → select the equity award account and period → Search → Download as "
        ".csv. Supplies the fair-market-value price of each vest; without it the "
        "Individual account's stock-plan rows have no cost basis."
    ),
    "freetrade_gia": (
        "Use the Freetrade APP, not the website: GIA → Activity → Share button (top "
        "right) → export CSV. The app exports from 2020; the website only covers the "
        "last 12 months."
    ),
    "hl_fund_share": (
        "hl.co.uk → Accounts → Tax Centre → generate a Transaction Summary → download "
        "its CSV. Then, for every buy and sell line in it, download the PDF contract "
        "note (Transaction History → the trade) and upload that here too: HL's CSV has "
        "no ticker, quantity or unit price, so each trade takes them from its note. "
        "Keep each note's filename starting with the trade reference, e.g. "
        "B302087054_BOUGHT.pdf. Fund & Share Account only — never an ISA, LISA or SIPP."
    ),
    "interactive_brokers": (
        "Client Portal → Performance & Reports → Transaction History → period Custom, "
        "from the account's first transaction to today → clear every type/symbol filter "
        "→ download CSV. Not an Activity Statement or Flex Query — their layout differs. "
        "The account's base currency must be GBP."
    ),
    "morgan_stanley_awards": (
        "Morgan Stanley at Work (formerly StockPlan Connect) → download the full report "
        "set and upload 'Releases Report.csv' and 'Withdrawals Report.csv' under exactly "
        "those names. Built for Alphabet GSU Class C awards; other employers and plans "
        "are untested."
    ),
    "sharesight": (
        "Sharesight → Tax → All Trades Report (since inception, 'Do not group'), and the "
        "Taxable Income Report for the tax year. Export each to a spreadsheet, save the "
        "sheet as CSV, and upload them as 'All Trades Report.csv' and 'Taxable Income "
        "Report.csv'. The portfolio's base currency must be GBP."
    ),
    "trading212_invest": (
        "Trading 212 → Menu → History → export → pick the date range, tick every data "
        "category → download CSV. Several exports covering consecutive ranges are fine; "
        "overlaps are deduplicated by transaction ID. Invest account only, never the ISA."
    ),
    "vanguard_gia": (
        "vanguardinvestor.co.uk → Documents → Report Generator → Client Transactions "
        "Listing for the whole history → save the General Account worksheet as a "
        "comma-separated CSV, keeping both the Cash Transactions and Investment "
        "Transactions tables. One file per account: the newest upload is used."
    ),
    "bank_generic": (
        "Download a statement CSV covering the tax year. Only interest rows are "
        "used — set up the column mapping once and re-use it."
    ),
    "raw_csv": (
        "CSV in cgt-calc raw format: date,action,symbol,quantity,price,fees,currency "
        "(dates YYYY-MM-DD)."
    ),
}

# Banks only feed interest, which is reported per tax year — no need for full history.
_TAX_YEAR_ONLY_TYPES = {"bank_generic"}

# Validation warnings on Individual docs that are explained by (and go away with)
# an Equity Awards document.
_AWARDS_WARNING_MARKERS = ("stock-plan", "no schwab award file")

# A Hargreaves Lansdown trade takes its ticker, quantity, unit price and dealing
# charge from a PDF contract note, which is a separate upload to the same
# account. A Transaction Summary validated before its notes arrive is warned
# about, listing the trade references it could not resolve, in exactly this
# shape (engine.worker writes it) so that the references whose note has since
# been uploaded can be dropped from the warning here.
HL_MISSING_NOTES_PREFIX = "No contract note uploaded for "
HL_MISSING_NOTES_SUFFIX = (
    " — an HL trade takes its ticker, quantity, unit price and dealing charge from the "
    "PDF note. Upload each one to this account, keeping the trade reference at the "
    "start of its filename; this warning clears once they are all here."
)


def _merge_ranges(ranges: list[tuple[date, date]]) -> list[tuple[date, date]]:
    merged: list[tuple[date, date]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _gaps(required: tuple[date, date], covered: list[tuple[date, date]]) -> list[tuple[date, date]]:
    gaps = []
    cursor = required[0]
    for start, end in covered:
        if end < required[0] or start > required[1]:
            continue
        if start > cursor:
            gaps.append((cursor, min(start - timedelta(days=1), required[1])))
        cursor = max(cursor, end + timedelta(days=1))
        if cursor > required[1]:
            break
    if cursor <= required[1]:
        gaps.append((cursor, required[1]))
    return gaps


def account_coverage(
    account: dict, docs: list[dict], tax_year: int, overrides: list[dict] | None = None
) -> dict:
    overrides = overrides or []
    year_end = tax_years.tax_year_end(tax_year)
    required_end = min(date.today(), year_end)

    doc_ranges = [
        (date.fromisoformat(d["date_min"]), date.fromisoformat(d["date_max"]))
        for d in docs
        if d["date_min"] and d["date_max"]
    ]
    override_ranges = [
        (date.fromisoformat(o["start"]), date.fromisoformat(o["end"])) for o in overrides
    ]
    covered_docs = _merge_ranges(doc_ranges)
    covered_all = _merge_ranges(doc_ranges + override_ranges)

    if account["type"] in _TAX_YEAR_ONLY_TYPES:
        required_start = tax_years.tax_year_start(tax_year)
    elif account["first_activity_date"]:
        required_start = date.fromisoformat(account["first_activity_date"])
    elif covered_docs:
        required_start = covered_docs[0][0]  # best guess: earliest seen transaction
    else:
        required_start = tax_years.tax_year_start(tax_year)

    gaps = (
        _gaps((required_start, required_end), covered_all) if required_start <= required_end else []
    )
    # Tolerate small seams (weekends/quiet weeks between exports don't
    # necessarily contain transactions — a "gap" under 21 days is only a hint).
    hard_gaps = [g for g in gaps if (g[1] - g[0]).days >= 21]
    soft_gaps = [g for g in gaps if (g[1] - g[0]).days < 21]

    if not docs:
        status = "missing"
    elif hard_gaps:
        status = "gaps"
    else:
        status = "ok"

    return {
        "account": account,
        "documents": docs,
        "required": {"start": required_start.isoformat(), "end": required_end.isoformat()},
        "covered": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in covered_docs],
        "confirmed_empty": [
            {"id": o["id"], "start": o["start"], "end": o["end"], "note": o["note"]}
            for o in overrides
        ],
        "gaps": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in hard_gaps],
        "soft_gaps": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in soft_gaps],
        "status": status,
        "instructions": INSTRUCTIONS.get(account["type"], ""),
    }


def _has_contract_note(reference: str, filenames: list[str]) -> bool:
    """Whether one of the account's documents is `<reference>_*.pdf`, the naming
    the parser matches contract notes by (case-insensitively)."""
    start = f"{reference.lower()}_"
    return any(n.lower().startswith(start) and n.lower().endswith(".pdf") for n in filenames)


def refresh_hl_warnings(docs: list[dict]) -> None:
    """Rewrite each document's missing-contract-note warning against the notes
    the account holds now. The warning is written when the Transaction Summary
    is validated, and the notes are normally uploaded after it, so without this
    it would name references that are no longer missing — and never clear."""
    filenames = [d["filename"] for d in docs]
    for doc in docs:
        refreshed = []
        for warning in doc["warnings"]:
            if not warning.startswith(HL_MISSING_NOTES_PREFIX):
                refreshed.append(warning)
                continue
            listed = warning[len(HL_MISSING_NOTES_PREFIX) :].split(" — ")[0]
            missing = [
                ref
                for ref in (part.strip() for part in listed.split(","))
                if ref and not _has_contract_note(ref, filenames)
            ]
            if missing:
                refreshed.append(
                    HL_MISSING_NOTES_PREFIX + ", ".join(missing) + HL_MISSING_NOTES_SUFFIX
                )
        doc["warnings"] = refreshed


def _awards_related(warning: str) -> bool:
    lowered = warning.lower()
    return any(marker in lowered for marker in _AWARDS_WARNING_MARKERS)


def checklist(user_id: int, tax_year: int) -> dict:
    accounts = repo.list_accounts(user_id)
    items = [
        account_coverage(
            a,
            repo.list_documents(user_id, a["id"]),
            tax_year,
            repo.list_coverage_overrides(user_id, a["id"]),
        )
        for a in accounts
    ]

    for item in items:
        if item["account"]["type"] == "hl_fund_share":
            refresh_hl_warnings(item["documents"])

    # Cross-account dependency: Schwab Individual vest rows need the Equity Awards export.
    has_awards_docs = any(i["account"]["type"] == "schwab_awards" and i["documents"] for i in items)
    needs: list[dict] = []
    for i in items:
        if i["account"]["type"] != "schwab_individual":
            continue
        vest_warnings = [w for d in i["documents"] for w in d["warnings"] if _awards_related(w)]
        if not vest_warnings:
            continue
        if has_awards_docs:
            # The awards document is present — those warnings are stale for display.
            for d in i["documents"]:
                d["warnings"] = [w for w in d["warnings"] if not _awards_related(w)]
        else:
            needs.append(
                {
                    "type": "schwab_awards",
                    "because": (
                        f"Your '{i['account']['name']}' export has RSU vest rows (Stock Plan "
                        "Activity) whose prices come from the Equity Awards export."
                    ),
                    "instructions": INSTRUCTIONS["schwab_awards"],
                }
            )
            break

    overall = "ok"
    if not items:
        overall = "no_accounts"
    elif any(i["status"] == "missing" for i in items):
        overall = "missing"
    elif any(i["status"] == "gaps" for i in items) or needs:
        overall = "gaps"
    return {
        "tax_year": tax_year,
        "label": tax_years.label(tax_year),
        "year_start": tax_years.tax_year_start(tax_year).isoformat(),
        "year_end": tax_years.tax_year_end(tax_year).isoformat(),
        "filing_deadline": tax_years.filing_deadline(tax_year).isoformat(),
        "accounts": items,
        "needs": needs,
        "overall": overall,
    }
