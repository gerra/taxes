"""ReportBundle + tax-year constants -> what the report page renders:
headline cards, the SA box table (with per-figure explanations), and the
2024/25 mid-year CGT rate-change split when applicable.

Box numbers follow the 2024/25 paper forms; verify on each new year's forms.
Every figure gets a short explanation: what it is, how it was computed here,
where it goes."""

from datetime import date
from decimal import Decimal

from core import tax_years


def _f(value) -> float:
    return float(Decimal(value)) if value is not None else 0.0


def _gain_split(bundle: dict, change_date: str) -> dict:
    cut = date.fromisoformat(change_date)
    before = after = 0.0
    for event in bundle.get("disposals", []):
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
            "form": "SA106",
            "box": "dividends",
            "label": "Foreign dividends (gross)",
            "value": round(dividends_total, 2),
            "explain": "Dividends from non-UK companies (your US holdings), gross, "
            "in GBP at HMRC monthly rates. Goes on the SA106 foreign pages with "
            "the US withholding alongside.",
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
    }

    return {
        "tax_year": tax_year,
        "label": yl,
        "filing_deadline": tax_years.filing_deadline(tax_year).isoformat(),
        "cards": cards,
        "sa_boxes": sa_boxes,
        "rate_change_split": rate_change,
        "warnings": warnings,
        "has_estimates": profile is not None,
    }


def summary_for_planner(bundle: dict) -> dict:
    t = bundle["totals"]
    return {
        "dividends_total": _f(t["dividends_total"]),
        "dividends_taxable": _f(t["dividends_taxable"]),
        "uk_interest": _f(t["uk_interest"]),
        "foreign_interest": _f(t["foreign_interest"]),
        "total_gain": _f(t["total_gain"]),
        "taxable_gain": _f(t["taxable_gain"]) if t["taxable_gain"] is not None else 0.0,
    }
