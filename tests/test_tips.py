from core import tax_years
from core.tax_profile import build_profile
from core.tips import build_tips

Y = tax_years.get_year(2025)


def _ctx(inputs, invest=None, bundle=None):
    invest = invest or {}
    return {
        "inputs": inputs,
        "year": Y,
        "profile": build_profile(inputs, Y, invest),
        "invest": invest,
        "bundle": bundle,
        "tax_year": 2025,
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
    # this year 50k + carry forward (10k + 0 + 20k) = 80k headroom at 40%
    assert tip["estimated_win_gbp"] == 80000 * 0.40


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
