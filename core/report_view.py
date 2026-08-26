"""ReportBundle + tax-year constants -> what the report page renders:
headline cards, the SA box table (with per-figure explanations), and the
2024/25 mid-year CGT rate-change split when applicable.

Box numbers follow the 2024/25 paper forms; verify on each new year's forms.
Every figure gets a short explanation: what it is, how it was computed here,
where it goes."""

from datetime import date
from decimal import Decimal

from core import notices, tax_years


def _f(value) -> float:
    return float(Decimal(value)) if value is not None else 0.0


def _gain_split(bundle: dict, change_date: str) -> dict:
    cut = date.fromisoformat(change_date)
    before = after = 0.0
    for event in bundle.get("disposals", []):
        if event.get("exempt"):
            continue
        gain = _f(event["gain"])
        if date.fromisoformat(event["date"]) < cut:
            before += gain
        else:
            after += gain
    return {"before": round(before, 2), "after": round(after, 2), "date": change_date}


def build_view(bundle: dict, tax_year: int, profile: dict | None) -> dict:
    y = tax_years.get_year(tax_year) or {}
    t = bundle["totals"]
    yl = tax_years.label(tax_year)

    proceeds = _f(t["disposal_proceeds"])
    costs = _f(t["allowable_costs"])
    gains_before_losses = _f(t["capital_gain_before_losses"])
    losses = abs(_f(t["capital_loss"]))
    taxable_gain = _f(t["taxable_gain"]) if t["taxable_gain"] is not None else None
    dividends_total = _f(t["dividends_total"])
    treaty_relief = _f(t["dividend_treaty_relief"])
    dividends_taxable = _f(t["dividends_taxable"])
    uk_interest = _f(t["uk_interest"])
    foreign_interest = _f(t["foreign_interest"])
    other_income = _f(t.get("other_income"))
    other_income_tax = _f(t.get("other_income_tax"))
    other_rows = bundle.get("other_income", [])
    # A REIT distribution is logged under its ticker with tax withheld; a
    # share-lending fee under the broker's name with none.
    brokers = {r["broker"] for r in bundle.get("interest", [])} | {"Freetrade", "Charles Schwab"}
    pid_sources = sorted(
        {r["source"] for r in other_rows if _f(r.get("tax_gbp")) > 0 or r["source"] not in brokers}
    )
    fee_total = sum(_f(r["amount_gbp"]) for r in other_rows if r["source"] not in pid_sources)
    pid_total = other_income - fee_total
    # Dividends split by the payer's ISIN country: GB is a UK dividend, anything
    # else (Irish/Luxembourg ETFs, US shares) belongs on the foreign pages. ERI
    # (offshore funds by definition) stays with the foreign figure.
    div_rows = bundle.get("dividends", [])
    uk_dividends = sum(_f(d["amount_gbp"]) for d in div_rows if d.get("country") == "GB")
    uk_div_symbols = sorted({d["symbol"] for d in div_rows if d.get("country") == "GB"})
    foreign_dividends = max(0.0, dividends_total - uk_dividends)
    foreign_div_symbols = sorted({d["symbol"] for d in div_rows if d.get("country") != "GB"})
    # T-bill returns that fall in this year (deeply discounted securities).
    tbills = [t for t in (bundle.get("exempt") or {}).get("tbills", []) if t.get("in_year")]
    tbill_profit = sum(_f(t["profit"]) for t in tbills if t.get("profit") is not None)

    sa_boxes = [
        {
            "form": "SA108",
            "box": "23",
            "label": "Number of disposals",
            "value": t["disposal_count"],
            "format": "int",
            "explain": f"How many share disposals you made in {yl}. Same-day trades "
            "in one security count as one disposal.",
        },
        {
            "form": "SA108",
            "box": "24",
            "label": "Disposal proceeds",
            "value": round(proceeds, 2),
            "explain": "The GBP sum of everything you sold this tax year, converted "
            "at HMRC monthly exchange rates on each sale date.",
        },
        {
            "form": "SA108",
            "box": "25",
            "label": "Allowable costs",
            "value": round(costs, 2),
            "explain": "What HMRC lets you deduct: the matched acquisition cost of "
            "the shares sold (same-day, then 30-day, then the Section 104 pooled "
            "average cost) plus dealing fees.",
        },
        {
            "form": "SA108",
            "box": "26",
            "label": "Gains in the year, before losses",
            "value": round(gains_before_losses, 2),
            "explain": "The sum of every disposal that made a gain, before "
            "subtracting the loss-making ones.",
        },
        {
            "form": "SA108",
            "box": "27",
            "label": "Losses in the year",
            "value": round(losses, 2),
            "explain": "The sum of every disposal that made a loss. Losses first "
            "offset this year's gains; unused losses carry forward if claimed "
            "within 4 years.",
        },
        {
            "form": "SA100 TR3",
            "box": "2",
            "label": "Untaxed UK interest",
            "value": round(uk_interest, 2),
            "explain": "Interest paid gross by UK banks/brokers (GBP accounts). "
            "Taxed after your personal savings allowance.",
        },
        {
            "form": "SA106" if foreign_interest > 0 else "SA100 TR3",
            "box": "F" if foreign_interest > 0 else "3",
            "label": "Foreign interest",
            "value": round(foreign_interest, 2),
            "explain": "Interest from non-UK sources (e.g. USD cash at a US broker), "
            "converted at HMRC monthly rates. Under £2,000 with no foreign tax "
            "taken off it can go on the main return; otherwise it belongs on the "
            "SA106 foreign pages.",
        },
        {
            "form": "SA100 TR3",
            "box": "4",
            "label": "Dividends from UK companies",
            "value": round(uk_dividends, 2),
            "explain": "Dividends whose payer has a GB ISIN"
            + (f" ({', '.join(uk_div_symbols)})" if uk_div_symbols else "")
            + ", gross. UK dividends carry no withholding; if one here shows tax "
            "taken off it is a REIT property income distribution mislabelled as a "
            "dividend — see the notice.",
        },
        {
            "form": "SA106",
            "box": "dividends",
            "label": "Foreign dividends (gross)",
            "value": round(foreign_dividends, 2),
            "explain": "Dividends from payers registered outside the UK"
            + (f" ({', '.join(foreign_div_symbols)})" if foreign_div_symbols else "")
            + " — US shares, and Irish- or Luxembourg-domiciled ETFs count as foreign "
            "even when they pay in GBP — gross, in GBP at HMRC monthly rates, plus any "
            "excess reported income. Goes on the SA106 foreign pages (or the main "
            "return's small-amounts box if under that year's limit) with the "
            "withholding alongside.",
        },
        {
            "form": "SA106",
            "box": "foreign tax",
            "label": "Foreign tax taken off (treaty-limited)",
            "value": round(treaty_relief, 2),
            "explain": "US withholding at the 15% UK–US treaty rate — claimable as "
            "Foreign Tax Credit Relief against the UK dividend tax. Withholding "
            "above 15% is not creditable.",
        },
    ]
    if other_income > 0:
        parts = []
        if pid_total > 0:
            parts.append(
                f"£{pid_total:,.2f} of property income distributions from UK REITs "
                f"({', '.join(pid_sources)}), gross"
            )
        if fee_total > 0:
            parts.append(f"£{fee_total:,.2f} of share-lending fees")
        sa_boxes.append(
            {
                "form": "SA100 TR3",
                "box": "17",
                "label": "Other taxable income (REIT PIDs, share lending)",
                "value": round(other_income, 2),
                "explain": " and ".join(parts) + ". PIDs are taxed as property income and "
                "share-lending fees as miscellaneous income — neither is a dividend nor "
                "interest, so both go in 'Other UK income' box 17, with what they are in "
                "box 21. Share-lending fees under £1,000 are covered by the trading and "
                "miscellaneous income allowance if you have no other such income; PIDs "
                "are not covered by the £1,000 property allowance.",
            }
        )
        sa_boxes.append(
            {
                "form": "SA100 TR3",
                "box": "19",
                "label": "Tax taken off other income",
                "value": round(other_income_tax, 2),
                "explain": "The 20% basic-rate tax the REITs withheld from the PIDs before "
                "paying them. HMRC sets it against your bill, so enter it here rather "
                "than netting it off box 17.",
            }
        )

    if tbill_profit > 0:
        sa_boxes.append(
            {
                "form": "SA101 Ai1",
                "box": "3",
                "label": "Deeply discounted securities: T-bill returns (gross)",
                "value": round(tbill_profit, 2),
                "explain": f"{len(tbills)} UK Treasury bill{'s' if len(tbills) != 1 else ''} "
                "matured or were sold this year. A T-bill is bought below £1 per unit and "
                "redeemed at £1 on the date in its name; the difference is income from a "
                "deeply discounted security, not a capital gain. Reconstructed from the "
                "purchases because Freetrade never exports the redemption — check it against "
                "your statements. Goes in the 'Interest from gilt-edged and other UK "
                "securities, deeply discounted securities and accrued income profits' "
                "section of the SA101 Additional information pages (gross amount box).",
            }
        )

    # T-bill redemptions (reconstructed by the parser as sales at par) are
    # exempt disposals too, but their return is the SA101 income above, so the
    # banner keeps them apart from the gilts' notional gains.
    tbill_symbols = {
        s["symbol"]
        for s in (bundle.get("exempt") or {}).get("securities", [])
        if s["kind"] == "tbill"
    }
    all_exempt = [e for e in bundle.get("disposals", []) if e.get("exempt")]
    exempt_events = [e for e in all_exempt if e["symbol"] not in tbill_symbols]
    tbill_events = [e for e in all_exempt if e["symbol"] in tbill_symbols]
    exempt_disposals = None
    if all_exempt:
        exempt_gain = sum(_f(e["gain"]) for e in exempt_events)
        symbols = sorted({e["symbol"] for e in exempt_events})
        parts = []
        if exempt_events:
            parts.append(
                f"{len(exempt_events)} disposal{'s' if len(exempt_events) != 1 else ''} of "
                f"gilts ({', '.join(symbols)}) with a notional "
                f"{'gain' if exempt_gain >= 0 else 'loss'} of £{abs(exempt_gain):,.2f}"
            )
        if tbill_events:
            parts.append(
                f"{len(tbill_events)} UK T-bill redemption{'s' if len(tbill_events) != 1 else ''} "
                "whose discount is income (the SA101 row), not a gain"
            )
        exempt_disposals = {
            "count": len(exempt_events),
            "tbill_count": len(tbill_events),
            "proceeds": round(sum(_f(e["amount"]) for e in exempt_events), 2),
            "gain": round(exempt_gain, 2),
            "symbols": symbols,
            "explain": (
                " and ".join(parts) + " — exempt from capital gains tax under TCGA 1992 "
                "s115, so not counted in the SA108 boxes above and not disposals to declare. "
                "Interest on gilts is still taxable."
            ),
        }

    warnings = list(bundle.get("warnings", []))
    if not y:
        warnings.append(
            f"No tax constants for {yl} — allowances/rates missing; extend core/tax_years.py."
        )

    rate_change = None
    if y.get("cgt_mid_year_change"):
        rate_change = _gain_split(bundle, y["cgt_mid_year_change"]["date"])

    cards = {
        "taxable_gain": {
            "value": taxable_gain,
            "sub": f"after £{y.get('cgt_allowance', 0):,} annual exempt amount" if y else None,
            "estimated_tax": profile["tax"]["cgt_estimate"] if profile else None,
        },
        "dividends_taxable": {
            "value": round(dividends_taxable, 2),
            "sub": f"of £{dividends_total:,.2f} total, after allowance and treaty relief",
            "estimated_tax": profile["tax"]["dividend_tax"] if profile else None,
        },
        "uk_interest": {"value": round(uk_interest, 2)},
        "foreign_interest": {"value": round(foreign_interest, 2)},
        "interest_estimated_tax": profile["tax"]["savings_tax"] if profile else None,
        "other_income": {
            "value": round(other_income, 2),
            "tax_taken_off": round(other_income_tax, 2),
            "estimated_tax": profile["tax"].get("other_income_tax") if profile else None,
        },
    }

    if profile:
        tx = profile["tax"]
        tax_due = {
            "available": True,
            "cgt": tx["cgt_estimate"],
            "dividends": tx["dividend_tax"],
            "interest": tx["savings_tax"],
            "other_income": tx.get("other_income_tax", 0.0),
            "total": round(
                tx["cgt_estimate"]
                + tx["dividend_tax"]
                + tx["savings_tax"]
                + tx.get("other_income_tax", 0.0),
                2,
            ),
            "marginal_band": profile["bands"]["marginal_band"],
            "personal_allowance": profile["allowances"]["personal_allowance"],
            "psa": profile["allowances"]["psa"],
            "cgt_at_basic": tx["cgt_at_basic"],
            "cgt_at_higher": tx["cgt_at_higher"],
            "cgt_rates": y.get("cgt_rates_shares"),
            "dividend_allowance": y.get("dividend_allowance"),
            "cgt_allowance": y.get("cgt_allowance"),
        }
    else:
        tax_due = {"available": False}

    return {
        "tax_year": tax_year,
        "label": yl,
        "filing_deadline": tax_years.filing_deadline(tax_year).isoformat(),
        "cards": cards,
        "sa_boxes": sa_boxes,
        "rate_change_split": rate_change,
        "exempt_disposals": exempt_disposals,
        "warnings": warnings,
        "notices": notices.build_notices(
            warnings, bundle.get("refunds"), bundle.get("exempt"), tax_year, bundle
        ),
        "has_estimates": profile is not None,
        "tax_due": tax_due,
    }


def summary_for_planner(bundle: dict) -> dict:
    t = bundle["totals"]
    return {
        "dividends_total": _f(t["dividends_total"]),
        "dividends_taxable": _f(t["dividends_taxable"]),
        "uk_interest": _f(t["uk_interest"]),
        "foreign_interest": _f(t["foreign_interest"]),
        "other_income": _f(t.get("other_income")),
        "other_income_tax": _f(t.get("other_income_tax")),
        "total_gain": _f(t["total_gain"]),
        "taxable_gain": _f(t["taxable_gain"]) if t["taxable_gain"] is not None else 0.0,
    }
