"""Document-coverage computation: what date ranges each account's documents
cover vs what a tax year's calculation needs (full history from first activity —
the Section 104 pool replays everything)."""

from datetime import date, timedelta

from core import repo, tax_years

# Static export instructions shown next to gaps, per account type.
INSTRUCTIONS = {
    "schwab_individual": (
        "schwab.com → Accounts → Transaction history → select period (max ~4 years "
        "per export) → Search → Download as .csv. Export multiple chunks to cover "
        "your full history; overlaps are fine."
    ),
    "schwab_awards": (
        "Same flow, on the Equity Award account: schwab.com → Accounts → Transaction "
        "history → select the equity award account and period → Search → Download as "
        ".csv. Needed for the fair-market-value prices of your vested awards."
    ),
    "freetrade_gia": (
        "Use the Freetrade APP, not the website: GIA → Activity → Share button (top "
        "right) → export CSV. The app exports from 2020; the website only covers the "
        "last 12 months."
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


def account_coverage(account: dict, docs: list[dict], tax_year: int) -> dict:
    year_end = tax_years.tax_year_end(tax_year)
    required_end = min(date.today(), year_end)

    doc_ranges = [
        (date.fromisoformat(d["date_min"]), date.fromisoformat(d["date_max"]))
        for d in docs
        if d["date_min"] and d["date_max"]
    ]
    covered = _merge_ranges(doc_ranges)

    if account["type"] in _TAX_YEAR_ONLY_TYPES:
        required_start = tax_years.tax_year_start(tax_year)
    elif account["first_activity_date"]:
        required_start = date.fromisoformat(account["first_activity_date"])
    elif covered:
        required_start = covered[0][0]  # best guess: earliest seen transaction
    else:
        required_start = tax_years.tax_year_start(tax_year)

    gaps = _gaps((required_start, required_end), covered) if required_start <= required_end else []
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
        "covered": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in covered],
        "gaps": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in hard_gaps],
        "soft_gaps": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in soft_gaps],
        "status": status,
        "instructions": INSTRUCTIONS.get(account["type"], ""),
    }


def checklist(user_id: int, tax_year: int) -> dict:
    accounts = repo.list_accounts(user_id)
    items = [account_coverage(a, repo.list_documents(user_id, a["id"]), tax_year) for a in accounts]
    overall = "ok"
    if not items:
        overall = "no_accounts"
    elif any(i["status"] == "missing" for i in items):
        overall = "missing"
    elif any(i["status"] == "gaps" for i in items):
        overall = "gaps"
    return {
        "tax_year": tax_year,
        "label": tax_years.label(tax_year),
        "year_start": tax_years.tax_year_start(tax_year).isoformat(),
        "year_end": tax_years.tax_year_end(tax_year).isoformat(),
        "filing_deadline": tax_years.filing_deadline(tax_year).isoformat(),
        "accounts": items,
        "overall": overall,
    }
