"""Per-tax-year constants. Keyed by the tax year's starting calendar year
(2025 = 2025/26, i.e. 6 Apr 2025 – 5 Apr 2026).

All figures verified against gov.uk as of Aug 2026. SA box numbers follow the
2024/25 forms (SA108 "Listed shares and securities", SA100 TR3) — re-verify
against the actual form PDF when a new year's forms are published (yearly
maintenance task, see docs/plan/00-overview.md)."""

from datetime import date

# Income tax (rUK, not Scottish rates)
_COMMON = {
    "personal_allowance": 12570,
    "pa_taper_start": 100000,  # PA shrinks £1 per £2 of adjusted net income above this
    "basic_band": 37700,  # taxable income above PA taxed at basic rate up to this
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


def label(tax_year: int) -> str:
    return f"{tax_year}/{(tax_year + 1) % 100:02d}"
