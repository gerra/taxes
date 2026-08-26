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
