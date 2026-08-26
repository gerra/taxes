"""Turn raw cgt-calc / engine warning strings into structured, human notices.

Each notice: {kind: info|warning|error, category, title, summary,
occurrences: [str], why, action, count, raw: [str]}. Text fields may contain
[[value]] tokens — the UI renders those as highlighted pills.

Unknown messages fall through as a generic warning with the raw text, so
nothing the engine says is ever hidden."""

import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation

_DISCREPANCY = re.compile(
    r"Amount discrepancy for \w+\(date=datetime\.date\((\d+), (\d+), (\d+)\)"
    r".*?action=<ActionType\.(\w+)"
    r".*?symbol='([^']*)'"
    r".*?quantity=Decimal\('([^']*)'\)"
    r".*?price=Decimal\('([^']*)'\)"
    r".*?fees=Decimal\('([^']*)'\)"
    r".*?currency='([^']*)'"
    r".*?broker='([^']*)'"
    r".*?supplied=(-?\d+(?:\.\d+)?), calculated=(-?\d+(?:\.\d+)?)"
)
_BNB = re.compile(
    r"Bed and breakfasting for ([A-Za-z0-9.\-]+?)\. Disposed on (\d{4}-\d{2}-\d{2}) "
    r"and acquired again on (\d{4}-\d{2}-\d{2})"
)
_TREATY = re.compile(
    r"double taxation treaty does not match .*?\(expected (-?[\d.]+) base tax for (\w+) "
    r"but (-?[\d.]+) was deducted\) for (\S+) ticker"
)

_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}
_COUNTRY_CCY = {"USA": "USD", "UK": "GBP"}


def _fmt_date(y: str, m: str, d: str) -> str:
    return date(int(y), int(m), int(d)).strftime("%-d %b %Y")


def _fmt_iso(s: str) -> str:
    return date.fromisoformat(s).strftime("%-d %b %Y")


def _money(value: str | Decimal, currency: str, decimals: int = 2) -> str:
    try:
        amount = abs(Decimal(str(value)))
    except InvalidOperation:
        return f"{value} {currency}"
    text = f"{amount:,.{decimals}f}"
    sym = _SYMBOLS.get(currency)
    return f"{sym}{text}" if sym else f"{text} {currency}"


def _num(value: str) -> str:
    try:
        d = Decimal(value)
    except InvalidOperation:
        return value
    return f"{d.normalize():f}"


def _discrepancy(m: re.Match, raw: str) -> dict:
    y, mo, d, action, symbol, qty, price, fees, ccy, broker, supplied, calculated = m.groups()
    verb = "sale" if action == "SELL" else action.lower()
    missing = Decimal(calculated) - Decimal(supplied)
    ratio = (missing / Decimal(calculated)) if Decimal(calculated) else Decimal(0)
    backup_withholding = abs(ratio - Decimal("0.24")) < Decimal("0.003")

    summary = (
        f"{broker} reported [[{_money(supplied, ccy)}]] for [[{_num(qty)}]] shares at "
        f"[[{_money(price, ccy, 3)}]] — that's [[{_money(missing, ccy)}]] less than the "
        f"shares were worth. The full value [[{_money(calculated, ccy)}]] is used for CGT, "
        "as HMRC requires."
    )
    if backup_withholding:
        summary += (
            " The missing amount is exactly [[24%]] of the proceeds — the US "
            "backup-withholding rate, which brokers apply when they have no valid "
            "W-8BEN on file."
        )
        why = (
            "A UK resident with a valid W-8BEN should have NO US tax withheld on share "
            "sales. Backup withholding kicks in when the form is missing or expired "
            "(W-8BENs last 3 calendar years). It is not a cost of the disposal — your CGT "
            "proceeds are still the full amount — and it's usually reclaimable: from the "
            "broker if caught in the same US tax year, otherwise from the IRS by filing "
            "Form 1040-NR with the 1042-S/1099 that reports the withholding."
        )
        action = (
            "Check your W-8BEN status with the broker (Schwab: Profile → Tax forms), then "
            "ask them how to reclaim the withheld amount. Keep the trade-details PDF as evidence."
        )
    else:
        why = (
            "The broker deducted something from the proceeds before reporting them — "
            "commonly tax withheld (sell-to-cover at an RSU vest, or US withholding) or a "
            "fee not in the fees column. HMRC treats every share sold as disposed at its "
            "full price, so the gain is computed on quantity × price minus dealing fees only."
        )
        action = (
            "Open the trade details on the broker's site and check what was deducted; "
            "confirm it below with the withholding figure and the PDF."
        )
    return {
        "key": f"amount_adjusted__{symbol}__{int(y):04d}-{int(mo):02d}-{int(d):02d}",
        "data": {
            "supplied": supplied,
            "calculated": calculated,
            "currency": ccy,
            "quantity": qty,
            "price": price,
            "fees": fees,
        },
        "kind": "warning",
        "category": "amount_adjusted",
        "title": f"{symbol} {verb} on [[{_fmt_date(y, mo, d)}]] — tax withheld from proceeds"
        if backup_withholding
        else f"{symbol} {verb} on [[{_fmt_date(y, mo, d)}]] — proceeds adjusted",
        "summary": summary,
        "occurrences": [],
        "why": why,
        "action": action,
        "count": 1,
        "raw": [raw],
    }


def build_notices(warnings: list[str]) -> list[dict]:
    notices: list[dict] = []
    bnb: dict[str, dict] = {}
    treaty: dict[str, dict] = {}

    for raw in warnings:
        text = raw.strip()
        if not text:
            continue

        m = _DISCREPANCY.search(text)
        if m:
            notices.append(_discrepancy(m, text))
            continue

        m = _BNB.search(text)
        if m:
            symbol, sold, rebought = m.groups()
            group = bnb.setdefault(
                symbol,
                {
                    "key": f"bed_and_breakfast__{symbol}",
                    "kind": "info",
                    "category": "bed_and_breakfast",
                    "title": f"30-day rule applied to [[{symbol}]]",
                    "summary": (
                        "Shares sold and bought back within 30 days are matched to the "
                        "repurchase cost instead of the pool. Already reflected in the gains."
                    ),
                    "occurrences": [],
                    "why": (
                        "HMRC's bed-and-breakfast rule stops you resetting your cost base by "
                        "selling and immediately rebuying. It's a rule being applied, not a "
                        "problem with your data."
                    ),
                    "action": None,
                    "count": 0,
                    "raw": [],
                },
            )
            group["occurrences"].append(
                f"Sold [[{_fmt_iso(sold)}]], bought again [[{_fmt_iso(rebought)}]]"
            )
            group["count"] += 1
            group["raw"].append(text)
            continue

        m = _TREATY.search(text)
        if m:
            expected, country, deducted, symbol = m.groups()
            ccy = _COUNTRY_CCY.get(country, "")
            group = treaty.setdefault(
                symbol,
                {
                    "key": f"withholding__{symbol}",
                    "kind": "warning",
                    "category": "withholding",
                    "title": f"[[{symbol}]] dividends taxed above the treaty rate",
                    "summary": "",
                    "occurrences": [],
                    "why": (
                        "Only withholding at the UK–US treaty rate (15%) can be credited against "
                        "UK tax. Anything withheld above that is simply lost."
                    ),
                    "action": (
                        "Check your W-8BEN with the broker — it expires every 3 years, and "
                        "without a valid one US withholding defaults to 30%."
                    ),
                    "count": 0,
                    "raw": [],
                    "_expected": Decimal(0),
                    "_deducted": Decimal(0),
                    "_ccy": ccy,
                },
            )
            exp, ded = abs(Decimal(expected)), abs(Decimal(deducted))
            group["_expected"] += exp
            group["_deducted"] += ded
            group["occurrences"].append(
                f"Withheld [[{_money(ded, ccy)}]], treaty rate would be [[{_money(exp, ccy)}]]"
            )
            group["count"] += 1
            group["raw"].append(text)
            continue

        lowered = text.lower()
        if "balance" in lowered and "reconcile" in lowered:
            notices.append(
                {
                    "key": "balance",
                    "kind": "warning",
                    "category": "balance",
                    "title": "Cash balance didn't reconcile",
                    "summary": (
                        "Some deposits or withdrawals are missing from your documents, so the "
                        "cash running total doesn't add up. Gains, dividends and interest are "
                        "still correct as long as every trade and payment row is present."
                    ),
                    "occurrences": [],
                    "why": (
                        "Broker exports with a limited date range often omit early top-ups; "
                        "the calculation ran without the balance check."
                    ),
                    "action": "If you can, upload an export reaching back to the account's first deposit.",
                    "count": 1,
                    "raw": [text],
                }
            )
            continue

        if lowered.startswith("pdf not rendered"):
            kind, title = "info", "Computation PDF wasn't generated"
        elif "missing allowance" in lowered or "no tax constants" in lowered:
            kind, title = "warning", "Tax-year allowances not configured"
        else:
            kind, title = "warning", text[:90] + ("…" if len(text) > 90 else "")
        notices.append(
            {
                "key": "other__" + hashlib.sha1(text.encode()).hexdigest()[:10],
                "kind": kind,
                "category": "other",
                "title": title,
                "summary": text,
                "occurrences": [],
                "why": None,
                "action": None,
                "count": 1,
                "raw": [text],
            }
        )

    for group in treaty.values():
        exp, ded, ccy = group.pop("_expected"), group.pop("_deducted"), group.pop("_ccy")
        actual_rate = (Decimal(15) * ded / exp) if exp else Decimal(0)
        n = group["count"]
        group["summary"] = (
            f"On [[{n}]] dividend{'s' if n != 1 else ''} the broker withheld about "
            f"[[{actual_rate:.0f}%]] instead of the treaty [[15%]] — roughly "
            f"[[{_money(ded - exp, ccy)}]] more tax than necessary, which can't be reclaimed "
            "through the UK return."
        )
        notices.append(group)
    notices.extend(bnb.values())

    order = {"error": 0, "warning": 1, "info": 2}
    notices.sort(key=lambda n: order[n["kind"]])
    return notices


_KIND_ORDER = {"error": 0, "warning": 1, "info": 2}

# What the user must gather and enter to verify each notice type. The UI renders
# these as a guided form; `checks` in apply_resolutions() grade the answers.
VERIFICATION: dict[str, dict] = {
    "amount_adjusted": {
        "intro": "Verify the sale against the broker's own trade record.",
        "docs": [
            {
                "title": "Trade transaction details for this sale",
                "where": "Schwab → Accounts → History → click the transaction → Print / save as PDF",
            }
        ],
        "fields": [
            {
                "key": "principal",
                "label": "Principal (gross value on the trade details)",
                "type": "money",
                "required": True,
            },
            {
                "key": "withholding",
                "label": "Withholding taxes on the trade details",
                "type": "money",
                "required": True,
            },
            {
                "key": "reason",
                "label": "What is this withholding?",
                "type": "choice",
                "required": True,
                "options": [
                    {"value": "backup", "label": "US backup withholding — no valid W-8BEN on file"},
                    {
                        "value": "sell_to_cover",
                        "label": "Sell-to-cover at an RSU vest (tax via payroll)",
                    },
                    {"value": "other", "label": "Something else — explain in the note"},
                ],
            },
            {
                "key": "refunded",
                "label": "Amount refunded later, if any",
                "type": "money",
                "required": False,
            },
        ],
    },
    "withholding": {
        "intro": "Establish why more than the treaty 15% was withheld.",
        "docs": [
            {"title": "W-8BEN status and expiry", "where": "Schwab → Profile → Tax forms"},
            {
                "title": "Form 1042-S for the tax year",
                "where": "Schwab → Accounts → Statements & Tax forms → Tax forms",
            },
        ],
        "fields": [
            {
                "key": "w8ben_status",
                "label": "W-8BEN status",
                "type": "choice",
                "required": True,
                "options": [
                    {"value": "valid", "label": "Valid — in date"},
                    {"value": "expired", "label": "Expired or missing"},
                    {"value": "renewed", "label": "Renewed since"},
                ],
            },
            {
                "key": "w8ben_date",
                "label": "W-8BEN expiry or renewal date",
                "type": "date",
                "required": False,
            },
        ],
    },
    "balance": {
        "intro": "Confirm nothing that affects gains or income is missing.",
        "docs": [
            {
                "title": "Export reaching back to the account's first deposit",
                "where": "Same broker export flow, widest date range available",
            }
        ],
        "fields": [
            {
                "key": "all_rows_present",
                "label": "I've checked every buy, sell, dividend and interest row is present",
                "type": "checkbox",
                "required": True,
            }
        ],
    },
    "other": {"intro": "Record what you checked.", "docs": [], "fields": []},
}


def verification_for(category: str) -> dict:
    return VERIFICATION.get(category, VERIFICATION["other"])


def _dec(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except InvalidOperation:
        return None


def _checks_amount_adjusted(n: dict, data: dict) -> list[dict]:
    d = n["data"]
    ccy = d["currency"]
    calc, supplied = Decimal(d["calculated"]), Decimal(d["supplied"])
    qty, price, fees = (
        _dec(d.get("quantity")),
        _dec(d.get("price")),
        _dec(d.get("fees")) or Decimal(0),
    )
    checks = []

    principal = _dec(data.get("principal"))
    if principal is None:
        checks.append({"label": "Principal matches quantity × price", "status": "pending"})
    elif qty is not None and price is not None:
        expected = qty * price
        ok = abs(principal - expected) < Decimal("0.05")
        checks.append(
            {
                "label": "Principal matches quantity × price",
                "status": "ok" if ok else "fail",
                "detail": f"{_num(str(qty))} × {_money(price, ccy, 3)} = {_money(expected, ccy)}"
                + ("" if ok else f", but trade details say {_money(principal, ccy)}"),
            }
        )

    withholding = _dec(data.get("withholding"))
    if withholding is None:
        checks.append({"label": "Withholding explains the missing amount", "status": "pending"})
    else:
        diff = abs(calc - withholding - supplied)
        ok = diff < Decimal("0.05")
        checks.append(
            {
                "label": "Withholding explains the missing amount",
                "status": "ok" if ok else "fail",
                "detail": f"{_money(calc, ccy)} (after {_money(fees, ccy)} fees) − {_money(withholding, ccy)} "
                f"= {_money(calc - withholding, ccy)}"
                + (
                    " — matches the broker's total"
                    if ok
                    else f" — broker total was {_money(supplied, ccy)} (off by {_money(diff, ccy)})"
                ),
            }
        )

    reason = data.get("reason")
    if reason == "backup":
        checks.append(
            {
                "label": "Tax treatment",
                "status": "info",
                "detail": "US backup withholding is not a UK deduction — CGT proceeds stay at the "
                "full amount. Reclaim it from the IRS (Form 1040-NR with the 1042-S/1099-B). "
                "Renew the W-8BEN to stop it recurring.",
            }
        )
    elif reason == "sell_to_cover":
        checks.append(
            {
                "label": "Tax treatment",
                "status": "info",
                "detail": "Sell-to-cover tax is income tax on the vest, collected via payroll — "
                "already on your P60. Nothing extra on the UK return; CGT proceeds stay at the "
                "full amount.",
            }
        )
    elif reason == "other":
        checks.append(
            {
                "label": "Tax treatment",
                "status": "warn",
                "detail": "Unexplained deduction — see note.",
            }
        )
    else:
        checks.append({"label": "Tax treatment", "status": "pending"})

    refunded = _dec(data.get("refunded"))
    if refunded:
        checks.append(
            {
                "label": "Refund",
                "status": "info",
                "detail": f"{_money(refunded, ccy)} refunded later — no effect on the UK CGT figures.",
            }
        )
    return checks


def _checks_withholding(n: dict, data: dict) -> list[dict]:
    status = data.get("w8ben_status")
    when = data.get("w8ben_date")
    when_txt = f" ({_fmt_iso(when)})" if when else ""
    if status == "valid":
        return [
            {
                "label": "W-8BEN",
                "status": "warn",
                "detail": f"Valid{when_txt}, yet 30% was withheld — ask the broker to correct their "
                "records and refund the excess; it can't be reclaimed through the UK return.",
            }
        ]
    if status == "expired":
        return [
            {
                "label": "W-8BEN",
                "status": "fail",
                "detail": f"Expired or missing{when_txt} — renew it with the broker now. The extra 15% "
                "already withheld is reclaimable only from the IRS (Form 1040-NR).",
            }
        ]
    if status == "renewed":
        return [
            {
                "label": "W-8BEN",
                "status": "ok",
                "detail": f"Renewed{when_txt} — future dividends should be withheld at 15%. Check the "
                "next dividend to confirm.",
            }
        ]
    return [{"label": "W-8BEN", "status": "pending"}]


def _checks_balance(n: dict, data: dict) -> list[dict]:
    if data.get("all_rows_present") in ("true", True, "1", "on"):
        return [
            {
                "label": "Transactions complete",
                "status": "ok",
                "detail": "Missing deposits/withdrawals don't affect gains, dividends or interest.",
            }
        ]
    return [{"label": "Transactions complete", "status": "pending"}]


def _required_missing(n: dict, data: dict) -> list[str]:
    spec = verification_for(n["category"])
    missing = []
    for f in spec["fields"]:
        if f.get("required") and not data.get(f["key"]):
            missing.append(f["label"])
    return missing


def apply_resolutions(notices: list[dict], resolutions: dict[str, dict]) -> list[dict]:
    """Attach the user's verification answers to each notice, grade them, and
    sort verified notices last. resolution.status: verified | mismatch | partial."""
    graders = {
        "amount_adjusted": _checks_amount_adjusted,
        "withholding": _checks_withholding,
        "balance": _checks_balance,
    }
    for n in notices:
        n["verification"] = verification_for(n["category"])
        r = resolutions.get(n["key"])
        if not r:
            n["resolution"] = None
            continue
        data = r["data"] or {}
        checks = graders.get(n["category"], lambda _n, _d: [])(n, data)
        statuses = [c["status"] for c in checks]
        missing = _required_missing(n, data)
        if "fail" in statuses:
            status = "mismatch"
        elif missing or "pending" in statuses:
            status = "partial"
        else:
            status = "verified"
        arithmetic = next((c for c in checks if c["label"].startswith("Withholding")), None)
        n["resolution"] = {
            "note": r["note"],
            "data": data,
            "evidence_name": r["evidence_name"],
            "created_at": r["created_at"],
            "status": status,
            "checks": checks,
            "missing": missing,
            # kept for older callers
            "verified": None
            if not arithmetic or arithmetic["status"] == "pending"
            else arithmetic["status"] == "ok",
            "check": arithmetic.get("detail") if arithmetic else None,
        }
    notices.sort(
        key=lambda n: (
            1 if (n.get("resolution") or {}).get("status") == "verified" else 0,
            _KIND_ORDER[n["kind"]],
        )
    )
    return notices
