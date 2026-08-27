"""The Self Assessment bill: the whole liability, not just the investment part.

The question this answers is "what will HMRC actually charge me for this year",
which for a PAYE employee is mostly not about investments at all. PAYE is an
estimate made from a tax code issued before the year began; when the code is
wrong — an allowance you are no longer entitled to, a benefit nobody coded —
the difference is collected through the return, and it can dwarf the tax on the
dividends and interest. The bill is:

    income tax liability on ALL income
  − tax deducted at source (every P60, plus tax withheld on other income)
  − foreign tax credit relief
  = income tax shortfall (negative means a refund)
  + capital gains tax
  − anything already paid to HMRC for the year
  = Self Assessment bill

The investment-only sub-total — savings + dividends + capital gains, less any
tax already paid on gains — is kept alongside it, because that is the figure
this app used to show as its headline and it is still worth seeing on its own.

Everything year-specific comes from `core.tax_years`; the tax rules themselves
(band stacking, the allowance taper, capital gains by disposal date, foreign
tax credit relief, the payments-on-account test) come from `core.estimator`, so
this module is assembly and explanation rather than arithmetic of its own.

Rounding runs through `estimator.round_for_tax` and defaults to HMRC's
behaviour, because matching the real bill is the point. The pence-precise
figures are computed alongside and carried as secondaries.

England/Northern Ireland and Wales only — see `core.tax_years` on Scotland.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from core import estimator, paye, tax_years
from core.estimator import ONE, ZERO, dec

# Below this the "tax deducted" on a P60 with real pay is almost certainly
# missing rather than genuinely nil, and treating it as nil would invent a
# five-figure shortfall.
_SUSPICIOUS_NIL_PAY = Decimal(1)


@dataclass
class Inputs:
    """Everything the bill needs. Every field is optional except the year:
    an empty set of inputs produces today's investment-only behaviour with the
    "no P60" caveat, which is exactly what should happen."""

    year: dict
    tax_year: int

    # Employment. Each row: {name, pay, tax_deducted, tax_code, student_loan_deducted}.
    # `pay` and `tax_deducted` are read off the P60 and never derived.
    employments: list[dict] = field(default_factory=list)
    benefits_in_kind: Decimal | float | int | str = 0

    # Other non-savings income: REIT property income distributions and
    # share-lending fees from the report, plus anything typed into the planner.
    other_non_savings_income: Decimal | float | int | str = 0
    other_non_savings_tax_deducted: Decimal | float | int | str = 0

    # Savings income, all of it. Foreign interest is a separate field so it can
    # never be quietly dropped from the total.
    uk_interest: Decimal | float | int | str = 0
    foreign_interest: Decimal | float | int | str = 0
    interest_distributions: Decimal | float | int | str = 0
    other_interest: Decimal | float | int | str = 0
    foreign_interest_tax: Decimal | float | int | str = 0

    # Dividends, gross. Foreign ones carry the withholding and the treaty cap.
    uk_dividends: Decimal | float | int | str = 0
    foreign_dividends: Decimal | float | int | str = 0
    foreign_dividend_tax: Decimal | float | int | str = 0
    foreign_dividend_treaty_relief: Decimal | float | int | str | None = None

    # Reliefs paid net, which extend the bands and reduce adjusted net income.
    pension_relief_at_source_net: Decimal | float | int | str = 0
    gift_aid_net: Decimal | float | int | str = 0

    # Capital gains: [{date, gain, exempt?, residential?}].
    disposals: list[dict] = field(default_factory=list)
    losses_brought_forward: Decimal | float | int | str = 0
    # Set when the taxable gain was typed in rather than computed from disposals.
    taxable_gain_override: Decimal | float | int | str | None = None
    reported_losses: Decimal | float | int | str | None = None
    entered_losses: Decimal | float | int | str | None = None

    # Already handed to HMRC for this year.
    payments_on_account_made: Decimal | float | int | str = 0
    tax_paid_on_gains: Decimal | float | int | str = 0

    student_loan_plan: str | None = None
    # Asked for so the estimate can say it is incomplete; not taxed here.
    self_employment_income: Decimal | float | int | str = 0

    rounding_mode: str = estimator.ROUNDING_HMRC


# ── Building the inputs from what the app already holds ───────────────────────

# Planner keys that carry a single employment, kept so planners saved before the
# employment section existed still place income in the right bands. They carry
# no tax deducted, so they produce the investment-only figure and the "enter
# your P60" caveat rather than a made-up reconciliation.
LEGACY_PAY_KEY = "employment_income"


def _num(inputs: dict, key: str) -> Decimal:
    return dec(inputs.get(key))


def employments_from_planner(inputs: dict) -> list[dict]:
    """The employment rows, from the repeatable P60 list or the legacy field.

    Rows with neither pay nor tax are dropped: an empty row the user added and
    never filled in should not look like a job that paid nothing."""
    rows = inputs.get("employments")
    if isinstance(rows, list) and rows:
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            has_pay = row.get("pay") not in (None, "")
            has_tax = row.get("tax_deducted") not in (None, "")
            if not has_pay and not has_tax:
                continue
            out.append(
                {
                    "name": row.get("name") or "Employment",
                    "pay": row.get("pay"),
                    "tax_deducted": row.get("tax_deducted"),
                    "tax_code": row.get("tax_code"),
                    "student_loan_deducted": row.get("student_loan_deducted"),
                }
            )
        if out:
            return out
    legacy = inputs.get(LEGACY_PAY_KEY)
    if legacy not in (None, ""):
        return [{"name": "Employment", "pay": legacy}]
    return []


def inputs_from_planner(planner: dict, year: dict, tax_year: int, invest: dict) -> Inputs:
    """Assemble the bill's inputs from the planner form and the year's report.

    The planner supplies what only you know (P60s, benefits, pension, what you
    have already paid); the report supplies the investment income it computed
    from your broker documents. Neither is asked for twice."""
    planner = planner or {}
    invest = invest or {}

    def from_invest(key: str) -> Decimal:
        return dec(invest.get(key))

    mode = planner.get("rounding_mode") or estimator.ROUNDING_HMRC
    return Inputs(
        year=year,
        tax_year=tax_year,
        employments=employments_from_planner(planner),
        benefits_in_kind=_num(planner, "benefits_in_kind"),
        # REIT property income distributions and share-lending fees are
        # non-savings income with tax already withheld; "other taxable income"
        # is whatever the planner was told about on top.
        other_non_savings_income=from_invest("other_income") + _num(planner, "other_income"),
        other_non_savings_tax_deducted=from_invest("other_income_tax"),
        uk_interest=from_invest("uk_interest"),
        foreign_interest=from_invest("foreign_interest"),
        interest_distributions=from_invest("interest_distributions"),
        other_interest=_num(planner, "other_interest"),
        uk_dividends=from_invest("uk_dividends"),
        foreign_dividends=from_invest("foreign_dividends"),
        foreign_dividend_tax=from_invest("foreign_dividend_tax"),
        foreign_dividend_treaty_relief=invest.get("foreign_dividend_treaty_relief"),
        pension_relief_at_source_net=_num(planner, "sipp_paid"),
        gift_aid_net=_num(planner, "gift_aid_paid"),
        disposals=invest.get("disposals") or [],
        taxable_gain_override=(invest.get("taxable_gain") if not invest.get("disposals") else None),
        reported_losses=invest.get("losses"),
        entered_losses=planner.get("entered_losses"),
        payments_on_account_made=_num(planner, "payments_on_account_made"),
        tax_paid_on_gains=_num(planner, "tax_paid_on_gains"),
        student_loan_plan=planner.get("student_loan_plan"),
        self_employment_income=_num(planner, "self_employment_income"),
        rounding_mode=mode if mode in estimator.ROUNDING_MODES else estimator.ROUNDING_HMRC,
    )


# ── Rounding ──────────────────────────────────────────────────────────────────


def _income(value, mode: str) -> Decimal:
    """An income source, rounded the way the bill will round it."""
    return estimator.round_for_tax(value, "income", mode)


# ── The computation ───────────────────────────────────────────────────────────


def compute(inputs: Inputs) -> dict:
    """The full bill, plus everything needed to explain and check it."""
    year = inputs.year
    mode = inputs.rounding_mode
    if mode not in estimator.ROUNDING_MODES:
        raise ValueError(f"Unknown rounding mode {mode!r}")

    emp = paye.employments_total(inputs.employments)
    warnings: list[str] = []

    # ── Income, each source rounded on its own ────────────────────────────────
    employment_pay = _income(emp["pay"], mode)
    benefits = _income(inputs.benefits_in_kind, mode)
    other_non_savings = _income(inputs.other_non_savings_income, mode)
    self_employment = dec(inputs.self_employment_income)
    non_savings = employment_pay + benefits + other_non_savings

    uk_interest = _income(inputs.uk_interest, mode)
    foreign_interest = _income(inputs.foreign_interest, mode)
    interest_distributions = _income(inputs.interest_distributions, mode)
    other_interest = _income(inputs.other_interest, mode)
    savings = uk_interest + foreign_interest + interest_distributions + other_interest

    uk_dividends = _income(inputs.uk_dividends, mode)
    foreign_dividends = _income(inputs.foreign_dividends, mode)
    dividends = uk_dividends + foreign_dividends

    total_income = non_savings + savings + dividends

    # ── Allowances and bands ─────────────────────────────────────────────────
    # Relief at source: HMRC has already added 25% to what you paid, and the
    # gross figure is what extends the bands and cuts adjusted net income.
    pension_gross = dec(inputs.pension_relief_at_source_net) / Decimal("0.8")
    gift_aid_gross = dec(inputs.gift_aid_net) / Decimal("0.8")
    band_extension = pension_gross + gift_aid_gross
    adjusted_net_income = max(ZERO, total_income - band_extension)

    personal_allowance = estimator.taper_allowance(
        dec(year["personal_allowance"]), dec(year["pa_taper_start"]), adjusted_net_income
    )
    basic_limit = dec(year["basic_band"]) + band_extension
    higher_limit = dec(year["higher_rate_limit"]) + band_extension

    # The allowance goes against non-savings income first, then savings, then
    # dividends — HMRC's order, and the one that leaves the taxpayer best off.
    allowance_left = personal_allowance
    taxable_non_savings = max(ZERO, non_savings - allowance_left)
    allowance_left = max(ZERO, allowance_left - non_savings)
    taxable_savings = max(ZERO, savings - allowance_left)
    allowance_left = max(ZERO, allowance_left - savings)
    taxable_dividends = max(ZERO, dividends - allowance_left)

    rates = year["income_rates"]
    ns_slices, floor = estimator.band_slices(
        taxable_non_savings, ZERO, basic_limit=basic_limit, higher_limit=higher_limit, rates=rates
    )
    non_savings_tax = estimator.slices_tax(ns_slices)

    # ── Savings ──────────────────────────────────────────────────────────────
    # The starting rate band shrinks £1 for £1 with non-savings income above the
    # personal allowance, and is gone entirely by ~£17,570 of salary. The
    # personal savings allowance is sized by the band the savings income lands
    # in: £1,000 basic, £500 higher, nil additional.
    starting_band = max(ZERO, dec(year["starting_rate_savings_band"]) - taxable_non_savings)
    savings_band = estimator.band_at(floor, basic_limit, higher_limit)
    psa = dec(year["psa"][savings_band])
    savings_at_zero = min(taxable_savings, starting_band + psa)
    floor += savings_at_zero
    sv_slices, floor = estimator.band_slices(
        taxable_savings - savings_at_zero,
        floor,
        basic_limit=basic_limit,
        higher_limit=higher_limit,
        rates=rates,
    )
    savings_tax = estimator.slices_tax(sv_slices)

    # ── Dividends ────────────────────────────────────────────────────────────
    # The dividend allowance is a 0% rate, not a deduction: it still occupies
    # band space. It goes to the UK dividends first, which leaves the foreign
    # ones charged and so lets their foreign tax credit be used rather than
    # wasted — the credit is capped at the UK tax on that same income.
    allowance_on_dividends = dividends - taxable_dividends
    uk_taxable_dividends = max(ZERO, uk_dividends - allowance_on_dividends)
    foreign_taxable_dividends = max(ZERO, taxable_dividends - uk_taxable_dividends)
    dividend_allowance = dec(year["dividend_allowance"])
    allowance_used = min(taxable_dividends, dividend_allowance)
    uk_allowance_used = min(uk_taxable_dividends, allowance_used)
    foreign_charged = max(ZERO, foreign_taxable_dividends - (allowance_used - uk_allowance_used))

    dividend_floor = floor + allowance_used
    charged_dividends = taxable_dividends - allowance_used
    dv_slices, floor = estimator.band_slices(
        charged_dividends,
        dividend_floor,
        basic_limit=basic_limit,
        higher_limit=higher_limit,
        rates=year["dividend_rates"],
    )
    dividend_tax_gross = estimator.slices_tax(dv_slices)
    # The foreign dividends sit at the top of the dividend stack, so the UK tax
    # on them is what that top slice costs.
    dv_without_foreign, _ = estimator.band_slices(
        max(ZERO, charged_dividends - foreign_charged),
        dividend_floor,
        basic_limit=basic_limit,
        higher_limit=higher_limit,
        rates=year["dividend_rates"],
    )
    uk_tax_on_foreign_dividends = dividend_tax_gross - estimator.slices_tax(dv_without_foreign)

    # ── Foreign tax credit relief ────────────────────────────────────────────
    # A credit against the tax, capped at the UK tax actually charged on that
    # income. Income sheltered by the dividend allowance bears no UK tax, so it
    # generates no relief however much was withheld abroad.
    treaty_cap = inputs.foreign_dividend_treaty_relief
    withheld_dividends = dec(inputs.foreign_dividend_tax)
    creditable_dividends = (
        min(withheld_dividends, dec(treaty_cap)) if treaty_cap is not None else withheld_dividends
    )
    ftcr_dividends = estimator.ftcr(
        gross=foreign_dividends,
        withheld=creditable_dividends,
        treaty_rate=ONE,
        uk_tax_on_income=uk_tax_on_foreign_dividends,
    )
    # Foreign interest: the savings slices are charged in stacking order, so the
    # UK tax on the foreign part is whatever the top of the savings stack costs.
    uk_tax_on_foreign_interest = _tax_on_top_of_savings(
        foreign_interest,
        taxable_savings=taxable_savings,
        savings_at_zero=savings_at_zero,
        slices=sv_slices,
    )
    ftcr_interest = estimator.ftcr(
        gross=foreign_interest,
        withheld=dec(inputs.foreign_interest_tax),
        treaty_rate=ONE,
        uk_tax_on_income=uk_tax_on_foreign_interest,
    )
    ftcr = ftcr_dividends + ftcr_interest

    income_tax_total = non_savings_tax + savings_tax + dividend_tax_gross

    # ── Tax already collected at source ──────────────────────────────────────
    # PAYE off the P60s, plus the 20% REITs withhold from property income
    # distributions. Never derived from a tax code — see core.paye.
    paye_deducted = dec(emp["tax_deducted"])
    other_tax_deducted = dec(inputs.other_non_savings_tax_deducted)
    tax_at_source = paye_deducted + other_tax_deducted

    reconciled = _has_p60(inputs.employments)

    # Non-savings income is stacked as one block, so the tax on the report's
    # other UK income (REIT property income distributions, share-lending fees)
    # is what the block would cost without it — the marginal slices at the top.
    other_income_gross_tax = _tax_on_other_income(
        other_non_savings,
        taxable_non_savings=taxable_non_savings,
        slices_total=non_savings_tax,
        basic_limit=basic_limit,
        higher_limit=higher_limit,
        rates=rates,
    )
    other_income_tax = other_income_gross_tax - other_tax_deducted
    # What is left is the tax on pay and benefits — the part PAYE was supposed
    # to collect.
    employment_tax = non_savings_tax - other_income_gross_tax

    # Without a P60 there is no way to know what PAYE collected. Treating it as
    # nil would turn a whole year's salary tax into an apparent shortfall and
    # produce a five-figure "bill", so the unreconciled case carries no
    # employment component at all: the figure is investment income only, and
    # `reconciled` plus a warning say so rather than passing off a guess.
    employment_shortfall = (employment_tax - paye_deducted) if reconciled else ZERO
    at_source_for_bill = tax_at_source if reconciled else employment_tax + other_tax_deducted
    income_tax_shortfall = income_tax_total - at_source_for_bill - ftcr

    # ── Capital gains ────────────────────────────────────────────────────────
    cgt = _capital_gains(inputs, year, basic_room=max(ZERO, basic_limit - floor))
    cgt_total = cgt["cgt_total"]

    # ── The bill ─────────────────────────────────────────────────────────────
    payments_made = dec(inputs.payments_on_account_made)
    gains_credit = dec(inputs.tax_paid_on_gains)
    already_paid = payments_made + gains_credit
    sa_bill = income_tax_shortfall + cgt_total - already_paid

    # What this app showed as its headline before the reconciliation existed:
    # the tax on investment income at the taxpayer's marginal position, with no
    # view of PAYE at all. It differs from the bill by the employment shortfall
    # and any payments on account already made.
    dividend_tax = dividend_tax_gross - ftcr_dividends
    interest_tax = savings_tax - ftcr_interest
    investment_only = interest_tax + dividend_tax + other_income_tax + cgt_total - gains_credit
    student_loan = _student_loan(
        inputs,
        earned=employment_pay + benefits + self_employment,
        unearned=savings + dividends + other_non_savings,
        deducted=dec(emp["student_loan_deducted"]),
    )

    # ── Payments on account ──────────────────────────────────────────────────
    # The balancing payment is the income tax shortfall (plus Class 4 NIC, which
    # this app does not compute because self-employment is out of scope).
    # Capital gains tax and student loan repayments are never part of it.
    #
    # It uses the same at-source figure as the bill, so the two can never
    # disagree: the P60 total when there is one, and the tax PAYE ought to have
    # collected when there is not.
    poa = estimator.payments_on_account(
        liability_excluding_cgt=income_tax_shortfall,
        tax_collected_at_source=at_source_for_bill,
        total_liability_excluding_cgt=income_tax_total,
    )
    poa["assumed_paye"] = not reconciled
    if not reconciled:
        poa["explain"] += (
            " No P60 was entered, so this assumes PAYE collected exactly the right tax on your "
            "salary. If it under-collected, the real balancing payment is larger than the figure "
            "above and the share collected at source is smaller — both tests move against you. "
            "Enter your P60 to have this computed rather than assumed."
        )

    explanation = paye.explain_shortfall(
        employments=inputs.employments,
        benefits=benefits,
        shortfall=employment_shortfall,
        year=year,
    )
    warnings.extend(
        _warnings(
            inputs,
            emp=emp,
            year=year,
            benefits=benefits,
            reconciled=reconciled,
            foreign_interest=foreign_interest,
            foreign_dividends=foreign_dividends,
            student_loan=student_loan,
            self_employment=self_employment,
        )
    )

    return {
        "reconciled": reconciled,
        "rounding_mode": mode,
        "tax_year": inputs.tax_year,
        "label": tax_years.label(inputs.tax_year),
        "due_date": tax_years.balancing_payment_due(inputs.tax_year).isoformat(),
        "income": {
            "employment_pay": employment_pay,
            "benefits_in_kind": benefits,
            "other_non_savings": other_non_savings,
            "non_savings": non_savings,
            "uk_interest": uk_interest,
            "foreign_interest": foreign_interest,
            "interest_distributions": interest_distributions,
            "other_interest": other_interest,
            "savings": savings,
            "uk_dividends": uk_dividends,
            "foreign_dividends": foreign_dividends,
            "dividends": dividends,
            "total": total_income,
            "adjusted_net_income": adjusted_net_income,
            "self_employment": self_employment,
        },
        "allowances": {
            "personal_allowance": personal_allowance,
            "personal_allowance_full": dec(year["personal_allowance"]),
            "psa": psa,
            "starting_rate_used": min(taxable_savings, starting_band),
            "dividend_allowance": dividend_allowance,
            "dividend_allowance_used": allowance_used,
            "band_extension": band_extension,
            "pension_gross": pension_gross,
            "gift_aid_gross": gift_aid_gross,
        },
        "bands": {
            "basic_limit": basic_limit,
            "higher_limit": higher_limit,
            "taxable_non_savings": taxable_non_savings,
            "taxable_savings": taxable_savings,
            "taxable_dividends": taxable_dividends,
            "taxable_income": taxable_non_savings + taxable_savings + taxable_dividends,
            "cgt_basic_room": max(ZERO, basic_limit - floor),
            "marginal_band": estimator.band_at(floor, basic_limit, higher_limit),
        },
        "income_tax": {
            "non_savings": non_savings_tax,
            "savings": savings_tax,
            "dividends_gross": dividend_tax_gross,
            "dividends": dividend_tax,
            "total": income_tax_total,
            "slices": {
                "non_savings": _slice_rows(ns_slices),
                "savings": _slice_rows(sv_slices),
                "dividends": _slice_rows(dv_slices),
            },
        },
        "at_source": {
            "paye": paye_deducted,
            "other_income": other_tax_deducted,
            "total": tax_at_source,
            "employments": emp["rows"],
        },
        "ftcr": {
            "total": ftcr,
            "dividends": ftcr_dividends,
            "interest": ftcr_interest,
            "foreign_dividend_tax": withheld_dividends,
            "foreign_interest_tax": dec(inputs.foreign_interest_tax),
            "uk_tax_on_foreign_dividends": uk_tax_on_foreign_dividends,
        },
        "income_tax_shortfall": income_tax_shortfall,
        "employment_shortfall": employment_shortfall,
        "cgt": cgt,
        "already_paid": {
            "total": already_paid,
            "payments_on_account_made": payments_made,
            "tax_paid_on_gains": gains_credit,
        },
        "sa_bill": sa_bill,
        "investment_only": investment_only,
        "investment_only_parts": {
            "interest": interest_tax,
            "dividends": dividend_tax,
            "other_income": other_income_tax,
            "cgt": cgt_total,
            "tax_paid_on_gains": gains_credit,
        },
        "student_loan": student_loan,
        "payments_on_account": poa,
        "tax_code_explanation": explanation,
        "warnings": warnings,
        "rows": _breakdown_rows(
            employment_shortfall=employment_shortfall,
            other_income_tax=other_income_tax,
            interest_tax=savings_tax,
            dividend_tax=dividend_tax_gross,
            cgt_total=cgt_total,
            ftcr=ftcr,
            already_paid=already_paid,
            sa_bill=sa_bill,
            reconciled=reconciled,
            psa=psa,
            dividend_allowance=dividend_allowance,
            year=year,
        ),
    }


# ── The API boundary ──────────────────────────────────────────────────────────


def _json(value):
    """Decimals to floats, rounded to the penny, everything else untouched.

    Money crosses the API as a number the frontend formats; the Decimals stay
    inside this module, where the precision matters."""
    if isinstance(value, Decimal):
        return round(float(value), 2)
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json(v) for v in value]
    return value


def to_json(result: dict) -> dict:
    """The computation as the API sends it."""
    return _json(result)


def compute_for(planner: dict, year: dict, invest: dict) -> dict:
    """The bill from the planner form and the year's investment summary."""
    return compute(inputs_from_planner(planner, year, year["tax_year"], invest))


# ── Pieces ────────────────────────────────────────────────────────────────────


def _has_p60(employments: list[dict]) -> bool:
    """Whether there is enough to reconcile PAYE: pay AND a tax figure that was
    actually entered. Pay on its own is not enough — treating a missing tax
    deducted as nil would turn the whole year's PAYE into a "shortfall"."""
    for e in employments:
        if dec(e.get("pay")) > ZERO and e.get("tax_deducted") not in (None, ""):
            return True
    return False


def _slice_rows(slices: list[dict]) -> list[dict]:
    return [
        {"band": s["band"], "amount": s["amount"], "rate": s["rate"], "tax": s["tax"]}
        for s in slices
    ]


def _tax_on_top_of_savings(
    amount: Decimal, *, taxable_savings: Decimal, savings_at_zero: Decimal, slices: list[dict]
) -> Decimal:
    """UK tax on the top `amount` of the savings stack — what a foreign-interest
    credit is capped at. Interest inside the starting rate band or the personal
    savings allowance bears no UK tax, so it earns no credit."""
    if amount <= ZERO or taxable_savings <= ZERO:
        return ZERO
    charged = max(ZERO, taxable_savings - savings_at_zero)
    top = min(dec(amount), charged)
    tax = ZERO
    left = top
    for s in reversed(slices):
        if left <= ZERO:
            break
        take = min(s["amount"], left)
        tax += take * s["rate"]
        left -= take
    return tax


def _tax_on_other_income(
    other: Decimal,
    *,
    taxable_non_savings: Decimal,
    slices_total: Decimal,
    basic_limit: Decimal,
    higher_limit: Decimal,
    rates: dict,
) -> Decimal:
    """Tax attributable to the report's other UK income (REIT property income
    distributions, share-lending fees): what the non-savings tax would drop by
    if that income were not there."""
    if other <= ZERO:
        return ZERO
    without, _ = estimator.band_slices(
        max(ZERO, taxable_non_savings - other),
        ZERO,
        basic_limit=basic_limit,
        higher_limit=higher_limit,
        rates=rates,
    )
    return slices_total - estimator.slices_tax(without)


def _capital_gains(inputs: Inputs, year: dict, *, basic_room: Decimal) -> dict:
    """Capital gains tax, charged at the rate for each disposal's date.

    Gains and losses are rounded HMRC's way whatever the income rounding mode:
    the same figures fill the whole-pound SA108 boxes, so a pence-precise gain
    would not match the return."""
    disposals = inputs.disposals
    if not disposals and inputs.taxable_gain_override is not None:
        # A typed-in taxable gain: put it back above the annual exempt amount so
        # the shared machinery charges it, dated after any mid-year rate change.
        change = estimator.rate_change(year)
        gain = dec(inputs.taxable_gain_override) + dec(year["cgt_allowance"])
        disposals = [{"date": change["date"] if change else "1900-01-01", "gain": gain}]
    return estimator.cgt_for_year(
        disposals,
        year,
        basic_room=basic_room,
        losses_brought_forward=inputs.losses_brought_forward,
    )


def _student_loan(
    inputs: Inputs, *, earned: Decimal, unearned: Decimal, deducted: Decimal
) -> dict | None:
    """The year's student loan repayment, if a plan was chosen.

    Unearned income under the £2,000 limit is ignored entirely; a penny over it
    and the whole amount counts, not just the excess (HMRC CSLM16035). Student
    loan repayments are collected through the return but are never part of a
    payment on account."""
    plan_key = (inputs.student_loan_plan or "").strip()
    if not plan_key or plan_key == "none":
        return None
    plans = tax_years.student_loan_plans(inputs.tax_year)
    if plans is None:
        return {
            "plan": plan_key,
            "available": False,
            "explain": (
                f"Student loan thresholds for {tax_years.label(inputs.tax_year)} are not in this "
                "app, so no repayment has been worked out. Add them to core/tax_years.py from "
                "the SL3 deduction tables for that year."
            ),
        }
    plan = plans.get(plan_key)
    if plan is None:
        return {
            "plan": plan_key,
            "available": False,
            "explain": f"{plan_key} is not a repayment plan for "
            f"{tax_years.label(inputs.tax_year)}.",
        }

    limit = dec(tax_years.STUDENT_LOAN_UNEARNED_LIMIT)
    counted_unearned = unearned if unearned > limit else ZERO
    income = earned + counted_unearned
    threshold = dec(plan["threshold"])
    rate = dec(plan["rate"])
    over = max(ZERO, income - threshold)
    due = estimator.round_gain_down(over * rate)
    balance = due - deducted
    return {
        "plan": plan_key,
        "available": True,
        "label": plan["label"],
        "threshold": threshold,
        "rate": rate,
        "income_counted": income,
        "earned": earned,
        "unearned": unearned,
        "unearned_counted": counted_unearned,
        "unearned_limit": limit,
        "total_due": due,
        "deducted_via_paye": deducted,
        "balance": balance,
        "explain": (
            f"{plan['label']}: {rate * estimator.HUNDRED:.0f}% of income over "
            f"£{threshold:,.0f}. "
            + (
                f"Unearned income of £{unearned:,.2f} is over the £{limit:,.0f} limit, so all "
                "of it counts, not just the excess. "
                if counted_unearned > ZERO
                else f"Unearned income of £{unearned:,.2f} is within the £{limit:,.0f} limit, "
                "so none of it counts. "
                if unearned > ZERO
                else ""
            )
            + f"On £{income:,.2f} that is £{due:,.2f} for the year, "
            + (
                f"of which £{deducted:,.2f} was already taken through payroll, leaving "
                f"£{balance:,.2f}."
                if deducted > ZERO
                else "none of it collected through payroll."
            )
            + " Student loan repayments are collected through the return but are never part "
            "of a payment on account."
        ),
    }


def _breakdown_rows(
    *,
    employment_shortfall: Decimal,
    other_income_tax: Decimal,
    interest_tax: Decimal,
    dividend_tax: Decimal,
    cgt_total: Decimal,
    ftcr: Decimal,
    already_paid: Decimal,
    sa_bill: Decimal,
    reconciled: bool,
    psa: Decimal,
    dividend_allowance: Decimal,
    year: dict,
) -> list[dict]:
    """The rows behind the headline, in the order the bill is built up. They sum
    to the total: employment shortfall + interest + dividends + gains, less
    foreign tax credit and anything already paid."""
    rows = [
        {
            "key": "employment",
            "label": "Employment tax shortfall",
            "amount": employment_shortfall,
            "explain": (
                "Income tax on your pay, benefits and other non-savings income, less the PAYE "
                "your employers actually deducted. PAYE works from a tax code set before the "
                "year began, so this is what it got wrong — positive means it under-collected "
                "and you owe the difference, negative means a refund."
                if reconciled
                else "No P60 figures entered, so PAYE has not been checked and nothing is counted "
                "here. That is an absence of information, not a finding that PAYE was right."
            ),
            "included": reconciled,
        },
        {
            "key": "other_income",
            "label": "Other UK income",
            "amount": other_income_tax,
            "explain": "REIT property income distributions and share-lending fees, at your "
            "marginal rate, less the 20% the REITs already withheld.",
            "included": other_income_tax != ZERO,
        },
        {
            "key": "interest",
            "label": "Interest",
            "amount": interest_tax,
            "explain": f"UK and foreign interest together, after your £{psa:,.0f} personal "
            "savings allowance. Foreign interest is taxable here even when the foreign bank "
            "took nothing off it, and it is the line most often left off a return.",
            "included": True,
        },
        {
            "key": "dividends",
            "label": "Dividends",
            "amount": dividend_tax,
            "explain": f"Dividends after the £{dividend_allowance:,.0f} dividend allowance, at "
            f"{dec(year['dividend_rates']['basic']) * estimator.HUNDRED:.2f}% / "
            f"{dec(year['dividend_rates']['higher']) * estimator.HUNDRED:.2f}% / "
            f"{dec(year['dividend_rates']['additional']) * estimator.HUNDRED:.2f}%. Foreign tax "
            "withheld comes off the tax below, not off this figure.",
            "included": True,
        },
        {
            "key": "cgt",
            "label": "Capital gains",
            "amount": cgt_total,
            "explain": f"Gains less losses and the £{dec(year['cgt_allowance']):,.0f} annual "
            "exempt amount, charged at the rate for each disposal's date. Capital gains tax is "
            "never part of a payment on account.",
            "included": True,
        },
        {
            "key": "ftcr",
            "label": "Foreign tax credit",
            "amount": -ftcr,
            "explain": "Foreign tax already withheld, credited against the UK bill — capped at "
            "the treaty rate and at the UK tax actually charged on that same income. Income "
            "sheltered by the dividend allowance bears no UK tax, so it earns no credit "
            "however much was withheld abroad.",
            "included": True,
        },
        {
            "key": "already_paid",
            "label": "Already paid",
            "amount": -already_paid,
            "explain": "Payments on account you have already made for this year, and any tax "
            "paid through HMRC's real-time capital gains service.",
            "included": True,
        },
    ]
    rows.append(
        {
            "key": "total",
            "label": "Total",
            "amount": sa_bill,
            "explain": "What the return should ask you for. A negative figure is a repayment.",
            "included": True,
            "total": True,
        }
    )
    return rows


def _warnings(
    inputs: Inputs,
    *,
    emp: dict,
    year: dict,
    benefits: Decimal,
    reconciled: bool,
    foreign_interest: Decimal,
    foreign_dividends: Decimal,
    student_loan: dict | None,
    self_employment: Decimal,
) -> list[str]:
    """Every check that can only be made once the figures are in one place."""
    out: list[str] = []

    if not reconciled:
        out.append(
            "This figure excludes any PAYE under- or over-collection on your salary. Enter your "
            "P60 figures to see the full bill — for an additional-rate taxpayer the PAYE "
            "shortfall is routinely larger than the whole investment-income bill."
        )

    for row in emp["rows"]:
        if row["pay"] > ZERO and row["tax_deducted"] < _SUSPICIOUS_NIL_PAY:
            out.append(
                f"{row['name']}: £{row['pay']:,.2f} of pay with no tax deducted. Unless the code "
                "was NT, check the P60 — a missing tax deducted turns the whole year's PAYE into "
                "an apparent shortfall."
            )

    typo = paye.tax_deducted_warning(employments=inputs.employments, benefits=benefits, year=year)
    if typo:
        out.append(typo)

    if dec(inputs.tax_paid_on_gains) > ZERO:
        out.append(
            "Only enter this if you actually paid CGT through HMRC's real-time service. Do not "
            "enter the taxable gain here — it is a tax figure, not a gain, and HMRC will credit "
            f"whatever you type as tax already paid. You entered "
            f"£{dec(inputs.tax_paid_on_gains):,.2f}."
        )

    if foreign_interest <= ZERO and foreign_dividends > ZERO:
        out.append(
            "You have foreign dividends but no foreign interest. Foreign currency cash at the "
            "same broker almost always pays interest, and it is taxable here even though no "
            "foreign tax was taken off it. Check before filing — this is the single easiest "
            "line to leave off a return."
        )

    loss_warning = _loss_rounding_warning(inputs)
    if loss_warning:
        out.append(loss_warning)

    if self_employment > ZERO:
        out.append(
            f"£{self_employment:,.2f} of self-employment or other untaxed income was entered. "
            "This app does not compute tax or Class 2/4 National Insurance on it, so the bill "
            "below is incomplete — treat it as a floor, not the answer."
        )

    if student_loan and not student_loan.get("available"):
        out.append(student_loan["explain"])

    if inputs.rounding_mode == estimator.ROUNDING_EXACT:
        out.append(
            "Pence-precise mode: HMRC rounds each income source down to the whole pound before "
            "charging tax, so this figure is not what will be charged. Switch back to HMRC "
            "rounding to match the real bill."
        )

    return out


def _loss_rounding_warning(inputs: Inputs) -> str | None:
    """HMRC rounds losses UP to the whole pound, in your favour. A loss entered
    as the rounded-down figure quietly costs up to £1 of relief and is the kind
    of thing nothing else on the return contradicts."""
    entered = inputs.entered_losses
    reported = inputs.reported_losses
    if entered in (None, "") or reported in (None, ""):
        return None
    entered = dec(entered)
    reported = dec(reported)
    if reported == reported.to_integral_value():
        return None  # nothing to round
    if entered == estimator.round_gain_down(reported):
        return (
            f"Your losses were entered as £{entered:,.0f}, which is £{reported:,.2f} rounded "
            f"down. HMRC rounds losses UP, in your favour: use "
            f"£{estimator.round_relief_up(reported):,.0f}."
        )
    return None
