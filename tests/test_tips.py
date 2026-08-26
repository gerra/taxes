from datetime import date

from core import tax_years
from core.tax_profile import build_profile
from core.tips import build_tips

Y = tax_years.get_year(2025)


def _ctx(inputs, invest=None, bundle=None, tax_year=2025, today=date(2026, 1, 15)):
    invest = invest or {}
    year = tax_years.get_year(tax_year)
    return {
        "inputs": inputs,
        "year": year,
        "profile": build_profile(inputs, year, invest),
        "invest": invest,
        "bundle": bundle,
        "tax_year": tax_year,
        "today": today,  # inside the year → the "contribute before 5 April" branch
        "prior_years": {},
    }


def _get(tips, id_):
    return next((t for t in tips if t["id"] == id_), None)


def test_pension_headroom_with_taper_zone_rate():
    inputs = {"employment_income": 130000, "sipp_paid": 8000}
    tips = build_tips(_ctx(inputs))
    tip = _get(tips, "pension_headroom")
    # AA 60k - 10k gross used = 50k headroom at 60% effective
    assert tip["estimated_win_gbp"] == 50000 * 0.60


def test_sixty_trap_amount():
    tips = build_tips(_ctx({"employment_income": 120000}))
    tip = _get(tips, "sixty_trap")
    assert tip is not None
    assert "£20,000" in tip["title"]
    assert tip["estimated_win_gbp"] == 12000


def test_no_sixty_trap_below_100k():
    assert _get(build_tips(_ctx({"employment_income": 90000})), "sixty_trap") is None


def test_cgt_harvest_uses_unused_allowance():
    tips = build_tips(_ctx({"employment_income": 60000}, {"total_gain": 1000}))
    tip = _get(tips, "cgt_harvest")
    assert tip["estimated_win_gbp"] == 2000 * 0.24


def test_carry_forward_included():
    inputs = {
        "employment_income": 80000,
        "pension_employee": 10000,
        "pension_prior_1": 50000,
        "pension_prior_2": 60000,
        "pension_prior_3": 40000,
    }
    tip = _get(build_tips(_ctx(inputs)), "pension_headroom")
    # this year 50k + carry forward: 2024/25 60k-50k = 10k, 2023/24 60k-60k = 0,
    # 2022/23 had a £40k allowance so 40k paid leaves 0 → 60k headroom at 40%
    assert tip["estimated_win_gbp"] == 60000 * 0.40
    assert "2024/25: £10,000.00 unused of £60,000.00" in tip["detail"]
    assert "2022/23: £0.00 unused of £40,000.00" in tip["detail"]
    # no income saved for those years → they can't be taper-checked
    assert len(tip["warnings"]) == 3 and all("unverified" in w for w in tip["warnings"])


def test_carry_forward_uses_that_years_allowance():
    inputs = {"employment_income": 80000, "pension_employee": 60000, "pension_prior_3": 30000}
    tip = _get(build_tips(_ctx(inputs)), "pension_headroom")
    # 2022/23 allowance was £40k, not this year's £60k: 10k unused, not 30k
    assert tip["estimated_win_gbp"] == 10000 * 0.40
    assert "2022/23: £10,000.00 unused of £40,000.00" in tip["detail"]


def test_carry_forward_reaches_years_before_constants_start():
    inputs = {"employment_income": 80000, "pension_employee": 40000, "pension_prior_3": 15000}
    tip = _get(build_tips(_ctx(inputs, tax_year=2022, today=date(2023, 1, 15))), "pension_headroom")
    # 2019/20 allowance £40k → 25k carried; this year (AA 40k) fully used
    assert tip["estimated_win_gbp"] == 25000 * 0.40


def test_withholding_flag():
    bundle = {
        "dividends": [
            {"symbol": "ABC", "amount_gbp": "100", "tax_at_source_gbp": "30"},
            {"symbol": "OK", "amount_gbp": "100", "tax_at_source_gbp": "15"},
        ],
        "portfolio_eoy": [],
    }
    tip = _get(build_tips(_ctx({"employment_income": 50000}, {}, bundle)), "withholding")
    assert tip is not None and "ABC" in tip["title"] and "OK" not in tip["title"]
