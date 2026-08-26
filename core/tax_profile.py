"""Income-tax profile + estimated tax on investment income, from planner inputs
plus the report's investment summary.

Simplified rUK (non-Scottish) rules, stacked in HMRC order: non-savings →
savings → dividends → capital gains. Deliberate simplifications are marked
`# approx:` — each tip that relies on one states its assumption."""

from dataclasses import dataclass


@dataclass
class Slice:
    amount: float
    rate: float

    @property
    def tax(self) -> float:
        return self.amount * self.rate


def _taper_pa(personal_allowance: float, taper_start: float, adjusted_net_income: float) -> float:
    if adjusted_net_income <= taper_start:
        return personal_allowance
    return max(0.0, personal_allowance - (adjusted_net_income - taper_start) / 2)


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


def build_profile(inputs: dict, year: dict, invest: dict) -> dict:
    """inputs: planner form (floats, may be missing). invest: report summary
    {dividends_total, dividends_taxable, uk_interest, foreign_interest,
    taxable_gain, total_gain, gain_post_change (2024 only)} — zeros if absent."""

    def val(key: str) -> float:
        return float(inputs.get(key) or 0)

    employment = val("employment_income")  # P60 "pay" — already net of net-pay pension
    other_income = val("other_income")
    sipp_gross = val("sipp_paid") / 0.8  # relief at source: HMRC adds 25% of the net payment
    gift_aid_gross = val("gift_aid_paid") / 0.8

    savings = float(invest.get("uk_interest") or 0) + float(invest.get("foreign_interest") or 0)
    savings += val("other_interest")
    dividends = float(invest.get("dividends_total") or 0)

    non_savings = employment + other_income
    total_income = non_savings + savings + dividends
    adjusted_net_income = max(0.0, total_income - sipp_gross - gift_aid_gross)

    pa = _taper_pa(year["personal_allowance"], year["pa_taper_start"], adjusted_net_income)
    band_extension = sipp_gross + gift_aid_gross
    basic_top = year["basic_band"] + band_extension  # on taxable (post-PA) income
    additional_top = (year["additional_threshold"] - year["personal_allowance"]) + band_extension

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

    # Savings: starting rate band (0%) shrinks £-for-£ with taxable non-savings income,
    # then the PSA (0%) sized by the band the savings income falls into.
    starting_band = max(0.0, year["starting_rate_savings_band"] - taxable_non_savings)
    band_at_floor = (
        "basic" if floor < basic_top else "higher" if floor < additional_top else "additional"
    )
    psa = year["psa"][band_at_floor]
    savings_at_zero = min(taxable_savings, starting_band + psa)
    floor += savings_at_zero
    sv_slices, floor = _band_slices(
        taxable_savings - savings_at_zero, floor, basic_top, additional_top, year["income_rates"]
    )

    # Dividends: allowance is taxed at 0% but still occupies band space
    div_allowance_used = min(taxable_dividends, year["dividend_allowance"])
    floor += div_allowance_used
    dv_slices, floor = _band_slices(
        taxable_dividends - div_allowance_used,
        floor,
        basic_top,
        additional_top,
        year["dividend_rates"],
    )

    taxable_income_total = taxable_non_savings + taxable_savings + taxable_dividends

    # CGT on shares: gains stack on top of taxable income
    taxable_gain = float(invest.get("taxable_gain") or 0)
    basic_room = max(0.0, basic_top - taxable_income_total)
    cgt_rates = year["cgt_rates_shares"]
    cgt_at_basic = min(taxable_gain, basic_room)
    cgt_at_higher = taxable_gain - cgt_at_basic
    cgt_estimate = cgt_at_basic * cgt_rates["basic"] + cgt_at_higher * cgt_rates["higher"]
    cgt_note = None
    if year.get("cgt_mid_year_change"):
        cgt_note = (
            "This year had a mid-year CGT rate change — the estimate uses the "
            "post-change rates; the exact split depends on disposal dates "
            "(see the report's rate-change section)."
        )

    savings_tax = sum(s.tax for s in sv_slices)
    dividend_tax = sum(s.tax for s in dv_slices)
    income_tax_total = sum(s.tax for s in ns_slices) + savings_tax + dividend_tax

    if taxable_income_total > basic_top:
        marginal_band = "additional" if taxable_income_total > additional_top else "higher"
    else:
        marginal_band = "basic"
    marginal_rate = year["income_rates"][marginal_band]
    in_pa_taper = year["pa_taper_start"] < adjusted_net_income <= year["additional_threshold"]
    # approx: inside the taper each £1 of extra income also costs 50p of PA → ~60%
    effective_marginal = 0.60 if in_pa_taper else marginal_rate

    return {
        "income": {
            "non_savings": non_savings,
            "savings": savings,
            "dividends": dividends,
            "total": total_income,
            "adjusted_net_income": adjusted_net_income,
        },
        "allowances": {
            "personal_allowance": pa,
            "psa": psa,
            "psa_used": min(taxable_savings, psa),
            "starting_rate_used": min(taxable_savings, starting_band),
            "dividend_allowance": year["dividend_allowance"],
            "cgt_allowance": year["cgt_allowance"],
        },
        "bands": {
            "basic_top": basic_top,
            "additional_top": additional_top,
            "taxable_income": taxable_income_total,
            "marginal_band": marginal_band,
            "in_pa_taper": in_pa_taper,
        },
        "tax": {
            "income_tax_total": round(income_tax_total, 2),
            "savings_tax": round(savings_tax, 2),
            "dividend_tax": round(dividend_tax, 2),
            "cgt_estimate": round(cgt_estimate, 2),
            "cgt_at_basic": round(cgt_at_basic, 2),
            "cgt_at_higher": round(cgt_at_higher, 2),
            "cgt_note": cgt_note,
        },
        "marginal": {
            "income_rate": marginal_rate,
            "effective_rate": effective_marginal,
        },
    }
