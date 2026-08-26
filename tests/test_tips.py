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


# ── Lost / expiring benefits ──────────────────────────────────────────────────
#
# An allowance that doesn't carry forward is "expiring" (orange) while the year
# is open and 5 April is near, and "lost" (red) once the year has closed.

CLOSED = date(2026, 8, 27)  # 2025/26 is over
NEAR_YEAR_END = date(2026, 3, 1)  # 35 days left in 2025/26
MID_YEAR = date(2026, 1, 15)  # 80 days left — nothing urgent yet


def _statuses(inputs, invest=None, today=MID_YEAR, tax_year=2025):
    tips = build_tips(_ctx(inputs, invest, tax_year=tax_year, today=today))
    return {t["id"]: t for t in tips}


def test_annual_allowances_are_quiet_mid_year():
    tips = _statuses({"employment_income": 60000, "isa_used": 0}, {"total_gain": 500})
    assert tips["cgt_harvest"]["status"] is None
    assert tips["bed_isa"]["status"] is None


def test_annual_allowances_expire_as_5_april_approaches():
    inputs = {"employment_income": 60000, "isa_used": 0}
    tips = _statuses(inputs, {"total_gain": 500}, NEAR_YEAR_END)
    assert tips["cgt_harvest"]["status"] == "expiring"
    assert "expires on 5 Apr 2026" in tips["cgt_harvest"]["status_note"]
    assert tips["cgt_harvest"]["estimated_win_gbp"] is not None  # still actionable
    assert tips["bed_isa"]["status"] == "expiring"
    assert "Move up to £20,000" in tips["bed_isa"]["what_to_do"]


def test_closed_year_allowances_are_lost():
    tips = _statuses({"employment_income": 60000, "isa_used": 5000}, {"total_gain": 500}, CLOSED)
    cgt = tips["cgt_harvest"]
    assert cgt["status"] == "lost" and cgt["estimated_win_gbp"] is None
    assert "expired unused on 5 Apr 2026" in cgt["status_note"]
    assert "before 5 April" not in cgt["what_to_do"]
    isa = tips["bed_isa"]
    assert isa["status"] == "lost" and isa["estimated_win_gbp"] is None
    assert "£15,000 of the 2025/26 £20,000 ISA allowance" in isa["status_note"]


def test_unfilled_isa_input_is_warned_about_before_the_card_goes_red():
    tips = _statuses({"employment_income": 60000}, today=CLOSED)
    assert tips["bed_isa"]["status"] == "lost"
    assert any("isn't filled in" in w for w in tips["bed_isa"]["warnings"])


def test_sixty_trap_closed_year_still_allows_gift_aid_carry_back():
    # 2025/26 closed on 5 Apr 2026; its return is due 31 Jan 2027, so an election
    # to carry a donation back is still open.
    tip = _statuses({"employment_income": 120000}, today=CLOSED)["sixty_trap"]
    assert tip["status"] == "expiring"
    assert "Gift Aid" in tip["what_to_do"] and "31 Jan 2027" in tip["status_note"]
    assert tip["estimated_win_gbp"] is None


def test_sixty_trap_is_lost_once_the_return_deadline_passes():
    tip = _statuses({"employment_income": 120000}, today=date(2027, 2, 1))["sixty_trap"]
    assert tip["status"] == "lost"
    assert "£10,000 of the 2025/26 personal allowance was tapered away" in tip["status_note"]


def test_expiring_and_lost_sort_above_plain_opportunities():
    tips = build_tips(
        _ctx({"employment_income": 120000, "isa_used": 0}, {"total_gain": 500}, today=CLOSED)
    )
    order = [t["status"] for t in tips]
    assert order == sorted(order, key=lambda s: {"expiring": 0, "lost": 1}.get(s, 2))
