"""Turn raw cgt-calc / engine warning strings into structured, human notices.

Each notice: {kind: info|warning|error, category, title, summary,
occurrences: [str], why, action, count, raw: [str], tax_year: int|None}.
Text fields may contain [[value]] tokens — the UI renders those as highlighted
pills.

The engine replays the whole transaction history for every run (Section 104
pools need it), so per-transaction warnings arrive for every year, not just
the one being reported. `tax_year` is the year a dated notice belongs to; the
UI hides other years' notices by default. None means the notice is about the
run as a whole (balance check, allowances, treaty checks — which the engine
already limits to the reported year).

Unknown messages fall through as a generic warning with the raw text, so
nothing the engine says is ever hidden."""

import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from core import tax_years

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

# Engine lines that a structured notice already covers in full.
_TBILL_ENGINE = re.compile(r"carry no Treasury bill maturities", re.IGNORECASE)
_GB_TREATY = re.compile(r"Taxation treaty for GB country is missing \(ticker: (\S+)\)")

# Any date the engine tends to print: an ISO date or a repr'd datetime.date.
_ANY_DATE = re.compile(
    r"datetime\.date\((\d{4}), (\d{1,2}), (\d{1,2})\)|\b(\d{4})-(\d{2})-(\d{2})\b"
)

_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}
_COUNTRY_CCY = {"USA": "USD", "UK": "GBP"}


def _fmt_date(y: str, m: str, d: str) -> str:
    return date(int(y), int(m), int(d)).strftime("%-d %b %Y")


def _tax_year_in(text: str) -> int | None:
    """Tax year of the first date mentioned in an engine message, if any."""
    m = _ANY_DATE.search(text)
    if not m:
        return None
    parts = [p for p in m.groups() if p is not None]
    try:
        return tax_years.tax_year_of(date(int(parts[0]), int(parts[1]), int(parts[2])))
    except ValueError:
        return None


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


def _find_refund(refunds: list[dict] | None, symbol: str, sale_date: str) -> dict | None:
    for r in refunds or []:
        if r.get("symbol") == symbol and r.get("sale_date") == sale_date:
            return r
    return None


def _discrepancy(m: re.Match, raw: str, refunds: list[dict] | None = None) -> dict:
    y, mo, d, action, symbol, qty, price, fees, ccy, broker, supplied, calculated = m.groups()
    sale_iso = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    refund = _find_refund(refunds, symbol, sale_iso)
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
    if refund:
        summary += (
            f" {broker} refunded [[{_money(refund['amount'], ccy)}]] on "
            f"[[{_fmt_iso(refund['refund_date'])}]] ({refund['days']} days later) — "
            "nothing to reclaim."
        )
        why = (
            "Backup withholding was applied at the sale (no valid W-8BEN on file at the "
            "time) and reversed by the broker within the same US tax year, which is the "
            "route the rules allow. The refund is a cash adjustment only — it doesn't "
            "change the CGT proceeds, which remain the full sale value."
        )
        action = None
    return {
        "key": f"amount_adjusted__{symbol}__{sale_iso}",
        "tax_year": tax_years.tax_year_of(date.fromisoformat(sale_iso)),
        "data": {
            "supplied": supplied,
            "calculated": calculated,
            "currency": ccy,
            "quantity": qty,
            "price": price,
            "fees": fees,
        },
        "kind": "info" if refund else "warning",
        "category": "amount_adjusted",
        "title": (
            f"{symbol} {verb} on [[{_fmt_date(y, mo, d)}]] — tax withheld, then refunded"
            if refund
            else f"{symbol} {verb} on [[{_fmt_date(y, mo, d)}]] — tax withheld from proceeds"
            if backup_withholding
            else f"{symbol} {verb} on [[{_fmt_date(y, mo, d)}]] — proceeds adjusted"
        ),
        "summary": summary,
        "occurrences": [],
        "why": why,
        "action": action,
        "count": 1,
        "raw": [raw],
    }


def _exempt_notices(exempt: dict | None, tax_year: int | None) -> list[dict]:
    """What the engine did with gilts and T-bills, and the Accrued Income Scheme
    flag. `exempt` is bundle["exempt"] from the worker."""
    if not exempt or not exempt.get("securities"):
        return []
    out: list[dict] = []
    securities = exempt["securities"]
    kinds = {"gilt": "gilt", "tbill": "UK Treasury bill", "manual": "marked by you"}
    out.append(
        {
            "key": "exempt_securities",
            "tax_year": None,
            "kind": "info",
            "category": "exempt",
            "title": "Gilts and T-bills treated as exempt from capital gains tax",
            "summary": (
                "Disposals of these securities are listed in the report but left out of "
                "the SA108 figures — gains on them are not chargeable and losses are not "
                "allowable (TCGA 1992 s115)."
            ),
            "occurrences": [
                f"[[{s['symbol']}]] — {s.get('title') or kinds.get(s['kind'], s['kind'])}"
                + (f" ({s['isin']})" if s.get("isin") else "")
                + (" — recognised by name" if s["source"] == "detected" else "")
                for s in securities
            ],
            "why": (
                "Gilt-edged securities and UK Treasury bills are exempt assets. The tool "
                "recognises them by their name and GB ISIN in the broker export; anything it "
                "cannot see can be added by ticker or ISIN under Documents → CGT-exempt "
                "securities. Interest on gilts is still taxable as interest."
            ),
            "action": (
                "A T-bill's return is the discount at maturity, taxed as income (deeply "
                "discounted securities), not a gain — brokers rarely export the maturity, "
                "so check your statements for it."
                if any(s["kind"] == "tbill" for s in securities)
                else None
            ),
            "count": len(securities),
            "raw": [],
        }
    )
    if exempt.get("ais_applies"):
        limit = Decimal(exempt.get("ais_limit") or "5000")
        peak = Decimal(exempt.get("ais_nominal_peak") or "0")
        lines = []
        for a in exempt.get("accrued_interest", []):
            if tax_years.tax_year_of(date.fromisoformat(a["date"])) != tax_year:
                continue
            verb = "paid on the purchase" if a["side"] == "purchase" else "received on the sale"
            lines.append(
                f"[[{_money(a['amount'], a['currency'])}]] accrued interest {verb} of "
                f"[[{a['symbol']}]] on [[{_fmt_iso(a['date'])}]]"
            )
        out.append(
            {
                "key": "accrued_income_scheme",
                "tax_year": tax_year,
                "kind": "warning",
                "category": "accrued_income",
                "title": "Accrued Income Scheme may apply to your gilt trades",
                "summary": (
                    f"You held up to [[£{peak:,.2f}]] nominal of gilts this year, over the "
                    f"[[£{limit:,.0f}]] limit, so interest accrued at the time of each purchase "
                    "and sale is taxed as income rather than being ignored. Not computed here."
                ),
                "occurrences": lines,
                "why": (
                    "A gilt trades at a dirty price: the cash paid or received includes the "
                    "coupon accrued since the last payment date. Accrued interest paid on a "
                    "purchase is relief; accrued interest received on a sale is a charge — "
                    "both taxed as interest in the year of the next interest payment date "
                    "(ITA 2007 Part 12; HS343)."
                ),
                "action": (
                    "Add the net accrued interest (received minus paid) to your untaxed UK "
                    "interest for the year of the next coupon date, or deduct it if net paid. "
                    "The amounts above are the engine's estimates from the dirty price."
                ),
                "count": len(lines),
                "raw": [],
            }
        )
    return out


def _tbill_notices(exempt: dict | None, tax_year: int | None) -> list[dict]:
    """T-bill returns are income the broker export never shows."""
    tbills = [t for t in (exempt or {}).get("tbills", []) if t.get("in_year")]
    if not tbills:
        return []
    total = sum(Decimal(t["profit"]) for t in tbills if t.get("profit") is not None)
    lines = []
    for t in tbills:
        when = _fmt_iso(t["event_date"]) if t.get("event_date") else "unknown date"
        verb = "sold" if t["status"] == "sold" else "matured"
        lines.append(
            f"[[{t['symbol']}]] {t.get('title') or ''}: £{Decimal(t['nominal']):,.2f} nominal "
            f"for £{Decimal(t['cost']):,.2f}, {verb} [[{when}]] → [[£{Decimal(t['profit']):,.2f}]]"
        )
    return [
        {
            "key": "tbill_returns",
            "tax_year": tax_year,
            "kind": "warning",
            "category": "tbill_returns",
            "title": "T-bill returns are income your export doesn't show",
            "summary": (
                f"[[{len(tbills)}]] UK Treasury bill{'s' if len(tbills) != 1 else ''} "
                f"matured or were sold this year, earning about [[£{total:,.2f}]] — taxable as "
                "income (deeply discounted securities), not a capital gain, and absent from "
                "the Freetrade export."
            ),
            "occurrences": lines,
            "why": (
                "A T-bill is bought below £1 per unit and redeemed at £1 on the date in its "
                "name. Brokers export the purchase but not the redemption, so the tool "
                "reconstructs the return from the purchase and the maturity date; a bill sold "
                "early uses its sale proceeds instead."
            ),
            "action": (
                "Check the figures against your Freetrade statements — the date in a bill's "
                "name can run a few days after the real redemption, so a bill maturing around "
                "5 April may belong to the other tax year. Then enter the total in the SA101 "
                "Additional information pages, 'deeply discounted securities' gross amount box "
                "(the report's SA101 row); verify the box on the SA101 notes."
            ),
            "count": len(tbills),
            "raw": [],
        }
    ]


def _data_notices(bundle: dict | None, tax_year: int | None) -> list[dict]:
    """Gaps and mislabels visible in the bundle itself."""
    if not bundle:
        return []
    out: list[dict] = []
    offshore = bundle.get("offshore_funds_without_eri") or []
    if offshore:
        out.append(
            {
                "key": "offshore_eri_missing",
                "tax_year": tax_year,
                "kind": "warning",
                "category": "eri_missing",
                "title": "Offshore funds held with no excess reported income data",
                "summary": (
                    f"[[{len(offshore)}]] holding{'s' if len(offshore) != 1 else ''} "
                    "registered offshore had no excess-reported-income entry this year, so "
                    "any ERI they reported is missing from the dividend/interest figures."
                ),
                "occurrences": [f"[[{f['symbol']}]] ({f['isin']})" for f in offshore],
                "why": (
                    "Irish-, Luxembourg- and Jersey-domiciled ETFs are offshore reporting "
                    "funds: income they report but do not distribute is taxable on you six "
                    "months after their period end (HS265). The engine only knows the ERI "
                    "figures bundled with it, so a fund with none may simply be missing data — "
                    "or be a physical ETC with nothing to report."
                ),
                "action": (
                    "Look up each fund's 'excess reportable income per unit' for the period in "
                    "its reporting-fund statement (the KPMG/fund reporting pages) and add it to "
                    "the foreign dividend or interest figure by hand — the tool cannot take an "
                    "ERI file yet."
                ),
                "count": len(offshore),
                "raw": [],
            }
        )
    pids: dict[str, dict] = {}
    for d in bundle.get("dividends", []):
        tax = Decimal(d.get("tax_at_source_gbp") or 0)
        if d.get("country") == "GB" and tax != 0:
            year = tax_years.tax_year_of(date.fromisoformat(d["date"]))
            if tax_year is not None and year != tax_year:
                continue
            g = pids.setdefault(
                d["symbol"],
                {
                    "key": f"pid_as_dividend__{d['symbol']}",
                    "tax_year": year,
                    "kind": "warning",
                    "category": "pid_as_dividend",
                    "title": f"[[{d['symbol']}]] withheld tax on a UK 'dividend' — a REIT PID",
                    "summary": "",
                    "occurrences": [],
                    "why": (
                        "UK dividends are paid without withholding. A UK payer taking 20% off "
                        "is a REIT paying a property income distribution, which the export "
                        "labelled as a dividend (Freetrade only started typing these PROPERTY "
                        "in 2025)."
                    ),
                    "action": (
                        "Strictly this belongs in 'Other UK income' box 17 (gross) with the tax "
                        "in box 19, not the dividend boxes; the tool has counted it as a UK "
                        "dividend with the withholding shown. Move it by hand if you prefer the "
                        "strict treatment."
                    ),
                    "count": 0,
                    "raw": [],
                    "_gross": Decimal(0),
                    "_tax": Decimal(0),
                },
            )
            g["_gross"] += Decimal(d["amount_gbp"])
            g["_tax"] += abs(tax)
            g["occurrences"].append(
                f"[[{_fmt_iso(d['date'])}]]: £{Decimal(d['amount_gbp']):,.2f} gross, "
                f"[[£{abs(tax):,.2f}]] withheld"
            )
            g["count"] += 1
    for g in pids.values():
        gross, tax = g.pop("_gross"), g.pop("_tax")
        g["summary"] = (
            f"£{gross:,.2f} of distributions with [[£{tax:,.2f}]] tax taken off, counted in "
            "the UK dividends figure."
        )
        out.append(g)
    foreign_tax = [
        r for r in bundle.get("interest_tax") or [] if r.get("currency") and r["currency"] != "GBP"
    ]
    if foreign_tax:
        total = sum(Decimal(r["amount_gbp"]) for r in foreign_tax)
        out.append(
            {
                "key": "foreign_interest_withholding",
                "tax_year": tax_year,
                "kind": "info",
                "category": "interest_withholding",
                "title": "Withholding on foreign interest is not a UK tax credit",
                "summary": (
                    f"[[£{total:,.2f}]] was withheld from your foreign interest. The "
                    "UK–US treaty rate on interest is 0%, so none of it is creditable against "
                    "UK tax; the interest is still taxable here in full."
                ),
                "occurrences": [
                    f"{r['broker']} [[{_money(r['amount_gbp'], 'GBP')}]] on [[{_fmt_iso(r['date'])}]]"
                    for r in foreign_tax
                ],
                "why": (
                    "Foreign Tax Credit Relief is capped at the treaty rate, which is nil for "
                    "US interest. The withholding is reclaimable from the IRS, not HMRC."
                ),
                "action": "Give the broker a valid W-8BEN so interest is paid gross.",
                "count": len(foreign_tax),
                "raw": [],
            }
        )
    return out


def build_notices(
    warnings: list[str],
    refunds: list[dict] | None = None,
    exempt: dict | None = None,
    tax_year: int | None = None,
    bundle: dict | None = None,
) -> list[dict]:
    notices: list[dict] = _exempt_notices(exempt, tax_year)
    notices += _tbill_notices(exempt, tax_year)
    notices += _data_notices(bundle, tax_year)
    covered = {n["key"]: n for n in notices}
    bnb: dict[tuple[str, int], dict] = {}
    treaty: dict[str, dict] = {}

    for raw in warnings:
        text = raw.strip()
        if not text:
            continue

        # The engine's own T-bill line says what the tbill_returns notice says
        # with figures; keep its text as the notice's raw evidence.
        if _TBILL_ENGINE.search(text) and (exempt or {}).get("tbills"):
            key = "tbill_returns" if "tbill_returns" in covered else "exempt_securities"
            if key in covered:
                covered[key]["raw"].append(text)
                continue

        # A GB payer withholding tax has no treaty to check: that is the PID
        # notice's subject, not a separate warning.
        m = _GB_TREATY.search(text)
        if m and f"pid_as_dividend__{m.group(1)}" in covered:
            covered[f"pid_as_dividend__{m.group(1)}"]["raw"].append(text)
            continue

        m = _DISCREPANCY.search(text)
        if m:
            notices.append(_discrepancy(m, text, refunds))
            continue

        m = _BNB.search(text)
        if m:
            symbol, sold, rebought = m.groups()
            year = tax_years.tax_year_of(date.fromisoformat(sold))
            group = bnb.setdefault(
                (symbol, year),
                {
                    "key": f"bed_and_breakfast__{symbol}__{year}",
                    "tax_year": year,
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
                    "tax_year": None,
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
                    "tax_year": None,
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

        year = _tax_year_in(text)
        if lowered.startswith("pdf not rendered"):
            kind, title, year = "info", "Computation PDF wasn't generated", None
        elif "missing allowance" in lowered or "no tax constants" in lowered:
            kind, title, year = "warning", "Tax-year allowances not configured", None
        else:
            kind, title = "warning", text[:90] + ("…" if len(text) > 90 else "")
        notices.append(
            {
                "key": "other__" + hashlib.sha1(text.encode()).hexdigest()[:10],
                "tax_year": year,
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
