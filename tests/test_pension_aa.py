"""Pension annual allowance engine: per-year allowance, taper, carry-forward.

Fixture figures are real (Fidelity pension savings statement), with the
s228ZA rounding rule applied: the taper reduction is rounded down to £1."""

from datetime import date
from decimal import Decimal as D

import pytest

from core import pension_aa, tax_years
from core.pension_aa import PensionYear, allowance_for, compute
from core.tax_profile import build_profile
from core.tips import build_tips

# ── Fixture: real figures ──────────────────────────────────────────────────────

Y2022 = PensionYear(2022, D("7509.93"), None)  # income unknown → unverified
Y2023 = PensionYear(2023, D("9203.52"), D("220031.00"))
Y2024 = PensionYear(2024, D("16987.32"), D("332826.00"))
Y2025 = PensionYear(2025, D("17668.74"), D("376182.79"))
FIXTURE = [Y2022, Y2023, Y2024, Y2025]


# ── Per-year standard allowance and taper parameters ───────────────────────────


@pytest.mark.parametrize(
    "year, aa, threshold, adjusted, floor",
    [
        (2016, 40000, 110000, 150000, 10000),
        (2019, 40000, 110000, 150000, 10000),
        (2020, 40000, 200000, 240000, 4000),
        (2022, 40000, 200000, 240000, 4000),
        (2023, 60000, 200000, 260000, 10000),
        (2026, 60000, 200000, 260000, 10000),
    ],
)
def test_pension_rules_per_year(year, aa, threshold, adjusted, floor):
    r = tax_years.pension_rules(year)
    assert (r["aa"], r["threshold_income"], r["adjusted_income"], r["aa_min"]) == (
        aa,
        threshold,
        adjusted,
        floor,
    )


def test_pension_rules_unknown_before_2016():
    assert tax_years.pension_rules(2015) is None


# ── Taper ──────────────────────────────────────────────────────────────────────


def test_taper_2024_rounds_reduction_down_to_whole_pound():
    a = allowance_for(2024, D("332826.00"), D("16987.32"))
    assert a["adjusted_income"] == D("349813.32")
    assert a["tapered"]
    assert a["reduction"] == D("44906")  # 89,813.32 / 2 = 44,906.66 → £44,906
    assert a["allowance"] == D("15094.00")


def test_taper_floor_2025():
    a = allowance_for(2025, D("376182.79"), D("17668.74"))
    assert a["adjusted_income"] == D("393851.53")
    assert a["allowance"] == D("10000.00")  # 60k − 66,925 < 10k floor


def test_taper_floor_2022_parameters():
    # 2020/21–2022/23: limit £240k, floor £4,000
    a = allowance_for(2022, D("400000"), D("20000"))
    assert a["allowance"] == D("4000.00")
    a = allowance_for(2022, D("230000"), D("20000"))  # adjusted 250k → −5,000
    assert a["allowance"] == D("35000.00")


def test_taper_2019_parameters():
    # 2016/17–2019/20: threshold £110k, limit £150k, floor £10k
    a = allowance_for(2019, D("140000"), D("30000"))  # adjusted 170k → −10,000
    assert a["tapered"] and a["allowance"] == D("30000.00")
    a = allowance_for(2019, D("100000"), D("60000"))  # threshold 100k ≤ 110k
    assert not a["tapered"] and a["allowance"] == D("40000.00")


def test_taper_needs_both_conditions():
    # threshold > 200k but adjusted 229,234.52 < 260k → no taper (fixture 2023/24)
    a = allowance_for(2023, D("220031.00"), D("9203.52"))
    assert not a["tapered"] and a["allowance"] == D("60000.00")
    # adjusted > 260k but threshold 190k ≤ 200k → no taper
    a = allowance_for(2024, D("190000"), D("80000"))
    assert not a["tapered"] and a["allowance"] == D("60000.00")
    # same, but £15k of salary sacrifice pushes threshold income over 200k
    a = allowance_for(2024, D("190000"), D("80000"), sacrifice=D("15000"))
    assert a["threshold_income"] == D("205000") and a["tapered"]
    assert a["allowance"] == D("55000.00")  # (270k − 260k)/2


def test_threshold_income_deducts_relief_at_source():
    # £10k gross RAS SIPP: in net income, deducted for threshold, not re-added for adjusted
    a = allowance_for(2024, D("205000"), D("10000"), ras_gross=D("10000"))
    assert a["threshold_income"] == D("195000")
    assert a["adjusted_income"] == D("205000")
    assert not a["tapered"]


def test_unknown_income_gives_untapered_unverified_allowance():
    a = allowance_for(2022, None, D("7509.93"))
    assert a["allowance"] == D("40000.00") and not a["verified"]


# ── Carry-forward engine ───────────────────────────────────────────────────────


def test_fixture_2025_planner():
    res = compute(2025, FIXTURE)
    assert res["carry_available"] == {
        2022: D("30596.75"),  # 32,490.07 − 1,893.32 eaten by 2024/25's excess
        2023: D("50796.48"),
        2024: D("0.00"),
    }
    assert res["years"][2024]["excess"] == D("1893.32")
    assert res["years"][2024]["consumed"] == {2022: D("1893.32")}
    assert res["selected"]["allowance"] == D("10000.00")
    assert res["headroom"] == D("73724.49")
    assert res["charge"] == D("0.00")
    assert all(r["charge"] == 0 for r in res["years"].values())
    assert res["selected"]["consumed"] == {2022: D("7668.74")}
    assert res["carry_next"] == {2023: D("50796.48"), 2024: D("0.00"), 2025: D("0.00")}
    assert res["carry_next_total"] == D("50796.48")
    assert res["expired"] == D("22928.01")
    assert res["unverified_total"] == D("30596.75")
    assert any("2022/23" in w and "unverified" in w for w in res["warnings"])


def test_fixture_2026_planner_sees_2022_absorbing_2025_excess():
    y2026 = PensionYear(2026, D("0"), D("380000.00"))
    res = compute(2026, FIXTURE + [y2026])
    # 2025/26's excess went to 2022/23, so 2023/24's £50,796.48 is intact
    assert res["carry_available"] == {2023: D("50796.48"), 2024: D("0.00"), 2025: D("0.00")}
    assert res["selected"]["allowance"] == D("10000.00")  # own-year taper from 2026/27 income
    assert res["headroom"] == D("60796.48")


def test_without_2022_data_2025_excess_eats_2023():
    res = compute(2026, [Y2023, Y2024, Y2025, PensionYear(2026, D("0"), D("380000.00"))])
    # 2023/24 is now the oldest year available, so it absorbs both 2024/25's
    # excess (1,893.32) and 2025/26's (7,668.74): 50,796.48 − 9,562.06
    assert res["carry_available"][2023] == D("41234.42")
    assert any("2022/23" in w for w in res["warnings"]) is False  # out of range, no warning


def test_oldest_year_consumed_first():
    years = [
        PensionYear(2022, D("10000"), D("100000")),  # 30,000 unused
        PensionYear(2023, D("40000"), D("100000")),  # 20,000 unused
        PensionYear(2024, D("50000"), D("100000")),  # 10,000 unused
        PensionYear(2025, D("85000"), D("100000")),  # 25,000 over
    ]
    res = compute(2025, years)
    assert res["selected"]["consumed"] == {2022: D("25000.00")}
    assert res["carry_next"] == {2023: D("20000.00"), 2024: D("10000.00"), 2025: D("0.00")}
    assert res["charge"] == D("0.00")


def test_historical_excess_reduces_what_reaches_selected_year():
    years = [
        PensionYear(2022, D("0.01"), D("100000")),  # 39,999.99 unused
        PensionYear(2023, D("70000"), D("100000")),  # 10,000 over → eats 2022
        PensionYear(2024, D("60000"), D("100000")),
        PensionYear(2025, D("0"), D("100000")),
    ]
    res = compute(2025, years)
    assert res["years"][2023]["consumed"] == {2022: D("10000.00")}
    assert res["carry_available"] == {2022: D("29999.99"), 2023: D("0.00"), 2024: D("0.00")}
    assert res["headroom"] == D("89999.99")


def test_excess_beyond_carry_forward_is_a_charge():
    years = [
        PensionYear(2023, D("55000"), D("100000")),  # 5,000 unused
        PensionYear(2024, D("100000"), D("100000")),  # 40,000 over: 5,000 covered
        PensionYear(2025, D("20000"), D("100000")),
    ]
    res = compute(2025, years)
    assert res["years"][2024]["charge"] == D("35000.00")
    assert res["carry_available"] == {2023: D("0.00"), 2024: D("0.00")}
    assert res["headroom"] == D("40000.00")
    assert any("2024/25" in w and "charge" in w for w in res["warnings"])


def test_selected_year_charge():
    res = compute(2025, [PensionYear(2025, D("75000"), D("100000"))])
    assert res["headroom"] == D("-15000.00") and res["charge"] == D("15000.00")


def test_non_member_year_carries_nothing():
    years = [PensionYear(2023, D("0"), D("100000"), member=False), Y2025]
    res = compute(2025, years)
    assert res["carry_available"][2023] == D("0.00")
    assert any("2023/24" in w and "member" in w for w in res["warnings"])


def test_missing_prior_year_is_warned_not_assumed():
    res = compute(2025, [Y2025])
    assert res["carry_available"] == {}
    assert res["headroom"] == D("-7668.74")
    assert sum("no pension figure" in w for w in res["warnings"]) == 3


# ── The tip: open vs closed year ───────────────────────────────────────────────

FIXTURE_INPUTS_2025 = {
    "employment_income": 376182.79,
    "pension_employee": 7067.47,
    "pension_employer": 10601.27,
    "pension_prior_1": 16987.32,
    "pension_prior_2": 9203.52,
    "pension_prior_3": 7509.93,
}
PRIOR_YEARS = {
    2024: {"inputs": {"employment_income": 332826.00}, "invest": {}},
    2023: {"inputs": {"employment_income": 220031.00}, "invest": {}},
}


def _ctx(inputs, tax_year, today, prior_years=None):
    y = tax_years.get_year(tax_year)
    return {
        "inputs": inputs,
        "year": y,
        "profile": build_profile(inputs, y, {}),
        "invest": {},
        "bundle": None,
        "tax_year": tax_year,
        "today": today,
        "prior_years": prior_years or {},
    }


def _pension_tip(tips):
    return next(t for t in tips if t["id"] == "pension_headroom")


def test_tip_open_year_suggests_capped_contribution():
    tip = _pension_tip(build_tips(_ctx(FIXTURE_INPUTS_2025, 2025, date(2026, 1, 15), PRIOR_YEARS)))
    assert tip["title"] == "£73,724.49 of pension annual allowance unused"
    assert "before 5 April 2026" in tip["what_to_do"]
    assert "£58,979.59 net" in tip["what_to_do"]  # 73,724.49 × 0.8
    assert "threshold income" in tip["what_to_do"]  # taper hint: RAS reduces threshold income
    assert tip["deadline"] == "2026-04-05"
    assert tip["estimated_win_gbp"] == round(73724.49 * 0.45)
    assert "= £73,724.49" in tip["detail"]
    assert "£15,094.00" in tip["detail"]
    assert any("2022/23" in w for w in tip["warnings"])


def test_tip_open_year_spells_out_the_avc_route():
    tip = _pension_tip(build_tips(_ctx(FIXTURE_INPUTS_2025, 2025, date(2026, 1, 15), PRIOR_YEARS)))
    assert "AVC into your workplace scheme" in tip["what_to_do"]
    steps = tip["how_to_execute"]
    # Carry-forward is only reached once the year's own allowance is exhausted.
    assert steps[0].startswith("Use this year first")
    assert "carry-forward can't be claimed on its own" in steps[0]
    assert "additional voluntary contribution" in steps[1]
    assert "salary sacrifice" in steps[1] and "saves NI" in steps[1]
    assert "standalone AVC contract" in steps[2]
    assert any("reach the provider by 5 Apr 2026" in x for x in steps)


def test_tip_steps_drop_the_carry_forward_ordering_when_there_is_none():
    inputs = {"employment_income": 80000, "pension_employer": 10000}
    steps = _pension_tip(build_tips(_ctx(inputs, 2025, date(2026, 1, 15))))["how_to_execute"]
    assert steps[0].startswith("This is all 2025/26's own allowance")
    # Unused annual allowance is not use-it-or-lose-it — it carries three years.
    assert "carries forward three years" in steps[0]


def test_tip_steps_send_headroom_above_earnings_through_the_employer():
    inputs = {"employment_income": 30000, "pension_prior_1": 0.01, "pension_prior_2": 0.01}
    steps = _pension_tip(build_tips(_ctx(inputs, 2025, date(2026, 1, 15))))["how_to_execute"]
    assert any("only an employer contribution can use that part" in x for x in steps)


def test_tip_charge_steps_cover_sa101_and_scheme_pays():
    inputs = {"employment_income": 150000, "pension_employer": 75000}
    steps = _pension_tip(build_tips(_ctx(inputs, 2024, date(2025, 6, 1))))["how_to_execute"]
    assert "SA101" in steps[0] and "box 10" in steps[0]
    # Mandatory Scheme Pays: election by 31 July of the year after the tax year.
    assert "31 July 2026" in steps[2] and "standard £60,000 allowance" in steps[2]


def test_tip_open_year_charge_says_stop_the_contributions_first():
    inputs = {"employment_income": 150000, "pension_employer": 75000}
    steps = _pension_tip(build_tips(_ctx(inputs, 2025, date(2026, 1, 15))))["how_to_execute"]
    assert steps[0].startswith("Stop what you still control before 5 Apr 2026")
    assert "SA101" in steps[1]


def test_tip_open_year_caps_at_relevant_earnings():
    inputs = {"employment_income": 30000, "pension_prior_1": 0.01, "pension_prior_2": 0.01}
    tip = _pension_tip(build_tips(_ctx(inputs, 2025, date(2026, 1, 15))))
    assert "£30,000.00 gross" in tip["what_to_do"] and "relevant UK earnings" in tip["what_to_do"]
    assert tip["estimated_win_gbp"] == round(30000 * 0.20)


def test_tip_closed_year_reports_no_charge_and_carry_forward():
    tip = _pension_tip(build_tips(_ctx(FIXTURE_INPUTS_2025, 2025, date(2026, 8, 26), PRIOR_YEARS)))
    assert "before 5 April" not in tip["what_to_do"]
    # The oldest year's remainder aged out with the year, so that leads the title.
    assert tip["title"] == "2025/26: £22,928.01 of 2022/23 allowance expired unused"
    assert "2023/24 £50,796.48" in tip["what_to_do"]
    assert "£22,928.01" in tip["what_to_do"] and "expired" in tip["what_to_do"]
    assert tip["estimated_win_gbp"] is None and tip["deadline"] is None
    assert tip["status"] == "lost"
    assert "£22,928.01 of unused 2022/23 allowance expired on 5 Apr 2026" in tip["status_note"]


def test_tip_closed_year_without_expiry_has_no_status():
    inputs = {"employment_income": 80000, "pension_employer": 60000, "pension_prior_3": 40000}
    tip = _pension_tip(build_tips(_ctx(inputs, 2025, date(2026, 8, 26))))
    assert tip["title"].startswith("2025/26: no annual allowance charge")
    assert tip["status"] is None and tip["status_note"] is None


def test_tip_open_year_flags_carry_forward_about_to_expire():
    tip = _pension_tip(build_tips(_ctx(FIXTURE_INPUTS_2025, 2025, date(2026, 1, 15), PRIOR_YEARS)))
    assert tip["status"] == "expiring"
    assert "£22,928.01 of 2022/23 carry-forward expires on 5 Apr 2026" in tip["status_note"]


def test_tip_closed_year_reports_charge():
    inputs = {"employment_income": 150000, "pension_employer": 75000}
    tip = _pension_tip(build_tips(_ctx(inputs, 2024, date(2025, 6, 1))))
    assert tip["title"] == "2024/25: annual allowance charge on £15,000.00"
    assert "SA101" in tip["what_to_do"]
    assert tip["deadline"] == "2026-01-31"
    assert tip["status"] == "lost"
    assert "charge of about £6,750.00 is due" in tip["status_note"]


def test_tip_open_year_excess_warns_of_charge():
    inputs = {"employment_income": 150000, "pension_employer": 75000}
    tip = _pension_tip(build_tips(_ctx(inputs, 2025, date(2026, 1, 15))))
    assert tip["title"] == "Pension input exceeds your allowance by £15,000.00"
    assert tip["estimated_win_gbp"] is None
    assert tip["status"] == "expiring"
    assert "unless contributions are cut before 5 Apr 2026" in tip["status_note"]


def test_tip_prefers_prior_year_planner_when_no_explicit_total():
    inputs = {"employment_income": 100000}
    prior = {
        2024: {
            "inputs": {"employment_income": 90000, "pension_employee": 5000, "sipp_paid": 8000},
            "invest": {"dividends_total": 2000},
        }
    }
    tip = _pension_tip(build_tips(_ctx(inputs, 2025, date(2026, 1, 15), prior)))
    # 2024/25 input = 5,000 + 8,000/0.8 = 15,000 → 45,000 unused; own year 60,000
    assert tip["title"] == "£105,000.00 of pension annual allowance unused"
    assert "2024/25" in tip["detail"] and "£45,000.00" in tip["detail"]


def test_money_helper_keeps_pence():
    assert pension_aa.money(7067.47) == D("7067.47")
    assert pension_aa.money("0.1") + pension_aa.money(0.2) == D("0.30")
