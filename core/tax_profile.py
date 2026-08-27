"""Income-tax profile + estimated tax on investment income, from planner inputs
plus the report's investment summary.

Simplified rUK (non-Scottish) rules, stacked in HMRC order: non-savings →
savings → dividends → capital gains. Deliberate simplifications are marked
`# approx:` — each tip that relies on one states its assumption.

Everything that needs the tax rules themselves rather than the band stacking —
capital gains by disposal date, foreign tax credit relief, the payments-on-
account test — lives in `core.estimator`; this module supplies the band
positions it needs and converts the result to the floats the API sends.

What this module's `tax` block reports is the tax on INVESTMENT income at your
marginal position: dividends, interest and gains, on the assumption that
employment tax was collected correctly through PAYE. That assumption is often
wrong, and the whole Self Assessment bill — including what PAYE under- or
over-collected on salary — is computed by `core.self_assessment` and carried
here under `self_assessment`. The two are kept side by side deliberately: the
investment-only figure is what this tool used to show as its headline and is
still worth seeing, but it is a sub-total, not the bill."""

from dataclasses import dataclass

from core import estimator, self_assessment, tax_years


@dataclass
class Slice:
    amount: float
    rate: float

    @property
    def tax(self) -> float:
        return self.amount * self.rate


def _band_slices(
    amount: float, floor: float, basic_top: float, additional_top: float, rates: dict
) -> tuple[list[Slice], float]:
    """Split `amount` of taxable income starting at `floor` into rate slices.
    Returns (slices, new_floor)."""
    slices = []
    cursor = floor
    remaining = amount
    for top, rate_key in ((basic_top, "basic"), (additional_top, "higher"), (None, "additional")):
        if remaining <= 0:
            break
        room = remaining if top is None else max(0.0, min(remaining, top - cursor))
        if room > 0:
            slices.append(Slice(room, rates[rate_key]))
            cursor += room
            remaining -= room
    return slices, cursor


def _f(value) -> float:
    return float(value or 0)


def _income_parts(inputs: dict, invest: dict) -> tuple[float, float, float]:
    """(non-savings, savings, dividends) from planner inputs + report summary."""

    def val(key: str) -> float:
        return float(inputs.get(key) or 0)

    employment = val("employment_income")  # P60 "pay" — already net of net-pay pension
    # Savings income is cash interest plus the distributions of bond funds,
    # which are interest for UK tax however the broker labelled them.
    savings = (
        _f(invest.get("uk_interest"))
        + _f(invest.get("foreign_interest"))
        + _f(invest.get("interest_distributions"))
        + val("other_interest")
    )
    dividends = _f(invest.get("dividends_total"))
    # The report's REIT PIDs and share-lending fees are non-savings income too.
    other = val("other_income") + _f(invest.get("other_income"))
    return employment + other, savings, dividends


def total_income(inputs: dict, invest: dict) -> float:
    """Net income before reliefs (ITA 2007 s23 step 2, simplified): employment +
    other income + interest + dividends. Used for the pension taper tests."""
    return sum(_income_parts(inputs, invest))


def _cgt(invest: dict, year: dict, basic_room: float) -> dict:
    """Capital gains tax, by disposal date where the disposals are known.

    Without them — a planner run with only a taxable-gain figure typed in — the
    year's headline rates are used and `dates_known` says so, because there is
    nothing to split on."""
    disposals = invest.get("disposals")
    if disposals:
        result = estimator.cgt_for_year(disposals, year, basic_room=basic_room)
        result["dates_known"] = True
        return result
    taxable_gain = estimator.dec(invest.get("taxable_gain"))
    synthetic = [{"date": None, "gain": taxable_gain + estimator.dec(year["cgt_allowance"])}]
    result = estimator.cgt_for_year(
        # A dateless disposal falls in the post-change bucket: the current rates.
        [{**synthetic[0], "date": _year_end_iso(year)}],
        year,
        basic_room=basic_room,
    )
    result["dates_known"] = False
    return result


def _year_end_iso(year: dict) -> str:
    """A date guaranteed to sit after any mid-year rate change in that year."""
    change = estimator.rate_change(year)
    return change["date"] if change else "1900-01-01"


def build_profile(inputs: dict, year: dict, invest: dict) -> dict:
    """inputs: planner form (floats, may be missing). invest: report summary
    (core.report_view.summary_for_planner) — zeros if absent."""

    def val(key: str) -> float:
        return float(inputs.get(key) or 0)

    sipp_gross = val("sipp_paid") / 0.8  # relief at source: HMRC adds 25% of the net payment
    gift_aid_gross = val("gift_aid_paid") / 0.8

    non_savings, savings, dividends = _income_parts(inputs, invest)
    # REIT PIDs and share-lending fees from the report: taxed at the marginal
    # income-tax rates, with the 20% the REITs withheld credited against the bill.
    report_other = _f(invest.get("other_income"))
    report_other_credit = _f(invest.get("other_income_tax"))
    total_income = non_savings + savings + dividends
    adjusted_net_income = max(0.0, total_income - sipp_gross - gift_aid_gross)

    band_extension = sipp_gross + gift_aid_gross
    # Both limits are measured in taxable (post-allowance) income, per ITA 2007
    # s10, and neither moves with the allowance: someone whose allowance has
    # tapered to nil still gets £37,700 at the basic rate and pays the
    # additional rate only above the year's higher rate limit of taxable income.
    # Deducting the standard allowance from that limit — as this did before the
    # PAYE reconciliation went in — moved £12,570 of a £220k salary from 40% to
    # 45% and overstated the tax on it by about £628. Where the limits are, and
    # which band anything lands in, comes from the year table via `bands`.
    bands = tax_years.bands_for(year, band_extension)
    pa = float(bands.personal_allowance(adjusted_net_income))
    basic_top = float(bands.basic_limit)
    additional_top = float(bands.higher_limit)

    # Allocate PA: non-savings first, then savings, then dividends
    pa_left = pa
    taxable_non_savings = max(0.0, non_savings - pa_left)
    pa_left = max(0.0, pa_left - non_savings)
    taxable_savings = max(0.0, savings - pa_left)
    pa_left = max(0.0, pa_left - savings)
    taxable_dividends = max(0.0, dividends - pa_left)

    floor = 0.0
    ns_slices, floor = _band_slices(
        taxable_non_savings, floor, basic_top, additional_top, year["income_rates"]
    )
    # Tax on the report's other income = what non-savings tax would drop by without it.
    ns_without_other, _ = _band_slices(
        max(0.0, taxable_non_savings - report_other),
        0.0,
        basic_top,
        additional_top,
        year["income_rates"],
    )
    other_income_gross_tax = sum(s.tax for s in ns_slices) - sum(s.tax for s in ns_without_other)
    other_income_tax = other_income_gross_tax - report_other_credit

    # Savings: starting rate band (0%) shrinks £-for-£ with taxable non-savings income,
    # then the PSA (0%) sized by the band the savings income falls into.
    starting_band = max(0.0, year["starting_rate_savings_band"] - taxable_non_savings)
    band_at_floor = bands.band_at(floor)
    psa = float(bands.psa(band_at_floor))
    savings_at_zero = min(taxable_savings, starting_band + psa)
    floor += savings_at_zero
    sv_slices, floor = _band_slices(
        taxable_savings - savings_at_zero, floor, basic_top, additional_top, year["income_rates"]
    )

    # Dividends. The £0-rate allowance is taxed at 0% but still occupies band
    # space, and it goes to the UK dividends first: leaving the foreign ones
    # fully charged is what lets the foreign tax credit be used rather than
    # wasted (FTCR is capped at the UK tax on that same income).
    uk_dividends = _f(invest.get("uk_dividends"))
    foreign_dividends = _f(invest.get("foreign_dividends"))
    if uk_dividends + foreign_dividends <= 0:
        uk_dividends, foreign_dividends = dividends, 0.0
    pa_on_dividends = dividends - taxable_dividends
    uk_taxable_dividends = max(0.0, uk_dividends - pa_on_dividends)
    foreign_taxable_dividends = max(0.0, taxable_dividends - uk_taxable_dividends)

    div_allowance_used = min(taxable_dividends, year["dividend_allowance"])
    uk_allowance_used = min(uk_taxable_dividends, div_allowance_used)
    foreign_charged = max(0.0, foreign_taxable_dividends - (div_allowance_used - uk_allowance_used))

    dividend_floor = floor + div_allowance_used
    charged_dividends = taxable_dividends - div_allowance_used
    dv_slices, floor = _band_slices(
        charged_dividends, dividend_floor, basic_top, additional_top, year["dividend_rates"]
    )
    # The foreign dividends sit at the top of the dividend stack (the allowance
    # went to the UK ones), so the UK tax on them is what the top slice costs.
    dv_without_foreign, _ = _band_slices(
        max(0.0, charged_dividends - foreign_charged),
        dividend_floor,
        basic_top,
        additional_top,
        year["dividend_rates"],
    )
    dividend_tax_gross = sum(s.tax for s in dv_slices)
    uk_tax_on_foreign_dividends = dividend_tax_gross - sum(s.tax for s in dv_without_foreign)

    # Foreign tax credit relief: a credit against the tax, never a deduction
    # from the taxable amount.
    withheld = _f(invest.get("foreign_dividend_tax"))
    treaty_rate = invest.get("foreign_dividend_treaty_rate")
    treaty_cap = invest.get("foreign_dividend_treaty_relief")
    if treaty_cap is None:
        treaty_cap = _f(treaty_rate if treaty_rate is not None else 0.15) * foreign_dividends
    relief = float(
        estimator.ftcr(
            gross=estimator.dec(foreign_dividends),
            withheld=estimator.dec(min(_f(withheld), _f(treaty_cap))),
            treaty_rate=estimator.ONE,
            uk_tax_on_income=estimator.dec(uk_tax_on_foreign_dividends),
        )
    )
    dividend_tax = dividend_tax_gross - relief

    taxable_income_total = taxable_non_savings + taxable_savings + taxable_dividends

    # CGT on shares: gains stack on top of taxable income, and the rate depends
    # on the disposal date in a year whose rates changed mid-year.
    basic_room = float(bands.basic_room(taxable_income_total))
    cgt = _cgt(invest, year, basic_room)
    cgt_total = float(cgt["cgt_total"])
    cgt_at_basic = float(sum(b["at_basic"] for b in cgt["buckets"]))
    cgt_at_higher = float(sum(b["at_higher"] for b in cgt["buckets"]))
    cgt_note = None
    if cgt["split_applies"] and not cgt["dates_known"]:
        cgt_note = (
            "This year's CGT rates changed on 30 October 2024 and no disposal dates were "
            "available here, so the estimate uses the post-change rates. Run the report to "
            "split it by disposal date."
        )
    elif cgt["needs_box_51_adjustment"]:
        cgt_note = cgt["adjustment_note"]

    savings_tax = sum(s.tax for s in sv_slices)
    non_savings_tax = sum(s.tax for s in ns_slices)
    income_tax_total = non_savings_tax + savings_tax + dividend_tax

    # The whole bill, PAYE reconciliation included. It is computed from the same
    # planner inputs and report summary, on Decimals and with HMRC's rounding,
    # and it owns the payments-on-account test: that test needs the real
    # balancing payment (the income tax shortfall after PAYE), which nothing in
    # this module's investment-only view can see.
    sa = self_assessment.compute_for(inputs, year, invest)
    poa = sa["payments_on_account"]

    marginal_band = bands.band_at(taxable_income_total)
    marginal_rate = float(bands.income_rate(marginal_band))
    in_pa_taper = bands.in_pa_taper(adjusted_net_income)
    # approx: inside the taper each £1 of extra income also costs 50p of PA → ~60%
    effective_marginal = 0.60 if in_pa_taper else marginal_rate

    return {
        "income": {
            "non_savings": non_savings,
            "other_income": report_other,
            "savings": savings,
            "dividends": dividends,
            "uk_dividends": uk_dividends,
            "foreign_dividends": foreign_dividends,
            "total": total_income,
            "adjusted_net_income": adjusted_net_income,
        },
        "allowances": {
            "personal_allowance": pa,
            "psa": psa,
            "psa_used": min(taxable_savings, psa),
            "starting_rate_used": min(taxable_savings, starting_band),
            "dividend_allowance": year["dividend_allowance"],
            "dividend_allowance_used": round(div_allowance_used, 2),
            "cgt_allowance": year["cgt_allowance"],
        },
        "bands": {
            "basic_top": basic_top,
            "additional_top": additional_top,
            "taxable_income": taxable_income_total,
            "marginal_band": marginal_band,
            "in_pa_taper": in_pa_taper,
            "cgt_basic_room": round(basic_room, 2),
        },
        "tax": {
            "income_tax_total": round(income_tax_total, 2),
            "savings_tax": round(savings_tax, 2),
            "dividend_tax": round(dividend_tax, 2),
            "dividend_tax_before_ftcr": round(dividend_tax_gross, 2),
            "uk_tax_on_foreign_dividends": round(uk_tax_on_foreign_dividends, 2),
            "ftcr": round(relief, 2),
            "foreign_tax_withheld": round(withheld, 2),
            # Net of the tax already withheld; negative means a refund is due.
            "other_income_tax": round(other_income_tax, 2),
            "other_income_credit": round(report_other_credit, 2),
            "cgt_estimate": round(cgt_total, 2),
            "cgt_total": round(cgt_total, 2),
            "sa_cgt_at_pre_oct_rates": round(float(cgt["sa_cgt_at_pre_oct_rates"]), 2),
            "cgt_adjustment": round(float(cgt["cgt_adjustment"]), 2),
            "cgt_at_basic": round(cgt_at_basic, 2),
            "cgt_at_higher": round(cgt_at_higher, 2),
            "cgt_note": cgt_note,
            # Tax on investment income alone — the old headline, now a
            # sub-total, and taken from the bill's own computation so the two
            # figures on the page cannot drift apart over a rounding rule.
            # `sa_bill` is what the return will actually ask for, PAYE
            # under-collection included.
            "investment_only": round(float(sa["investment_only"]), 2),
            "sa_bill": round(float(sa["sa_bill"]), 2),
            "reconciled": sa["reconciled"],
        },
        "cgt": _cgt_view(cgt),
        "self_assessment": self_assessment.to_json(sa),
        "payments_on_account": {
            "required": poa["required"],
            "threshold": float(poa["threshold"]),
            "liability_excluding_cgt": round(float(poa["liability_excluding_cgt"]), 2),
            "over_threshold": poa["over_threshold"],
            "tax_collected_at_source": round(float(poa["tax_collected_at_source"]), 2),
            "percent_at_source": round(float(poa["percent_at_source"]), 2),
            "under_80_percent_at_source": poa["under_80_percent_at_source"],
            "each_instalment": round(float(poa["each_instalment"]), 2),
            # True when no P60 was entered, so PAYE was assumed to have
            # collected the right tax rather than checked against one.
            "assumed_paye": poa["assumed_paye"],
            "explain": poa["explain"],
        },
        "marginal": {
            "income_rate": marginal_rate,
            "effective_rate": effective_marginal,
        },
    }


def _cgt_view(cgt: dict) -> dict:
    """The CGT computation as floats, for the API."""
    return {
        "total_gain": round(float(cgt["total_gain"]), 2),
        "taxable_gain": round(float(cgt["taxable_gain"]), 2),
        "annual_exempt_amount": float(cgt["annual_exempt_amount"]),
        "losses": round(float(cgt["losses"]), 2),
        "cgt_total": round(float(cgt["cgt_total"]), 2),
        "sa_cgt_at_pre_oct_rates": round(float(cgt["sa_cgt_at_pre_oct_rates"]), 2),
        "cgt_adjustment": round(float(cgt["cgt_adjustment"]), 2),
        "split_applies": cgt["split_applies"],
        "dates_known": cgt["dates_known"],
        "change_date": cgt["change_date"],
        "has_pre_change_disposals": cgt["has_pre_change_disposals"],
        "needs_box_51_adjustment": cgt["needs_box_51_adjustment"],
        "adjustment_note": cgt["adjustment_note"],
        "buckets": [
            {
                "key": b["key"],
                "label": b["label"],
                "gain": round(float(b["gain"]), 2),
                "relief": round(float(b["relief"]), 2),
                "net": round(float(b["net"]), 2),
                "rounded": float(b["rounded"]),
                "at_basic": float(b["at_basic"]),
                "at_higher": float(b["at_higher"]),
                "basic_rate": float(b["basic_rate"]),
                "higher_rate": float(b["higher_rate"]),
                "tax": round(float(b["tax"]), 2),
            }
            for b in cgt["buckets"]
            if b["gain"] or b["net"]
        ],
    }
