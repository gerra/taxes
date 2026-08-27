"""Per-tax-year constants. Keyed by the tax year's starting calendar year
(2025 = 2025/26, i.e. 6 Apr 2025 – 5 Apr 2026).

Every figure in `YEARS` was checked against gov.uk on 27 Aug 2026, year by year,
and each year carries the URLs it was checked against in its own `sources`
tuple — those URLs are the record, not a memory of what the numbers "usually
are". Two things this audit caught, both of which had produced wrong bills:

* 2022/23's additional rate starts above £150,000 of taxable income, not
  £125,140. The £125,140 threshold applies from 6 April 2023 only. Sharing one
  "higher rate limit" across every year had put 2022/23 at £125,140, which
  overstated a £127,720 salary's tax by £129 and, worse, classified the taxpayer
  as additional rate — costing them the £500 personal savings allowance and
  charging dividends at 39.35% instead of 33.75%.
* 2026/27's dividend rates rise 2 percentage points to 10.75% / 35.75%, with the
  additional rate unchanged at 39.35% (Budget 2025). The table had carried the
  2025/26 rates forward.

So: no year inherits an audited figure from another year. The allowances, the
band limits, the rates and the CGT figures are spelled out per year even where
they happen to be identical, because it was the sharing that hid the error. Only
plumbing that is genuinely year-independent (the ISA allowance, the pension
annual allowance parameters, the savings starting-rate band) sits in `_COMMON`,
and any year that moves one overrides it.

`_self_check()` runs at import and raises `TaxTableError` if the table is
internally inconsistent — a negative allowance, a personal allowance that tapers
away above the additional rate threshold, CGT rate periods that leave a gap in
the year. A wrong bill is much easier to ship than a broken import.

Which band a taxpayer is in is not decided anywhere but here: `bands_for(year,
band_extension)` returns a `Bands`, and the personal savings allowance, the
dividend rate, the income tax rate and the CGT rate are all read off the band it
derives. Nothing outside this module compares an amount against a threshold.

SA box numbers follow the 2024/25 forms (SA108 "Listed shares and securities",
SA100 TR3) — re-verify against the actual form PDF when a new year's forms are
published (yearly maintenance task, see docs/plan/00-overview.md).

The band limits are ITA 2007 s10 (basic rate limit, higher rate limit) and s35
(the allowance) with the taper in s35(2)-(3); the dividend nil rate is s13A.
Student loan thresholds: gov.uk "Student and Postgraduate Loan deduction
tables" (SL3) for each year.

England/Northern Ireland (and Wales, which uses the same rates) only —
Scottish income tax has five bands of its own and is not modelled. A Scottish
taxpayer's savings and dividend income still uses the rates here, but their
non-savings income does not, so the figures would be wrong for them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


class TaxTableError(RuntimeError):
    """The year table contradicts itself. Raised at import by `_self_check`."""


def _dec(value) -> Decimal:
    """Local Decimal conversion. This module is the leaf everything else imports,
    so it deliberately depends on nothing of ours — `estimator.dec` is the same
    function on the other side of that line."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


# ── Band names ────────────────────────────────────────────────────────────────
#
# The three rate bands, in stacking order. Every per-band table below is keyed
# by these, and `Bands.band_at` is the only thing that decides which one an
# amount is in.
BASIC = "basic"
HIGHER = "higher"
ADDITIONAL = "additional"
BAND_ORDER = (BASIC, HIGHER, ADDITIONAL)

# ── Rate sets, named by when they took effect ─────────────────────────────────
#
# Named rather than inlined so a year's entry says which regime it is in, and so
# a change of rates is one new constant referenced by the years it applies to.

# Non-savings and savings income. Unchanged across every year in this table.
# Savings rates rise 2pp from April 2027, which is past the last year here.
_INCOME_RATES = {BASIC: 0.20, HIGHER: 0.40, ADDITIONAL: 0.45}

# Dividends, from 6 Apr 2022 (Autumn Budget 2021: +1.25pp on each rate).
_DIVIDEND_RATES_2022 = {BASIC: 0.0875, HIGHER: 0.3375, ADDITIONAL: 0.3935}
# Dividends, from 6 Apr 2026 (Budget 2025: +2pp on the ordinary and upper rates;
# the additional rate is left where it is).
_DIVIDEND_RATES_2026 = {BASIC: 0.1075, HIGHER: 0.3575, ADDITIONAL: 0.3935}

# Personal savings allowance by band. £1,000 / £500 / nil since it began in
# 2016/17 and unchanged in every year here.
_PSA = {BASIC: 1000, HIGHER: 500, ADDITIONAL: 0}

# CGT rates on shares and other assets.
_CGT_SHARES_PRE_2024 = {BASIC: 0.10, HIGHER: 0.20}
_CGT_SHARES_FROM_30_OCT_2024 = {BASIC: 0.18, HIGHER: 0.24}
# Residential property (and carried interest) had its own higher pair until
# 5 Apr 2024, then joined the 18%/24% pair a rate change early.
_CGT_RESIDENTIAL_PRE_2024 = {BASIC: 0.18, HIGHER: 0.28}
_CGT_RESIDENTIAL_FROM_2024 = {BASIC: 0.18, HIGHER: 0.24}

# gov.uk pages the whole table is checked against. Each year names the ones that
# carry its figures; they are listed once here so the URLs cannot drift apart.
_SRC_INCOME_TAX = (
    "https://www.gov.uk/government/publications/rates-and-allowances-income-tax/"
    "income-tax-rates-and-allowances-current-and-past"
)
_SRC_EMPLOYERS_2022 = "https://www.gov.uk/guidance/rates-and-thresholds-for-employers-2022-to-2023"
_SRC_ADDITIONAL_RATE_2023 = (
    "https://www.gov.uk/government/publications/lowering-of-the-additional-rate-threshold/"
    "income-tax-additional-rate-threshold-from-6-april-2023"
)
_SRC_DIVIDEND_ALLOWANCE = (
    "https://www.gov.uk/government/publications/reduction-of-the-dividend-allowance/"
    "income-tax-reducing-the-dividend-allowance"
)
_SRC_DIVIDEND_RATES_2026 = (
    "https://www.gov.uk/government/publications/changes-to-tax-rates-for-property-savings-"
    "dividend-income/changes-to-tax-rates-for-property-savings-dividend-income"
)
_SRC_SAVINGS = "https://www.gov.uk/apply-tax-free-interest-on-savings"
_SRC_CGT = (
    "https://www.gov.uk/government/publications/rates-and-allowances-capital-gains-tax/"
    "capital-gains-tax-rates-and-annual-tax-free-allowances"
)

# Year-independent plumbing. Nothing audited above lives here: a figure in
# `_COMMON` is one that carries no year-specific risk, and any year that moves
# one overrides it in its own entry.
_COMMON = {
    # Savings starting rate: £5,000 at 0%, shrinking £1 for £1 with non-savings
    # income above the personal allowance, so it is gone by £17,570 of income.
    "starting_rate_savings_band": 5000,
    "isa_allowance": 20000,
    "pension_aa": 60000,
    "pension_taper_adjusted_income": 260000,
    "pension_taper_threshold_income": 200000,
    "pension_aa_min": 10000,
}

YEARS: dict[int, dict] = {
    # ── 2022/23 ── 6 Apr 2022 to 5 Apr 2023 ──────────────────────────────────
    # Additional rate above £150,000 of taxable income: the employers' guidance
    # for this year is explicit ("45% on annual earnings above £150,000"), and
    # the threshold only drops to £125,140 on 6 Apr 2023 (see the 2023/24 entry
    # and _SRC_ADDITIONAL_RATE_2023). The personal allowance still runs out at
    # £125,140 of income — in this year alone the two are different figures.
    # Dividends: allowance still £2,000 (cut to £1,000 from 6 Apr 2023), rates
    # 8.75/33.75/39.35 from 6 Apr 2022. CGT annual exempt amount £12,300, shares
    # 10%/20%, residential 18%/28%.
    2022: {
        **_COMMON,
        "sources": (_SRC_EMPLOYERS_2022, _SRC_DIVIDEND_ALLOWANCE, _SRC_SAVINGS, _SRC_CGT),
        "personal_allowance": 12570,
        "pa_taper_start": 100000,
        "pa_taper_end": 125140,
        "basic_band": 37700,
        "higher_rate_limit": 150000,
        "income_rates": _INCOME_RATES,
        "dividend_rates": _DIVIDEND_RATES_2022,
        "dividend_allowance": 2000,
        "psa": _PSA,
        "cgt_allowance": 12300,
        "cgt_rates_shares": _CGT_SHARES_PRE_2024,
        "cgt_rates_residential": _CGT_RESIDENTIAL_PRE_2024,
        "pension_aa": 40000,
        "pension_taper_adjusted_income": 240000,
        "pension_aa_min": 4000,
    },
    # ── 2023/24 ── 6 Apr 2023 to 5 Apr 2024 ──────────────────────────────────
    # The additional rate threshold drops to £125,140 from 6 Apr 2023 — the
    # point at which the tapered personal allowance reaches nil, which is why
    # the two figures coincide from here on. Dividend allowance £1,000; rates
    # unchanged. CGT annual exempt amount £6,000, rates unchanged.
    2023: {
        **_COMMON,
        "sources": (_SRC_INCOME_TAX, _SRC_ADDITIONAL_RATE_2023, _SRC_DIVIDEND_ALLOWANCE, _SRC_CGT),
        "personal_allowance": 12570,
        "pa_taper_start": 100000,
        "pa_taper_end": 125140,
        "basic_band": 37700,
        "higher_rate_limit": 125140,
        "income_rates": _INCOME_RATES,
        "dividend_rates": _DIVIDEND_RATES_2022,
        "dividend_allowance": 1000,
        "psa": _PSA,
        "cgt_allowance": 6000,
        "cgt_rates_shares": _CGT_SHARES_PRE_2024,
        "cgt_rates_residential": _CGT_RESIDENTIAL_PRE_2024,
    },
    # ── 2024/25 ── 6 Apr 2024 to 5 Apr 2025 ──────────────────────────────────
    # Dividend allowance £500. CGT annual exempt amount £3,000, and the rates on
    # shares change part-way through the year (Autumn Budget 2024): 10%/20% for
    # disposals before 30 Oct 2024, 18%/24% on or after. Residential property
    # moved to 18%/24% on 6 Apr 2024, so it does not move again on 30 October
    # and stays in its own bucket all year.
    2024: {
        **_COMMON,
        "sources": (_SRC_INCOME_TAX, _SRC_DIVIDEND_ALLOWANCE, _SRC_CGT),
        "personal_allowance": 12570,
        "pa_taper_start": 100000,
        "pa_taper_end": 125140,
        "basic_band": 37700,
        "higher_rate_limit": 125140,
        "income_rates": _INCOME_RATES,
        "dividend_rates": _DIVIDEND_RATES_2022,
        "dividend_allowance": 500,
        "psa": _PSA,
        "cgt_allowance": 3000,
        "cgt_rates_shares": _CGT_SHARES_FROM_30_OCT_2024,
        "cgt_rates_residential": _CGT_RESIDENTIAL_FROM_2024,
        "cgt_mid_year_change": {
            "date": "2024-10-30",
            "rates_before": _CGT_SHARES_PRE_2024,
        },
    },
    # ── 2025/26 ── 6 Apr 2025 to 5 Apr 2026 ──────────────────────────────────
    # Nothing in this table moves: thresholds frozen, dividend allowance £500,
    # CGT £3,000 at 18%/24% for the whole year.
    2025: {
        **_COMMON,
        "sources": (_SRC_INCOME_TAX, _SRC_CGT),
        "personal_allowance": 12570,
        "pa_taper_start": 100000,
        "pa_taper_end": 125140,
        "basic_band": 37700,
        "higher_rate_limit": 125140,
        "income_rates": _INCOME_RATES,
        "dividend_rates": _DIVIDEND_RATES_2022,
        "dividend_allowance": 500,
        "psa": _PSA,
        "cgt_allowance": 3000,
        "cgt_rates_shares": _CGT_SHARES_FROM_30_OCT_2024,
        "cgt_rates_residential": _CGT_RESIDENTIAL_FROM_2024,
    },
    # ── 2026/27 ── 6 Apr 2026 to 5 Apr 2027 ──────────────────────────────────
    # Dividend rates rise 2pp to 10.75% (ordinary) and 35.75% (upper) from
    # 6 Apr 2026; the additional rate stays at 39.35%. Savings and property
    # rates rise 2pp a year later, from 6 Apr 2027, which is outside this table
    # — the year that gets added next has to carry them.
    2026: {
        **_COMMON,
        "sources": (_SRC_INCOME_TAX, _SRC_DIVIDEND_RATES_2026, _SRC_CGT),
        "personal_allowance": 12570,
        "pa_taper_start": 100000,
        "pa_taper_end": 125140,
        "basic_band": 37700,
        "higher_rate_limit": 125140,
        "income_rates": _INCOME_RATES,
        "dividend_rates": _DIVIDEND_RATES_2026,
        "dividend_allowance": 500,
        "psa": _PSA,
        "cgt_allowance": 3000,
        "cgt_rates_shares": _CGT_SHARES_FROM_30_OCT_2024,
        "cgt_rates_residential": _CGT_RESIDENTIAL_FROM_2024,
    },
}


# Each year's constants carry the year they belong to, so anything handed a
# constants dict knows which year it is looking at without it being threaded
# through as a second argument alongside.
for _year, _constants in YEARS.items():
    _constants["tax_year"] = _year


def get_year(tax_year: int) -> dict | None:
    return YEARS.get(tax_year)


# ── Which band an amount is in ────────────────────────────────────────────────


def taper_allowance(year: dict, adjusted_net_income) -> Decimal:
    """The personal allowance after the ITA 2007 s35(2)-(3) taper: £1 less for
    every £2 of adjusted net income above the year's threshold, nil once the
    allowance is used up (which is what `pa_taper_end` records)."""
    pa = _dec(year["personal_allowance"])
    over = _dec(adjusted_net_income) - _dec(year["pa_taper_start"])
    if over <= 0:
        return pa
    return max(Decimal(0), pa - over / 2)


@dataclass(frozen=True)
class Bands:
    """One taxpayer's band boundaries for one year, and everything read off
    them.

    This is the only place in the app where an amount is compared against a
    threshold. Everything that depends on which band a figure lands in — the
    personal savings allowance, the dividend rate, the income tax rate, the CGT
    rate, whether the personal allowance is tapering — comes from here, so a
    year whose thresholds differ (2022/23's £150,000 additional rate) cannot be
    right in one calculation and wrong in another.

    `extension` is the gross of relief-at-source pension contributions and Gift
    Aid: it widens the basic and higher rate bands (ITA 2007 s414, s192 FA 2004)
    without touching the personal allowance taper, which works on adjusted net
    income that is already net of the same amount.

    Both limits are measured in TAXABLE income — income after allowances — not
    in gross pay, and neither moves down when the allowance tapers away."""

    year: dict
    extension: Decimal = Decimal(0)

    @property
    def basic_limit(self) -> Decimal:
        """Taxable income up to here is charged at the basic rate."""
        return _dec(self.year["basic_band"]) + self.extension

    @property
    def higher_limit(self) -> Decimal:
        """Taxable income above here is charged at the additional rate."""
        return _dec(self.year["higher_rate_limit"]) + self.extension

    def band_at(self, taxable_used) -> str:
        """The band the next pound stacked on `taxable_used` falls into."""
        used = _dec(taxable_used)
        if used < self.basic_limit:
            return BASIC
        return HIGHER if used < self.higher_limit else ADDITIONAL

    def basic_room(self, taxable_used) -> Decimal:
        """How much of the basic rate band is still free above `taxable_used` —
        what capital gains stack into before they reach the higher rate."""
        return max(Decimal(0), self.basic_limit - _dec(taxable_used))

    def psa(self, band: str) -> Decimal:
        """The personal savings allowance for a taxpayer in `band`: £1,000
        basic, £500 higher, nil additional."""
        return _dec(self.year["psa"][band])

    def income_rate(self, band: str) -> Decimal:
        return _dec(self.year["income_rates"][band])

    def dividend_rate(self, band: str) -> Decimal:
        return _dec(self.year["dividend_rates"][band])

    def cgt_rate(self, band: str, *, residential: bool = False) -> Decimal:
        """The CGT rate for a gain landing in `band`. Capital gains have two
        rates, not three: a gain above the basic rate band is charged at the
        higher rate whether the taxpayer is higher or additional rate."""
        key = "cgt_rates_residential" if residential else "cgt_rates_shares"
        rates = self.year.get(key) or self.year["cgt_rates_shares"]
        return _dec(rates[BASIC if band == BASIC else HIGHER])

    def personal_allowance(self, adjusted_net_income) -> Decimal:
        return taper_allowance(self.year, adjusted_net_income)

    def in_pa_taper(self, adjusted_net_income) -> bool:
        """Whether this income sits in the zone where each extra £2 also removes
        £1 of personal allowance — the "60% trap"."""
        ani = _dec(adjusted_net_income)
        return _dec(self.year["pa_taper_start"]) < ani <= _dec(self.year["pa_taper_end"])

    @property
    def taper_zone(self) -> tuple[Decimal, Decimal]:
        """(where the allowance starts tapering, where it is gone) — for the
        sentences that name that zone, so no view has to spell it out."""
        return _dec(self.year["pa_taper_start"]), _dec(self.year["pa_taper_end"])


def bands_for(year: dict, band_extension=0) -> Bands:
    """The band boundaries for one taxpayer in `year`, `band_extension` being
    the gross pension/Gift Aid relief that widens them."""
    return Bands(year, _dec(band_extension))


# ── Capital gains rate periods ────────────────────────────────────────────────


def cgt_rate_periods(year: dict) -> list[dict]:
    """The year's CGT rates as dated periods, in order, together covering the
    whole tax year exactly once.

    Most years have one period. 2024/25 has two, because the rates on shares
    changed on 30 October 2024. `_self_check` proves the periods leave no gap
    and no overlap; `parameters` shows them; `estimator` charges each disposal
    at the rates for the period its date falls in."""
    tax_year = year["tax_year"]
    start, end = tax_year_start(tax_year), tax_year_end(tax_year)
    residential = year.get("cgt_rates_residential") or year["cgt_rates_shares"]
    change = year.get("cgt_mid_year_change")
    if not change:
        return [
            {
                "start": start,
                "end": end,
                "shares": dict(year["cgt_rates_shares"]),
                "residential": dict(residential),
            }
        ]
    cut = date.fromisoformat(change["date"])
    return [
        {
            "start": start,
            "end": cut - timedelta(days=1),
            "shares": dict(change["rates_before"]),
            "residential": dict(residential),
        },
        {
            "start": cut,
            "end": end,
            "shares": dict(year["cgt_rates_shares"]),
            "residential": dict(residential),
        },
    ]


# ── The table, for showing ────────────────────────────────────────────────────


def _rate_triple(rates: dict) -> str:
    return " / ".join(f"{float(rates[b]) * 100:g}%" for b in BAND_ORDER)


def _pair(rates: dict) -> str:
    return f"{float(rates[BASIC]) * 100:g}% / {float(rates[HIGHER]) * 100:g}%"


def parameters(tax_year: int) -> list[dict] | None:
    """Every parameter the year's calculation uses, grouped for display, with
    the gov.uk pages each group was checked against.

    This exists so the figures can be eyeballed against gov.uk without reading
    the source: it is built from `YEARS` itself, so it cannot drift from what
    the bill was actually computed with."""
    year = YEARS.get(tax_year)
    if year is None:
        return None
    periods = [
        {
            "label": f"{p['start'].strftime('%-d %b %Y')} – {p['end'].strftime('%-d %b %Y')}",
            "shares": _pair(p["shares"]),
            "residential": _pair(p["residential"]),
        }
        for p in cgt_rate_periods(year)
    ]
    return [
        {
            "title": "Allowances",
            "source": year["sources"][0],
            "rows": [
                {
                    "label": "Personal allowance",
                    "value": year["personal_allowance"],
                    "kind": "money",
                },
                {"label": "Taper starts at", "value": year["pa_taper_start"], "kind": "money"},
                {"label": "Allowance gone at", "value": year["pa_taper_end"], "kind": "money"},
                {
                    "label": "Starting rate for savings",
                    "value": year["starting_rate_savings_band"],
                    "kind": "money",
                },
                {"label": "ISA allowance", "value": year["isa_allowance"], "kind": "money"},
            ],
        },
        {
            "title": "Income tax bands (taxable income, after allowances)",
            "source": year["sources"][0],
            "rows": [
                {"label": "Basic rate up to", "value": year["basic_band"], "kind": "money"},
                {
                    "label": "Higher rate up to",
                    "value": year["higher_rate_limit"],
                    "kind": "money",
                },
                {
                    "label": "Additional rate above",
                    "value": year["higher_rate_limit"],
                    "kind": "money",
                },
                {
                    "label": "Rates (basic / higher / additional)",
                    "value": _rate_triple(year["income_rates"]),
                    "kind": "text",
                },
            ],
        },
        {
            "title": "Savings and dividends",
            "source": _SRC_SAVINGS,
            "rows": [
                {
                    "label": "Personal savings allowance",
                    "value": " / ".join(f"£{year['psa'][b]:,}" for b in BAND_ORDER),
                    "kind": "text",
                },
                {
                    "label": "Dividend allowance",
                    "value": year["dividend_allowance"],
                    "kind": "money",
                },
                {
                    "label": "Dividend rates (basic / higher / additional)",
                    "value": _rate_triple(year["dividend_rates"]),
                    "kind": "text",
                },
            ],
        },
        {
            "title": "Capital gains",
            "source": _SRC_CGT,
            "rows": [
                {"label": "Annual exempt amount", "value": year["cgt_allowance"], "kind": "money"},
                *[
                    {
                        "label": f"Shares, {p['label']}",
                        "value": p["shares"],
                        "kind": "text",
                    }
                    for p in periods
                ],
                *[
                    {
                        "label": f"Residential property, {p['label']}",
                        "value": p["residential"],
                        "kind": "text",
                    }
                    for p in periods[:1]
                ],
            ],
        },
        {
            "title": "Pension annual allowance",
            "source": "https://www.gov.uk/guidance/pension-schemes-rates",
            "rows": [
                {"label": "Annual allowance", "value": year["pension_aa"], "kind": "money"},
                {
                    "label": "Taper: threshold income over",
                    "value": year["pension_taper_threshold_income"],
                    "kind": "money",
                },
                {
                    "label": "Taper: adjusted income over",
                    "value": year["pension_taper_adjusted_income"],
                    "kind": "money",
                },
                {"label": "Tapered floor", "value": year["pension_aa_min"], "kind": "money"},
            ],
        },
    ]


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


# ── Self-check ────────────────────────────────────────────────────────────────
#
# Runs at import. A table that contradicts itself produces a wrong bill that
# looks perfectly reasonable — a missing rate band or a threshold below the one
# under it is silent in every calculation and visible only in the total. This
# turns that class of mistake into an import that fails with the year and the
# figure named.

# Everything here is an allowance or a threshold: none of them can be negative.
_NON_NEGATIVE = (
    "personal_allowance",
    "pa_taper_start",
    "pa_taper_end",
    "basic_band",
    "higher_rate_limit",
    "dividend_allowance",
    "cgt_allowance",
    "starting_rate_savings_band",
    "isa_allowance",
    "pension_aa",
    "pension_aa_min",
    "pension_taper_threshold_income",
    "pension_taper_adjusted_income",
)


def _check_rates(problems: list[str], where: str, rates: dict, bands: tuple[str, ...]) -> None:
    missing = [b for b in bands if b not in rates]
    if missing:
        problems.append(f"{where}: no rate for {', '.join(missing)}")
        return
    for band in bands:
        rate = float(rates[band])
        if not 0 <= rate <= 1:
            problems.append(f"{where}: {band} rate {rate} is not a fraction between 0 and 1")
    ordered = [float(rates[b]) for b in bands]
    if ordered != sorted(ordered):
        problems.append(f"{where}: rates fall as the band rises ({ordered})")


def _check_year(problems: list[str], tax_year: int, year: dict) -> None:
    where = f"{label(tax_year)}"
    found = len(problems)
    for key in _NON_NEGATIVE:
        if key not in year:
            problems.append(f"{where}: missing {key}")
        elif float(year[key]) < 0:
            problems.append(f"{where}: {key} is negative ({year[key]})")
    for band in BAND_ORDER:
        if band not in year.get("psa", {}):
            problems.append(f"{where}: no personal savings allowance for the {band} band")
        elif float(year["psa"][band]) < 0:
            problems.append(f"{where}: {band} personal savings allowance is negative")
    if len(problems) > found:
        # Something this year is missing outright; the comparisons below would
        # raise KeyError rather than report it.
        return

    # The personal allowance must be gone by the time the additional rate
    # starts. A year that put the additional rate below the end of the taper
    # would be charging 45% inside the 60% zone — every pound there taxed at
    # 45% while it is also stripping away allowance at 40%.
    #
    # The two are measured differently: the taper works on adjusted net income
    # (gross), the rate limit on taxable income (after allowances). At the top
    # of the taper the allowance is nil, so at that point the two scales meet
    # and the comparison is exact.
    if _dec(year["pa_taper_end"]) > _dec(year["higher_rate_limit"]):
        problems.append(
            f"{where}: the personal allowance still tapers at "
            f"£{year['pa_taper_end']:,} but the additional rate starts at "
            f"£{year['higher_rate_limit']:,}"
        )
    # Where the taper ends is arithmetic, not a separate fact: the allowance
    # falls £1 per £2, so it is gone two allowances above the taper start.
    implied = _dec(year["pa_taper_start"]) + 2 * _dec(year["personal_allowance"])
    if _dec(year["pa_taper_end"]) != implied:
        problems.append(
            f"{where}: pa_taper_end is £{year['pa_taper_end']:,} but a "
            f"£{year['personal_allowance']:,} allowance tapering from "
            f"£{year['pa_taper_start']:,} runs out at £{implied:,}"
        )
    if _dec(year["basic_band"]) >= _dec(year["higher_rate_limit"]):
        problems.append(
            f"{where}: the basic rate band (£{year['basic_band']:,}) reaches the "
            f"additional rate threshold (£{year['higher_rate_limit']:,})"
        )

    _check_rates(problems, f"{where} income", year["income_rates"], BAND_ORDER)
    _check_rates(problems, f"{where} dividends", year["dividend_rates"], BAND_ORDER)
    _check_rates(problems, f"{where} CGT shares", year["cgt_rates_shares"], (BASIC, HIGHER))
    if year.get("cgt_rates_residential"):
        _check_rates(
            problems, f"{where} CGT residential", year["cgt_rates_residential"], (BASIC, HIGHER)
        )

    # The CGT rate periods have to tile the tax year: every disposal date in the
    # year must fall in exactly one of them, or a disposal is charged twice or
    # not at all.
    periods = cgt_rate_periods(year)
    start, end = tax_year_start(tax_year), tax_year_end(tax_year)
    if periods[0]["start"] != start:
        problems.append(
            f"{where}: CGT rates start on {periods[0]['start']}, not the "
            f"first day of the year ({start})"
        )
    if periods[-1]["end"] != end:
        problems.append(
            f"{where}: CGT rates end on {periods[-1]['end']}, not the last day of the year ({end})"
        )
    for period in periods:
        if period["start"] > period["end"]:
            problems.append(f"{where}: CGT rate period {period['start']}–{period['end']} is empty")
        elif period["start"] < start or period["end"] > end:
            problems.append(
                f"{where}: CGT rate period {period['start']}–{period['end']} falls outside "
                f"the tax year ({start}–{end})"
            )
    for before, after in zip(periods, periods[1:], strict=False):
        gap = (after["start"] - before["end"]).days
        if gap > 1:
            problems.append(f"{where}: no CGT rate between {before['end']} and {after['start']}")
        elif gap < 1:
            problems.append(
                f"{where}: CGT rate periods overlap at {after['start']} "
                f"(the previous one runs to {before['end']})"
            )
    for source in year.get("sources", ()):
        if not str(source).startswith("https://www.gov.uk/"):
            problems.append(f"{where}: {source} is not a gov.uk source")
    if not year.get("sources"):
        problems.append(f"{where}: no gov.uk source recorded")


def _self_check() -> None:
    """Raise `TaxTableError` if anything in `YEARS` contradicts itself."""
    problems: list[str] = []
    for tax_year, year in sorted(YEARS.items()):
        if year.get("tax_year") != tax_year:
            problems.append(f"{label(tax_year)}: entry is stamped {year.get('tax_year')}")
        _check_year(problems, tax_year, year)
    if problems:
        raise TaxTableError(
            "core/tax_years.py is inconsistent — fix the table before this app can "
            "compute anything:\n  " + "\n  ".join(problems)
        )


_self_check()
