"""Hand-computed examples for the income-tax profile (2025/26 constants)."""

import pytest

from core import tax_years
from core.tax_profile import build_profile

Y = tax_years.get_year(2025)


def test_plain_higher_rate_employee():
    p = build_profile({"employment_income": 60000}, Y, {})
    assert p["allowances"]["personal_allowance"] == 12570
    # 37700 @ 20% + 9730 @ 40%
    assert p["tax"]["income_tax_total"] == pytest.approx(11432)
    assert p["bands"]["marginal_band"] == "higher"
    assert not p["bands"]["in_pa_taper"]


def test_pa_taper_at_110k():
    p = build_profile({"employment_income": 110000}, Y, {})
    assert p["allowances"]["personal_allowance"] == pytest.approx(7570)
    assert p["tax"]["income_tax_total"] == pytest.approx(33432)
    assert p["bands"]["in_pa_taper"]
    assert p["marginal"]["effective_rate"] == 0.60


def test_dividends_straddling_band_boundary():
    p = build_profile({"employment_income": 50000}, Y, {"dividends_total": 5000})
    # £500 allowance at 0%, remaining £4500 falls in higher band at 33.75%
    assert p["tax"]["dividend_tax"] == pytest.approx(4500 * 0.3375)


def test_interest_psa_higher_rate():
    p = build_profile({"employment_income": 60000}, Y, {"uk_interest": 1000})
    assert p["allowances"]["psa"] == 500
    assert p["tax"]["savings_tax"] == pytest.approx(500 * 0.40)


def test_cgt_all_at_higher_rate():
    p = build_profile({"employment_income": 60000}, Y, {"taxable_gain": 10000})
    assert p["tax"]["cgt_estimate"] == pytest.approx(2400)


def test_cgt_within_basic_band():
    p = build_profile({"employment_income": 30000}, Y, {"taxable_gain": 10000})
    assert p["tax"]["cgt_estimate"] == pytest.approx(1800)


def test_sipp_extends_band_and_restores_pa():
    p = build_profile({"employment_income": 130000, "sipp_paid": 8000}, Y, {})
    # gross contribution 10k: ANI 120k -> PA 2570, basic band extended to 47700
    assert p["income"]["adjusted_net_income"] == pytest.approx(120000)
    assert p["allowances"]["personal_allowance"] == pytest.approx(2570)
    assert p["bands"]["basic_top"] == pytest.approx(47700)
    assert p["bands"]["in_pa_taper"]


def test_other_income_taxed_at_marginal_rate_less_credit():
    # £80.76 of PIDs/fees on top of £60k employment: 40% = 32.30, less 16.13 withheld
    p = build_profile(
        {"employment_income": 60000}, Y, {"other_income": 80.76, "other_income_tax": 16.13}
    )
    assert p["income"]["other_income"] == 80.76
    assert p["income"]["non_savings"] == pytest.approx(60080.76)
    assert p["tax"]["other_income_tax"] == pytest.approx(80.76 * 0.40 - 16.13, abs=0.01)
    assert p["tax"]["other_income_credit"] == 16.13


def test_other_income_within_personal_allowance_yields_a_refund():
    p = build_profile({}, Y, {"other_income": 100, "other_income_tax": 20})
    assert p["tax"]["other_income_tax"] == pytest.approx(-20)
