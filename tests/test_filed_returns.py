"""The three returns HMRC has actually calculated, reproduced to the penny.

Every figure here comes from a filed return and HMRC's own computation of it,
so these are the only tests in the suite that check the tool against reality
rather than against its own reading of the rules. If one of them fails, the
tool is wrong — not the test.

They exist because of the £150,000 bug: 2022/23's additional rate threshold was
carried over from a later year as £125,140, which put £2,580 of a £127,720
salary at 45% instead of 40% and — much worse than the £129 that cost —
classified the taxpayer as additional rate, taking away the £500 personal
savings allowance and charging dividends at 39.35% instead of 33.75%. A test
that only checked "an additional rate payer pays 45%" would have passed
throughout. So each case asserts the band classification as well as the bill:
the band is what the allowances and the dividend rate are read from.

2023/24 is examined in much more depth in test_paye_reconciliation.py (the
filed return had two mistakes in it, both deliberately preserved there); this
file keeps the headline so all three years fail in one place.
"""

import pytest

from core import tax_years
from core.self_assessment import Inputs, compute, to_json


def _bill(tax_year: int, **inputs):
    """The bill as the API sends it — floats to the penny."""
    year = tax_years.get_year(tax_year)
    return to_json(compute(Inputs(year=year, tax_year=tax_year, **inputs)))


def _band(result):
    return result["bands"]["marginal_band"]


# ── 2022/23 ───────────────────────────────────────────────────────────────────
#
# Pay £127,720, PAYE £38,516.40, nothing else. HMRC charged £5,031.60.
#
#   personal allowance:      nil (£127,720 is past the £125,140 taper end)
#   37,700 @ 20%           =  7,540.00
#   (127,720 − 37,700) @ 40% = 36,008.00   ← all of it at 40%: the additional
#   ────────────────────────────────────     rate starts at £150,000 this year
#   income tax               43,548.00
#   − PAYE                   38,516.40
#   = bill                    5,031.60


@pytest.fixture
def y2022():
    return _bill(
        2022,
        employments=[{"name": "Employer", "pay": "127720", "tax_deducted": "38516.40"}],
    )


def test_2022_23_reproduces_hmrcs_bill(y2022):
    assert y2022["sa_bill"] == pytest.approx(5031.60)


def test_2022_23_is_a_higher_rate_taxpayer(y2022):
    """£127,720 is over the old £125,140 threshold and under this year's
    £150,000 one. Getting this wrong is what made the bill £5,160.60."""
    assert _band(y2022) == tax_years.HIGHER
    assert y2022["income_tax"]["non_savings"] == pytest.approx(43548.00)
    assert not any(
        s["band"] == tax_years.ADDITIONAL for s in y2022["income_tax"]["slices"]["non_savings"]
    )


def test_2022_23_band_carries_the_right_allowance_and_dividend_rate(y2022):
    """What the band is actually for: a higher rate payer keeps £500 of personal
    savings allowance and pays 33.75% on dividends, not nil and 39.35%."""
    bands = tax_years.bands_for(tax_years.get_year(2022))
    assert float(bands.psa(_band(y2022))) == 500
    assert float(bands.dividend_rate(_band(y2022))) == 0.3375


# ── 2023/24 ───────────────────────────────────────────────────────────────────
#
# The return as filed: pay £220,031, PAYE £84,553.40, £2 of interest, £42 of
# foreign dividends with £11 withheld, gains £6,164 less £109 of losses, and £54
# in the "tax already paid on gains" box. HMRC charged £621.45.
#
#   37,700 @ 20% + 87,440 @ 40% + 94,891 @ 45% = 85,216.95
#   £2 of interest @ 45% (no PSA at this income)      0.90
#   £42 of dividends: inside the £1,000 allowance     0.00
#   − PAYE 84,553.40                              =  664.45
#   CGT: (6,164 − 109 − 6,000 AEA) = 55 @ 20%     =   11.00
#   − £54 already paid                            =  621.45


@pytest.fixture
def y2023():
    return _bill(
        2023,
        employments=[{"name": "Employer", "pay": "220031", "tax_deducted": "84553.40"}],
        uk_interest="2",
        foreign_dividends="42",
        foreign_dividend_tax="11",
        disposals=[
            {"date": "2024-01-15", "gain": "6164"},
            {"date": "2024-01-15", "gain": "-109"},
        ],
        tax_paid_on_gains="54",
    )


def test_2023_24_reproduces_hmrcs_bill(y2023):
    assert y2023["sa_bill"] == pytest.approx(621.45)


def test_2023_24_is_an_additional_rate_taxpayer(y2023):
    assert _band(y2023) == tax_years.ADDITIONAL
    assert y2023["income_tax"]["non_savings"] == pytest.approx(85216.95)
    # The band is why the £2 of interest is taxed at all: no PSA above £125,140.
    assert y2023["allowances"]["psa"] == 0
    assert y2023["income_tax"]["savings"] == pytest.approx(0.90)


def test_2023_24_capital_gains(y2023):
    assert y2023["cgt"]["cgt_total"] == pytest.approx(11.00)


# ── 2024/25 ───────────────────────────────────────────────────────────────────
#
# Pay £332,825, PAYE £135,974.25, UK dividends £726, foreign dividends £183, and
# £8,563.52 of gains split by the 30 October rate change: £2,524.95 before,
# £6,038.57 after. The annual exempt amount is set against the 24% gains, which
# is what saves the most.
#
#   dividends: (726 + 183 − 500 allowance) = 409 @ 39.35% = 160.94
#   gains before 30 Oct: 2,524 @ 20%                      = 504.80
#   gains after 30 Oct:  (6,038 − 3,000 AEA) @ 24%        = 729.12
#                                                    CGT  = 1,233.92


@pytest.fixture
def y2024():
    return _bill(
        2024,
        employments=[{"name": "Employer", "pay": "332825", "tax_deducted": "135974.25"}],
        uk_dividends="726",
        foreign_dividends="183",
        disposals=[
            {"date": "2024-05-16", "gain": "185.90"},
            {"date": "2024-08-26", "gain": "2339.05"},
            {"date": "2025-02-25", "gain": "6038.57"},
        ],
    )


def test_2024_25_is_an_additional_rate_taxpayer(y2024):
    assert _band(y2024) == tax_years.ADDITIONAL
    assert y2024["allowances"]["psa"] == 0


def test_2024_25_dividend_tax(y2024):
    """£909 of dividends less the £500 allowance, all at the additional rate."""
    assert y2024["income_tax"]["dividends_gross"] == pytest.approx(160.94)


def test_2024_25_capital_gains_tax(y2024):
    assert y2024["cgt"]["cgt_total"] == pytest.approx(1233.92)


def test_2024_25_exempt_amount_goes_against_the_24_percent_gains(y2024):
    """Relief comes off the highest-charged gains first: £3,000 against the 24%
    bucket saves £720, against the 20% bucket only £600."""
    by_key = {b["key"]: b for b in y2024["cgt"]["buckets"]}
    assert by_key["post_30_oct"]["rounded"] == pytest.approx(3038)
    assert by_key["pre_30_oct"]["rounded"] == pytest.approx(2524)
    assert by_key["post_30_oct"]["tax"] == pytest.approx(729.12)
    assert by_key["pre_30_oct"]["tax"] == pytest.approx(504.80)
