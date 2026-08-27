"""Per-tax-year constants. Keyed by the tax year's starting calendar year
(2025 = 2025/26, i.e. 6 Apr 2025 – 5 Apr 2026).

All figures verified against gov.uk as of Aug 2026. SA box numbers follow the
2024/25 forms (SA108 "Listed shares and securities", SA100 TR3) — re-verify
against the actual form PDF when a new year's forms are published (yearly
maintenance task, see docs/plan/00-overview.md).

Sources for the income tax figures: gov.uk "Income Tax rates and Personal
Allowances" and "Rates and thresholds for employers"; the band limits are
ITA 2007 s10 (basic rate limit, higher rate limit) and s35 (the allowance) with
the taper in s35(2)-(3). Student loan thresholds: gov.uk "Student and
Postgraduate Loan deduction tables" (SL3) for each year.

England/Northern Ireland (and Wales, which uses the same rates) only —
Scottish income tax has five bands of its own and is not modelled. A Scottish
taxpayer's savings and dividend income still uses the rates here, but their
non-savings income does not, so the figures would be wrong for them."""

from datetime import date

# Income tax (rUK, not Scottish rates)
_COMMON = {
    "personal_allowance": 12570,
    "pa_taper_start": 100000,  # PA shrinks £1 per £2 of adjusted net income above this
    "basic_band": 37700,  # taxable income above PA taxed at basic rate up to this
    # ITA 2007 s10: the additional rate starts above this much *taxable* income,
    # i.e. income already net of the personal allowance. It is not the standard
    # allowance plus the higher rate band — when the allowance has been tapered
    # away the two differ, and using the wrong one misplaces ~£12,570 of a
    # £220k salary between the 40% and 45% bands (about £628 of tax).
    "higher_rate_limit": 125140,
    # The gross income at which the tapered allowance reaches nil
    # (pa_taper_start + 2 x personal_allowance). Equal to higher_rate_limit by
    # arithmetic coincidence in every year so far — kept separate because they
    # answer different questions.
    "additional_threshold": 125140,
    "income_rates": {"basic": 0.20, "higher": 0.40, "additional": 0.45},
    "dividend_rates": {"basic": 0.0875, "higher": 0.3375, "additional": 0.3935},
    "psa": {"basic": 1000, "higher": 500, "additional": 0},
    "starting_rate_savings_band": 5000,
    "isa_allowance": 20000,
    "pension_aa": 60000,
    "pension_taper_adjusted_income": 260000,
    "pension_taper_threshold_income": 200000,
    "pension_aa_min": 10000,
}

YEARS: dict[int, dict] = {
    2022: {
        **_COMMON,
        "cgt_allowance": 12300,
        "dividend_allowance": 2000,
        "cgt_rates_shares": {"basic": 0.10, "higher": 0.20},
        "cgt_rates_residential": {"basic": 0.18, "higher": 0.28},
        "pension_aa": 40000,
        "pension_taper_adjusted_income": 240000,
        "pension_aa_min": 4000,
    },
    2023: {
        **_COMMON,
        "cgt_allowance": 6000,
        "dividend_allowance": 1000,
        "cgt_rates_shares": {"basic": 0.10, "higher": 0.20},
        "cgt_rates_residential": {"basic": 0.18, "higher": 0.28},
    },
    2024: {
        **_COMMON,
        "cgt_allowance": 3000,
        "dividend_allowance": 500,
        # Rates changed mid-year at Autumn Budget 2024: disposals before
        # 30 Oct 2024 at 10%/20%, on or after at 18%/24%.
        "cgt_rates_shares": {"basic": 0.18, "higher": 0.24},
        # Residential property was already 18%/24% from 6 Apr 2024, so it does
        # not move on 30 October and stays in its own bucket all year.
        "cgt_rates_residential": {"basic": 0.18, "higher": 0.24},
        "cgt_mid_year_change": {
            "date": "2024-10-30",
            "rates_before": {"basic": 0.10, "higher": 0.20},
        },
    },
    2025: {
        **_COMMON,
        "cgt_allowance": 3000,
        "dividend_allowance": 500,
        "cgt_rates_shares": {"basic": 0.18, "higher": 0.24},
        "cgt_rates_residential": {"basic": 0.18, "higher": 0.24},
    },
    2026: {
        **_COMMON,
        "cgt_allowance": 3000,
        "dividend_allowance": 500,
        "cgt_rates_shares": {"basic": 0.18, "higher": 0.24},
        "cgt_rates_residential": {"basic": 0.18, "higher": 0.24},
    },
}

# Each year's constants carry the year they belong to, so anything handed a
# constants dict knows which year it is looking at without it being threaded
# through as a second argument alongside.
for _year, _constants in YEARS.items():
    _constants["tax_year"] = _year


def get_year(tax_year: int) -> dict | None:
    return YEARS.get(tax_year)


# Pension annual-allowance rules for years YEARS doesn't cover: carry-forward
# reaches 3 years back from the selected year, and a prior year's own excess can
# reach 3 further. Threshold-income limit = adjusted-income limit − standard
# allowance (FA 2004 s228ZA(3)). Sources: s228, s228ZA; HMRC PTM057100.
_PENSION_HISTORY = (
    (
        range(2016, 2020),
        {"aa": 40000, "threshold_income": 110000, "adjusted_income": 150000, "aa_min": 10000},
    ),
    (
        range(2020, 2023),
        {"aa": 40000, "threshold_income": 200000, "adjusted_income": 240000, "aa_min": 4000},
    ),
)


def pension_rules(tax_year: int) -> dict | None:
    """Annual allowance and taper parameters for the year, or None if unknown.

    Keys: aa (standard allowance), threshold_income and adjusted_income (taper
    applies only when BOTH are exceeded), aa_min (the tapered floor)."""
    y = YEARS.get(tax_year)
    if y:
        return {
            "aa": y["pension_aa"],
            "threshold_income": y["pension_taper_threshold_income"],
            "adjusted_income": y["pension_taper_adjusted_income"],
            "aa_min": y["pension_aa_min"],
        }
    for years, rules in _PENSION_HISTORY:
        if tax_year in years:
            return dict(rules)
    return None


# Student and postgraduate loan repayment thresholds, by tax year. Rate is a
# share of income above the threshold: 9% for the undergraduate plans, 6% for
# the postgraduate loan (plan 3). Sources: gov.uk SL3 "Student and Postgraduate
# Loan deduction tables" for 2023-24, 2024-25, 2025-26 and 2026-27.
#
# 2022/23 is deliberately absent: the app's own year table reaches back to it,
# but the Plan 1 and Plan 4 thresholds for that year could not be confirmed
# against a primary source, and a guessed threshold produces a wrong repayment
# rather than an obvious gap. `student_loan_plans` returns None for it, and the
# computation says so instead of inventing a figure.
STUDENT_LOAN_PLANS: dict[int, dict[str, dict]] = {
    2023: {
        "plan_1": {"label": "Plan 1", "threshold": 22015, "rate": 0.09},
        "plan_2": {"label": "Plan 2", "threshold": 27295, "rate": 0.09},
        "plan_4": {"label": "Plan 4 (Scotland)", "threshold": 27660, "rate": 0.09},
        "postgraduate": {"label": "Postgraduate loan", "threshold": 21000, "rate": 0.06},
    },
    2024: {
        "plan_1": {"label": "Plan 1", "threshold": 24990, "rate": 0.09},
        "plan_2": {"label": "Plan 2", "threshold": 27295, "rate": 0.09},
        "plan_4": {"label": "Plan 4 (Scotland)", "threshold": 31395, "rate": 0.09},
        # Plan 5 loans exist from 2023 but nobody entered repayment before
        # April 2026, so an earlier year's figure would never be collected.
        "postgraduate": {"label": "Postgraduate loan", "threshold": 21000, "rate": 0.06},
    },
    2025: {
        "plan_1": {"label": "Plan 1", "threshold": 26065, "rate": 0.09},
        "plan_2": {"label": "Plan 2", "threshold": 28470, "rate": 0.09},
        "plan_4": {"label": "Plan 4 (Scotland)", "threshold": 32745, "rate": 0.09},
        "postgraduate": {"label": "Postgraduate loan", "threshold": 21000, "rate": 0.06},
    },
    2026: {
        "plan_1": {"label": "Plan 1", "threshold": 26900, "rate": 0.09},
        "plan_2": {"label": "Plan 2", "threshold": 29385, "rate": 0.09},
        "plan_4": {"label": "Plan 4 (Scotland)", "threshold": 33795, "rate": 0.09},
        "plan_5": {"label": "Plan 5", "threshold": 25000, "rate": 0.09},
        "postgraduate": {"label": "Postgraduate loan", "threshold": 21000, "rate": 0.06},
    },
}

# Unearned income (interest, dividends, property) is ignored for student loan
# repayments up to this much; go a penny over and the WHOLE amount counts, not
# just the excess. HMRC CSLM16035.
STUDENT_LOAN_UNEARNED_LIMIT = 2000


def student_loan_plans(tax_year: int) -> dict[str, dict] | None:
    """Repayment plans available for the year, or None if the thresholds for
    that year have not been verified."""
    plans = STUDENT_LOAN_PLANS.get(tax_year)
    return {k: dict(v) for k, v in plans.items()} if plans else None


def configured_years() -> list[int]:
    """Tax years with constants, ascending — the only years the UI offers."""
    return sorted(YEARS)


def tax_year_of(d: date) -> int:
    """The tax year a calendar date falls in (6 Apr Y – 5 Apr Y+1 -> Y)."""
    return d.year if d >= date(d.year, 4, 6) else d.year - 1


def tax_year_start(tax_year: int) -> date:
    return date(tax_year, 4, 6)


def tax_year_end(tax_year: int) -> date:
    return date(tax_year + 1, 4, 5)


def filing_deadline(tax_year: int) -> date:
    """Online Self Assessment deadline for the year."""
    return date(tax_year + 2, 1, 31)


def balancing_payment_due(tax_year: int) -> date:
    """When the year's balancing payment has to reach HMRC. The same 31 January
    as the filing deadline, and named separately because it is the date the bill
    is due rather than the date the return is due."""
    return filing_deadline(tax_year)


def label(tax_year: int) -> str:
    return f"{tax_year}/{(tax_year + 1) % 100:02d}"
