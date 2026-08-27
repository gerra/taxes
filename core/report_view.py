"""ReportBundle + tax-year constants -> what the report page renders:
headline cards, the SA box table (with per-figure explanations), the itemised
distribution table, and the 2024/25 mid-year CGT rate-change split with the
box 51 adjustment it needs.

Box numbers follow the 2024/25 paper forms; verify on each new year's forms.
Every figure gets a short explanation: what it is, how it was computed here,
where it goes.

The tax rules themselves live in `core.estimator`; this module only decides
what is shown and says where each figure goes on the return."""

from datetime import date
from decimal import Decimal

from core import estimator, notices, tax_years


def _f(value) -> float:
    return float(Decimal(value)) if value is not None else 0.0


def chargeable_disposals(bundle: dict) -> list[dict]:
    """The disposals that count for CGT: gilts and T-bills are outside it."""
    return [
        {"date": e["date"], "symbol": e.get("symbol"), "gain": e.get("gain")}
        for e in bundle.get("disposals", [])
        if not estimator.is_cgt_exempt(e)
    ]


def _gain_split(bundle: dict, year: dict, profile: dict | None) -> dict:
    """Gains either side of the mid-year rate change, plus the box 51 adjustment
    the return needs because its own calculation charges the whole year at the
    pre-change rates.

    Without a planner profile there is no income figure to place the gains in
    the bands, so the adjustment is shown at the higher rates and says so."""
    change = year["cgt_mid_year_change"]
    cut = date.fromisoformat(change["date"])
    before = after = 0.0
    for event in chargeable_disposals(bundle):
        gain = _f(event["gain"])
        if date.fromisoformat(event["date"]) < cut:
            before += gain
        else:
            after += gain
    if profile:
        cgt = profile["cgt"]
    else:
        computed = estimator.cgt_for_year(chargeable_disposals(bundle), year, basic_room=0)
        cgt = {
            "cgt_adjustment": round(float(computed["cgt_adjustment"]), 2),
            "sa_cgt_at_pre_oct_rates": round(float(computed["sa_cgt_at_pre_oct_rates"]), 2),
            "cgt_total": round(float(computed["cgt_total"]), 2),
            "needs_box_51_adjustment": computed["needs_box_51_adjustment"],
            "has_pre_change_disposals": computed["has_pre_change_disposals"],
            "adjustment_note": computed["adjustment_note"],
        }
    note = cgt["adjustment_note"]
    if note and not profile:
        note += (
            " That assumes every gain sits above the basic rate band — add your income in "
            "the Planner tab to place them exactly."
        )
    return {
        "before": round(before, 2),
        "after": round(after, 2),
        "date": change["date"],
        "rates_before": change["rates_before"],
        "rates_after": year["cgt_rates_shares"],
        "has_pre_change_disposals": cgt["has_pre_change_disposals"],
        "needs_box_51_adjustment": cgt["needs_box_51_adjustment"],
        "cgt_adjustment": cgt["cgt_adjustment"],
        "sa_cgt_at_pre_oct_rates": cgt["sa_cgt_at_pre_oct_rates"],
        "cgt_total": cgt["cgt_total"],
        "estimated": profile is None,
        "note": note
        or (
            f"Every disposal fell on or after {_short(change['date'])}, so there is nothing to "
            "adjust: the return's own calculation already charges them correctly."
            if not cgt["has_pre_change_disposals"]
            else "The gains are within the annual exempt amount, so there is no tax to adjust."
        ),
    }


def _short(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%-d %b %Y")


def classified_income(bundle: dict) -> dict:
    """Investment income split the way UK tax splits it, not the way the broker
    labelled it: REIT PIDs out of the dividend figure and into property income,
    bond-fund distributions out and into savings income. `rows` is the itemised
    table behind the totals, for a hand audit.

    Bundles produced before the itemised rows existed fall back to the engine's
    own totals for whichever family has no rows."""
    t = bundle["totals"]
    rows = estimator.classify_distributions(bundle)
    c = estimator.income_totals(rows)
    itemised = bool(bundle.get("dividends") or bundle.get("eri_distributions"))
    int_rows = bundle.get("interest") or []
    if itemised:
        uk_dividends = float(c["uk_dividends"])
        foreign_dividends = float(c["foreign_dividends"])
        foreign_dividend_tax = float(c["foreign_dividend_tax"])
        treaty_relief = float(c["foreign_dividend_treaty_relief"])
    else:
        uk_dividends = 0.0
        foreign_dividends = _f(t["dividends_total"])
        foreign_dividend_tax = _f(t.get("dividend_treaty_relief"))
        treaty_relief = _f(t.get("dividend_treaty_relief"))
    if itemised or bundle.get("other_income"):
        other_income = float(c["other_income"])
        other_income_tax = float(c["other_income_tax"])
    else:
        other_income = _f(t.get("other_income"))
        other_income_tax = _f(t.get("other_income_tax"))
    return {
        "rows": rows,
        "uk_dividends": round(uk_dividends, 2),
        "foreign_dividends": round(foreign_dividends, 2),
        "dividends_total": round(uk_dividends + foreign_dividends, 2),
        "foreign_dividend_tax": round(foreign_dividend_tax, 2),
        "foreign_dividend_treaty_relief": round(treaty_relief, 2),
        "property_income": round(float(c["property_income"]), 2),
        "property_income_tax": round(float(c["property_income_tax"]), 2),
        "share_lending_fees": round(float(c["share_lending_fees"]), 2),
        "other_income": round(other_income, 2),
        "other_income_tax": round(other_income_tax, 2),
        "interest_distributions": round(float(c["interest_distributions"]), 2),
        "uk_interest": round(float(c["uk_interest"]) if int_rows else _f(t["uk_interest"]), 2),
        "foreign_interest": round(
            float(c["foreign_interest"]) if int_rows else _f(t["foreign_interest"]), 2
        ),
    }


def _symbols(rows: list[dict], *kinds: str) -> list[str]:
    return sorted({r["source"] for r in rows if r["kind"] in kinds and r["source"]})


def build_view(bundle: dict, tax_year: int, profile: dict | None) -> dict:
    y = tax_years.get_year(tax_year) or {}
    t = bundle["totals"]
    yl = tax_years.label(tax_year)

    proceeds = _f(t["disposal_proceeds"])
    costs = _f(t["allowable_costs"])
    gains_before_losses = _f(t["capital_gain_before_losses"])
    losses = abs(_f(t["capital_loss"]))
    taxable_gain = _f(t["taxable_gain"]) if t["taxable_gain"] is not None else None
    inc = classified_income(bundle)
    rows = inc["rows"]
    dividends_total = inc["dividends_total"]
    treaty_relief = inc["foreign_dividend_treaty_relief"]
    # The dividend allowance is the only thing that comes off the taxable
    # dividend figure. Foreign tax credit relief is a credit against the tax —
    # deducting it here would relieve it twice.
    dividends_taxable = max(0.0, dividends_total - _f(y.get("dividend_allowance")))
    uk_interest = inc["uk_interest"]
    foreign_interest = inc["foreign_interest"]
    interest_distributions = inc["interest_distributions"]
    interest_fund_symbols = _symbols(rows, estimator.INTEREST_DISTRIBUTION, estimator.ERI_INTEREST)
    other_income = inc["other_income"]
    other_income_tax = inc["other_income_tax"]
    pid_total = inc["property_income"]
    fee_total = inc["share_lending_fees"]
    pid_sources = _symbols(rows, estimator.PROPERTY_INCOME_DISTRIBUTION)
    uk_dividends = inc["uk_dividends"]
    uk_div_symbols = _symbols(rows, estimator.UK_DIVIDEND)
    foreign_dividends = inc["foreign_dividends"]
    foreign_div_symbols = _symbols(rows, estimator.FOREIGN_DIVIDEND, estimator.ERI_DIVIDEND)
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
            "form": "SA106",
            "box": "interest",
            "label": "Interest distributions from bond funds",
            "value": round(interest_distributions, 2),
            "explain": "Distributions from funds holding more than 60% interest-bearing "
            "assets"
            + (f" ({', '.join(interest_fund_symbols)})" if interest_fund_symbols else "")
            + " are interest for UK tax, not dividends (ITTOIA 2005 s378A): savings "
            "income, taxed after the personal savings allowance and never touching the "
            "dividend allowance. Offshore-domiciled funds report them on the SA106 "
            "foreign pages; a UK-domiciled fund's go in box 2 with your other interest. "
            "Check each fund's reporting-fund statement — the >60% test is what decides "
            "it, not the fund's name.",
        },
        {
            "form": "SA100 TR3",
            "box": "4",
            "label": "Dividends from UK companies",
            "value": round(uk_dividends, 2),
            "explain": "Ordinary dividends from UK-registered companies"
            + (f" ({', '.join(uk_div_symbols)})" if uk_div_symbols else "")
            + ", gross. UK dividends carry no withholding, so anything a UK payer "
            "took tax off has been reclassified as a REIT property income "
            "distribution and moved to box 17 — see the distributions table.",
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
            "explain": "Withholding capped at the treaty rate (15% under the UK–US "
            "treaty) — claimable as Foreign Tax Credit Relief, which comes off the "
            "UK tax due, not off the dividend figure above. Anything withheld above "
            "the treaty rate is not creditable here; only the IRS can refund it. The "
            "relief is further capped at the UK tax on this same income.",
        },
    ]
    if interest_distributions <= 0:
        sa_boxes = [b for b in sa_boxes if b["box"] != "interest"]
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
        rate_change = _gain_split(bundle, y, profile)

    cards = {
        "taxable_gain": {
            "value": taxable_gain,
            "sub": f"after £{y.get('cgt_allowance', 0):,} annual exempt amount" if y else None,
            "estimated_tax": profile["tax"]["cgt_estimate"] if profile else None,
        },
        "dividends_taxable": {
            "value": round(dividends_taxable, 2),
            "sub": f"of £{dividends_total:,.2f} total, after the "
            f"£{_f(y.get('dividend_allowance')):,.0f} dividend allowance"
            + (
                f" — £{treaty_relief:,.2f} of foreign tax comes off the tax due, "
                "not off this figure"
                if treaty_relief
                else ""
            ),
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
        non_cgt = tx["dividend_tax"] + tx["savings_tax"] + tx.get("other_income_tax", 0.0)
        tax_due = {
            "available": True,
            "cgt": tx["cgt_total"],
            "cgt_sa_at_pre_oct_rates": tx["sa_cgt_at_pre_oct_rates"],
            "cgt_adjustment": tx["cgt_adjustment"],
            "cgt_note": tx.get("cgt_note"),
            "dividends": tx["dividend_tax"],
            "dividends_before_ftcr": tx["dividend_tax_before_ftcr"],
            "ftcr": tx["ftcr"],
            "foreign_tax_withheld": tx["foreign_tax_withheld"],
            "interest": tx["savings_tax"],
            "other_income": tx.get("other_income_tax", 0.0),
            # The headline bill. Payments on account look at `excluding_cgt`.
            "total": round(non_cgt + tx["cgt_total"], 2),
            "excluding_cgt": round(non_cgt, 2),
            "marginal_band": profile["bands"]["marginal_band"],
            "personal_allowance": profile["allowances"]["personal_allowance"],
            "psa": profile["allowances"]["psa"],
            "cgt_at_basic": tx["cgt_at_basic"],
            "cgt_at_higher": tx["cgt_at_higher"],
            "cgt_rates": y.get("cgt_rates_shares"),
            "cgt_buckets": profile["cgt"]["buckets"],
            "dividend_allowance": y.get("dividend_allowance"),
            "cgt_allowance": y.get("cgt_allowance"),
            "payments_on_account": profile["payments_on_account"],
        }
    else:
        tax_due = {"available": False}

    return {
        "tax_year": tax_year,
        "label": yl,
        "filing_deadline": tax_years.filing_deadline(tax_year).isoformat(),
        "cards": cards,
        "sa_boxes": sa_boxes,
        "distributions": _distribution_rows(rows),
        "distribution_totals": {k: v for k, v in inc.items() if k != "rows"},
        "rate_change_split": rate_change,
        "exempt_disposals": exempt_disposals,
        "warnings": warnings,
        "notices": notices.build_notices(
            warnings, bundle.get("refunds"), bundle.get("exempt"), tax_year, bundle
        ),
        "has_estimates": profile is not None,
        "tax_due": tax_due,
    }


def _distribution_rows(rows: list[dict]) -> list[dict]:
    """The itemised distribution table: one line per payment, with what it was
    classified as and why, for checking against the broker's statements."""
    return [
        {
            "date": r["date"],
            "symbol": r["symbol"],
            "source": r["source"],
            "kind": r["kind"],
            "label": r["label"],
            "taxed_as": r["taxed_as"],
            "uses_dividend_allowance": r["uses_dividend_allowance"],
            "currency": r["currency"],
            "gross": str(r["gross"]) if r["gross"] is not None else None,
            "fx_rate": str(r["fx_rate"]) if r["fx_rate"] is not None else None,
            "gross_gbp": round(float(r["gross_gbp"]), 2),
            "withheld_gbp": round(float(r["withheld_gbp"]), 2),
            "treaty_relief_gbp": round(float(r["treaty_relief_gbp"]), 2),
            "why": r["why"],
        }
        for r in rows
    ]


def summary_for_planner(bundle: dict) -> dict:
    """What the planner and the tax profile need from a report run: income by
    UK tax classification, and the chargeable disposals so capital gains can be
    charged at the rate for their disposal date."""
    t = bundle["totals"]
    inc = classified_income(bundle)
    return {
        "dividends_total": inc["dividends_total"],
        "uk_dividends": inc["uk_dividends"],
        "foreign_dividends": inc["foreign_dividends"],
        "foreign_dividend_tax": inc["foreign_dividend_tax"],
        "foreign_dividend_treaty_relief": inc["foreign_dividend_treaty_relief"],
        "uk_interest": inc["uk_interest"],
        "foreign_interest": inc["foreign_interest"],
        "interest_distributions": inc["interest_distributions"],
        "other_income": inc["other_income"],
        "other_income_tax": inc["other_income_tax"],
        "total_gain": _f(t["total_gain"]),
        "taxable_gain": _f(t["taxable_gain"]) if t["taxable_gain"] is not None else 0.0,
        "disposals": chargeable_disposals(bundle),
    }
