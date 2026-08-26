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
