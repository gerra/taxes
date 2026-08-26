"""Turn raw cgt-calc / engine warning strings into structured, human notices.

Each notice: {kind: info|warning|error, category, title, summary,
occurrences: [str], why, action, count, raw: [str]}. Text fields may contain
[[value]] tokens — the UI renders those as highlighted pills.

Unknown messages fall through as a generic warning with the raw text, so
nothing the engine says is ever hidden."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

_DISCREPANCY = re.compile(
    r"Amount discrepancy for \w+\(date=datetime\.date\((\d+), (\d+), (\d+)\)"
    r".*?action=<ActionType\.(\w+)"
    r".*?symbol='([^']*)'"
    r".*?quantity=Decimal\('([^']*)'\)"
    r".*?price=Decimal\('([^']*)'\)"
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
    y, mo, d, action, symbol, qty, price, ccy, broker, supplied, calculated = m.groups()
    verb = "sale" if action == "SELL" else action.lower()
    return {
        "kind": "warning",
        "category": "amount_adjusted",
        "title": f"{symbol} {verb} on [[{_fmt_date(y, mo, d)}]] — proceeds adjusted",
        "summary": (
            f"{broker} reported [[{_money(supplied, ccy)}]] for [[{_num(qty)}]] shares at "
            f"[[{_money(price, ccy, 3)}]], which doesn't add up. The full value "
            f"[[{_money(calculated, ccy)}]] is used for CGT."
        ),
        "occurrences": [],
        "why": (
            "This is usually a sell-to-cover: the broker sold shares to pay tax and only "
            "reported the cash you kept. HMRC treats every share sold as disposed, so the "
            "gain is computed on the full quantity × price."
        ),
        "action": "Check the Schwab statement for that date confirms shares were withheld for tax.",
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
