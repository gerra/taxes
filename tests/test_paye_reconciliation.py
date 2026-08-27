"""The 2023/24 PAYE reconciliation, against the return as actually filed.

The real numbers behind this file: a P60 showing £220,031.43 of pay and
£84,533.40 of tax deducted under final tax code 151T. That code granted about
£1,519 of personal allowance, which at £220k is worth nothing — the allowance
tapers to nil from £125,140 — so PAYE taxed £218,512 instead of £220,031 and
under-collected £683.55. The Self Assessment bill was almost entirely that
shortfall, and a tool that looked only at investment income put the year at
£40.40 when the real bill was £621.45.

Three fixtures:

A. The return as it was actually filed, with its two mistakes intact (a £20
   typo in the tax deducted, and the taxable gain typed into the "tax already
   paid on gains" box). Must reproduce £621.45 exactly — it is the only figure
   here that is checkable against reality.
B. The correct figures: the P60 to the penny, and the foreign interest that the
   filed return left out.
C. No employment figures at all: the estimate falls back to investment income
   and has to say what it is leaving out.
"""

import pytest

from core import estimator, paye, tax_years
from core.self_assessment import Inputs, compute, to_json

Y = tax_years.get_year(2023)


def _bill(**over):
    """The bill as the API sends it: floats to the penny, which is also the
    precision anything downstream of this ever sees."""
    return to_json(compute(Inputs(year=Y, tax_year=2023, **over)))


# ── Test case A: the return as filed ──────────────────────────────────────────
#
# Every figure is as it went onto the return: already rounded to whole pounds,
# £84,553.40 of tax deducted (a transposed digit — the P60 said £84,533.40), and
# £54 in the "tax already paid on gains" box, which was in fact the taxable
# gain and not tax at all.

CASE_A = {
    "employments": [{"name": "Employer", "pay": "220031", "tax_deducted": "84553.40"}],
    "uk_interest": "2",
    "foreign_interest": "0",
    "foreign_dividends": "42",
    "foreign_dividend_tax": "11",
    "disposals": [
        {"date": "2024-01-15", "gain": "6164"},
        {"date": "2024-01-15", "gain": "-109"},
    ],
    "tax_paid_on_gains": "54",
}


@pytest.fixture
def case_a():
    return _bill(**CASE_A)


def test_case_a_reproduces_the_filed_bill_exactly(case_a):
    """£621.45. This is the assertion the whole module exists for."""
    assert case_a["sa_bill"] == pytest.approx(621.45)


def test_case_a_income_tax_on_employment(case_a):
    # 37,700 @ 20% = 7,540.00
    # (125,140 - 37,700) @ 40% = 34,976.00
    # (220,031 - 125,140) @ 45% = 42,700.95
    assert case_a["income_tax"]["non_savings"] == pytest.approx(85216.95)


def test_case_a_savings_and_dividends(case_a):
    # £2 of interest at 45%: the personal savings allowance is nil at this income.
    assert case_a["income_tax"]["savings"] == pytest.approx(0.90)
    # £42 of foreign dividends sits inside the £1,000 dividend allowance.
    assert case_a["income_tax"]["dividends_gross"] == pytest.approx(0)


def test_case_a_foreign_tax_credit_is_nil_inside_the_dividend_allowance(case_a):
    """£11 was withheld abroad, but the dividend bore no UK tax, and relief is
    capped at the UK tax on that same income. Nothing to credit."""
    assert case_a["ftcr"]["total"] == pytest.approx(0)
    assert case_a["ftcr"]["foreign_dividend_tax"] == pytest.approx(11)


def test_case_a_total_income_tax_and_shortfall(case_a):
    assert case_a["income_tax"]["total"] == pytest.approx(85217.85)
    assert case_a["at_source"]["total"] == pytest.approx(84553.40)
    assert case_a["income_tax_shortfall"] == pytest.approx(664.45)


def test_case_a_capital_gains(case_a):
    # (6,164 - 109) - 6,000 annual exempt amount = 55, all above the basic band.
    assert case_a["cgt"]["cgt_total"] == pytest.approx(11.00)


def test_case_a_investment_only_subtotal(case_a):
    """What this tool used to show: 0.90 + 0 + 11.00 - 54.00."""
    assert case_a["investment_only"] == pytest.approx(-42.10)


def test_case_a_breakdown_rows_sum_to_the_bill(case_a):
    rows = {r["key"]: float(r["amount"]) for r in case_a["rows"]}
    assert rows["total"] == pytest.approx(621.45)
    assert sum(v for k, v in rows.items() if k != "total") == pytest.approx(rows["total"])


def test_case_a_warns_about_the_tax_already_paid_box(case_a):
    """The £54 was the taxable gain, not tax paid. HMRC credited it anyway."""
    assert any("real-time service" in w for w in case_a["warnings"])
    assert any("Do not enter the taxable gain here" in w for w in case_a["warnings"])


def test_case_a_warns_that_foreign_interest_is_missing(case_a):
    """Foreign dividends but no foreign interest: the £63.56 the real return
    left off. USD cash at the same broker almost always pays interest."""
    assert any("foreign dividends but no foreign interest" in w for w in case_a["warnings"])


# ── Test case B: the correct figures ──────────────────────────────────────────

CASE_B = {
    "employments": [
        {"name": "Employer", "pay": "220031.43", "tax_deducted": "84533.40", "tax_code": "151T"}
    ],
    "uk_interest": "2.22",
    "foreign_interest": "63.56",
    "foreign_dividends": "33.58",
    "disposals": [
        {"date": "2024-01-15", "gain": "6164.66"},
        {"date": "2024-01-15", "gain": "-109.76"},
    ],
}


@pytest.fixture
def case_b():
    return _bill(**CASE_B)


def test_case_b_employment_shortfall(case_b):
    """£85,216.95 due on £220,031, £84,533.40 collected."""
    assert case_b["income_tax"]["non_savings"] == pytest.approx(85216.95)
    assert case_b["employment_shortfall"] == pytest.approx(683.55)


def test_case_b_interest_includes_the_foreign_part(case_b):
    """£2 + £63 = £65 at 45%. Each source rounds down on its own, so £2.22 and
    £63.56 become £2 and £63 rather than £65.78 becoming £65."""
    assert case_b["income"]["uk_interest"] == pytest.approx(2)
    assert case_b["income"]["foreign_interest"] == pytest.approx(63)
    assert case_b["income_tax"]["savings"] == pytest.approx(29.25)


def test_case_b_capital_gains_round_hmrcs_way(case_b):
    """Losses round UP (£109.76 -> £110), gains DOWN: 6,164.66 - 110 - 6,000
    = 54.66 -> £54 at 20%."""
    assert case_b["cgt"]["cgt_total"] == pytest.approx(10.80)


def test_case_b_total_bill(case_b):
    assert case_b["sa_bill"] == pytest.approx(723.60)


def test_case_b_investment_only_subtotal(case_b):
    assert case_b["investment_only"] == pytest.approx(40.05)


def test_case_b_bill_is_mostly_paye_catch_up(case_b):
    """The point of the whole change: the investment income is a rounding error
    next to what the tax code got wrong."""
    assert case_b["sa_bill"] - case_b["investment_only"] == pytest.approx(683.55)


def test_case_b_tax_code_explains_the_shortfall_completely(case_b):
    """151T -> £1,519 allowance -> taxable £218,512 -> £84,533.40, exactly what
    the P60 says. So the code accounts for the shortfall on its own."""
    explanation = case_b["tax_code_explanation"]
    assert explanation["explains"] is True
    assert explanation["implied_tax"] == pytest.approx(84533.40)
    assert "fully explained by tax code 151T" in explanation["message"]
    assert "£1,519" in explanation["message"]


def test_case_b_payments_on_account_fail_both_tests(case_b):
    """Balancing payment £712.80 (under £1,000) and 99.2% collected at source
    (not under 80%). Neither test passes, so no payment on account."""
    poa = case_b["payments_on_account"]
    assert poa["liability_excluding_cgt"] == pytest.approx(712.80)
    assert poa["over_threshold"] is False
    assert float(poa["percent_at_source"]) == pytest.approx(99.2, abs=0.05)
    assert poa["under_80_percent_at_source"] is False
    assert poa["required"] is False


def test_case_b_balancing_payment_is_not_the_interest_tax(case_b):
    """The old bug: the payments-on-account test used the £29.60 of interest tax
    as the balancing payment. It is the whole income tax shortfall."""
    poa = case_b["payments_on_account"]
    assert poa["liability_excluding_cgt"] != pytest.approx(29.25)
    assert poa["liability_excluding_cgt"] == pytest.approx(case_b["income_tax_shortfall"], abs=0.01)


def test_case_b_payments_on_account_exclude_capital_gains(case_b):
    poa = case_b["payments_on_account"]
    assert poa["liability_excluding_cgt"] + case_b["cgt"]["cgt_total"] == pytest.approx(
        case_b["sa_bill"]
    )


def test_case_b_pence_precise_mode_keeps_the_interest_pence():
    """The secondary figure: without HMRC's rounding, £65.78 at 45% is £29.60
    and the investment-only sub-total is the £40.40 this tool used to show."""
    exact = _bill(**CASE_B, rounding_mode=estimator.ROUNDING_EXACT)
    assert float(exact["income_tax"]["savings"]) == pytest.approx(29.60, abs=0.005)
    assert float(exact["investment_only"]) == pytest.approx(40.40, abs=0.005)


def test_case_b_pence_precise_mode_says_it_is_not_the_real_bill():
    exact = _bill(**CASE_B, rounding_mode=estimator.ROUNDING_EXACT)
    assert any("not what will be charged" in w for w in exact["warnings"])


def test_case_b_reconciles_to_what_was_actually_paid(case_b):
    """£723.60 correct against £621.45 filed: about £102 under, made up of the
    missing foreign interest, the wrongly claimed £54 credit and the £20 typo."""
    filed = _bill(**CASE_A)
    assert float(case_b["sa_bill"] - filed["sa_bill"]) == pytest.approx(102.15, abs=0.01)


# ── Test case C: no P60 figures ───────────────────────────────────────────────
#
# The same investment figures as B, with the employment section left blank —
# which in practice means a planner saved before the section existed: the pay is
# known (it has to be, or the gains and interest land in the wrong bands) but
# what PAYE collected is not.

CASE_C = {**CASE_B, "employments": [{"name": "Employer", "pay": "220031.43"}]}


@pytest.fixture
def case_c():
    return _bill(**CASE_C)


def test_case_c_falls_back_to_the_investment_figure(case_c):
    assert case_c["reconciled"] is False
    assert case_c["investment_only"] == pytest.approx(40.05)
    assert case_c["sa_bill"] == pytest.approx(40.05)


def test_case_c_counts_no_employment_shortfall(case_c):
    """Not knowing what PAYE collected is not the same as knowing it was right,
    but it is certainly not a reason to invent a year's worth of salary tax."""
    assert case_c["employment_shortfall"] == pytest.approx(0)


def test_case_c_warns_about_what_it_excludes(case_c):
    assert any("excludes any PAYE under- or over-collection" in w for w in case_c["warnings"])
    assert any("Enter your P60" in w for w in case_c["warnings"])


def test_case_c_pence_precise_matches_the_old_headline():
    exact = _bill(**CASE_C, rounding_mode=estimator.ROUNDING_EXACT)
    assert float(exact["investment_only"]) == pytest.approx(40.40, abs=0.005)


def test_case_c_payments_on_account_say_paye_was_assumed(case_c):
    poa = case_c["payments_on_account"]
    assert poa["assumed_paye"] is True
    assert "assumes PAYE collected exactly the right tax" in poa["explain"]


def test_case_c_still_places_income_in_the_right_bands(case_c):
    """Pay without tax deducted is not a reconciliation, but it is still what
    decides whether the gains and interest are charged at basic or additional
    rates. Ignoring it would move the investment figure too."""
    assert case_c["income_tax"]["non_savings"] == pytest.approx(85216.95)
    assert case_c["bands"]["marginal_band"] == "additional"


def test_nothing_entered_at_all_still_produces_a_figure():
    """No employment row of any kind: the investment income is charged on its
    own, which at these amounts is inside the personal allowance."""
    result = _bill(**{k: v for k, v in CASE_B.items() if k != "employments"})
    assert result["reconciled"] is False
    assert result["income_tax"]["savings"] == pytest.approx(0)
    assert any("excludes any PAYE" in w for w in result["warnings"])


# ── Guardrails ────────────────────────────────────────────────────────────────


def test_tax_deducted_is_never_derived_from_the_tax_code():
    """The whole reconciliation is the gap between the code and the P60. If the
    code fed the deduction the gap would always be nil by construction."""
    result = _bill(
        employments=[{"pay": "220031", "tax_deducted": "70000", "tax_code": "151T"}],
    )
    assert result["at_source"]["paye"] == pytest.approx(70000)
    assert result["income_tax_shortfall"] == pytest.approx(85216.95 - 70000)


def test_a_large_gap_between_tax_deducted_and_the_code_is_flagged():
    result = _bill(
        employments=[{"pay": "220031", "tax_deducted": "80000", "tax_code": "151T"}],
    )
    assert any("Check the tax deducted" in w for w in result["warnings"])


def test_the_twenty_pound_typo_is_surfaced_even_below_the_warning_threshold():
    """£20 is inside the ~£25 tolerance, so it raises no warning — but the tax
    code check still prints both figures, which is how it gets noticed."""
    result = _bill(
        employments=[{"pay": "220031", "tax_deducted": "84553.40", "tax_code": "151T"}],
    )
    assert not any("Check the tax deducted" in w for w in result["warnings"])
    explanation = result["tax_code_explanation"]
    assert explanation["explains"] is False
    assert "£84,533.40" in explanation["message"]
    assert "£84,553.40" in explanation["message"]
    assert "£20.00 more" in explanation["message"]


def test_pay_with_no_tax_deducted_at_all_is_flagged():
    result = _bill(employments=[{"pay": "220031", "tax_deducted": "0"}])
    assert any("no tax deducted" in w for w in result["warnings"])


def test_losses_rounded_the_wrong_way_are_flagged():
    """HMRC rounds losses UP, in the taxpayer's favour. Entering the
    rounded-down figure quietly gives away up to £1 of relief."""
    result = _bill(entered_losses="109", reported_losses="109.76")
    assert any("HMRC rounds losses UP" in w and "£110" in w for w in result["warnings"])


def test_losses_rounded_correctly_are_not_flagged():
    result = _bill(entered_losses="110", reported_losses="109.76")
    assert not any("rounds losses UP" in w for w in result["warnings"])


def test_self_employment_income_makes_the_estimate_incomplete():
    result = _bill(**CASE_B, self_employment_income="12000")
    assert any("does not compute tax or Class 2/4" in w for w in result["warnings"])


def test_foreign_interest_is_always_in_the_savings_total():
    """The line the real return left off. It is taxable here even though no
    foreign tax was withheld on it."""
    without = _bill(**{**CASE_C, "foreign_interest": "0"})
    with_it = _bill(**CASE_C)
    assert with_it["income"]["savings"] > without["income"]["savings"]
    assert with_it["income_tax"]["savings"] == pytest.approx(29.25)
    assert without["income_tax"]["savings"] == pytest.approx(0.90)


# ── Benefits, multiple employments, band placement ────────────────────────────


def test_benefits_in_kind_add_to_the_shortfall():
    """A benefit the tax code never picked up is taxable income with no PAYE
    against it, so all of it lands on the bill."""
    plain = _bill(employments=[{"pay": "220031", "tax_deducted": "84533.40"}])
    with_benefits = _bill(
        employments=[{"pay": "220031", "tax_deducted": "84533.40"}], benefits_in_kind="5000"
    )
    assert with_benefits["employment_shortfall"] - plain["employment_shortfall"] == pytest.approx(
        5000 * 0.45
    )


def test_two_employments_are_summed_and_neither_code_is_re_run():
    """HMRC splits one allowance between two codes, so no single code can be
    checked against a single P60 — but the shortfall is still real."""
    result = _bill(
        employments=[
            {"name": "Main", "pay": "200000", "tax_deducted": "80000", "tax_code": "1257L"},
            {"name": "Second", "pay": "20031", "tax_deducted": "4533.40", "tax_code": "BR"},
        ],
    )
    assert result["at_source"]["paye"] == pytest.approx(84533.40)
    assert result["income"]["employment_pay"] == pytest.approx(220031)
    assert result["employment_shortfall"] == pytest.approx(683.55)
    explanation = result["tax_code_explanation"]
    assert explanation["explains"] is False
    assert "2 PAYE employments" in explanation["message"]


def test_the_additional_rate_starts_at_125140_of_taxable_income():
    """Not at £112,570. The higher rate limit is measured in taxable income and
    does not move down when the personal allowance is tapered away — getting
    this wrong shifts £12,570 from 40% to 45%, about £628 of tax."""
    result = _bill(employments=[{"pay": "220031", "tax_deducted": "0"}])
    slices = {s["band"]: float(s["amount"]) for s in result["income_tax"]["slices"]["non_savings"]}
    assert slices["basic"] == pytest.approx(37700)
    assert slices["higher"] == pytest.approx(125140 - 37700)
    assert slices["additional"] == pytest.approx(220031 - 125140)


def test_pension_relief_at_source_extends_both_bands():
    """A £8,000 net contribution is £10,000 gross: it moves both band limits up
    by that much and takes the same off adjusted net income."""
    result = _bill(
        employments=[{"pay": "220031", "tax_deducted": "84533.40"}],
        pension_relief_at_source_net="8000",
    )
    assert float(result["bands"]["basic_limit"]) == pytest.approx(47700)
    assert float(result["bands"]["higher_limit"]) == pytest.approx(135140)
    # £10,000 moves from 40% to 20% at the bottom and another £10,000 from 45%
    # to 40% at the top: £2,000 + £500 of tax saved.
    assert result["income_tax"]["non_savings"] == pytest.approx(85216.95 - 2500)


# ── The personal allowance taper ──────────────────────────────────────────────


def test_allowance_is_nil_above_the_taper_ceiling(case_b):
    assert float(case_b["allowances"]["personal_allowance"]) == pytest.approx(0)


def test_allowance_halves_away_through_the_taper():
    result = _bill(employments=[{"pay": "110000", "tax_deducted": "0"}])
    # £10,000 over £100,000 costs £5,000 of the £12,570 allowance.
    assert float(result["allowances"]["personal_allowance"]) == pytest.approx(7570)


# ── Tax code decoding ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "code,allowance",
    [
        ("151T", 1519),
        ("1257L", 12579),
        ("0T", 0),
        ("K475", -4759),
        ("C1257L", 12579),
    ],
)
def test_numeric_codes_decode_to_an_allowance(code, allowance):
    """Number x 10 + 9, which is how HMRC's own free-pay tables read a code.
    A K code is negative: it adds to taxable pay instead of sheltering it."""
    assert float(paye.decode_tax_code(code).allowance) == pytest.approx(allowance)


@pytest.mark.parametrize("code,band", [("BR", "basic"), ("D0", "higher"), ("D1", "additional")])
def test_flat_rate_codes_charge_every_pound_at_one_rate(code, band):
    decoded = paye.decode_tax_code(code)
    assert decoded.flat_rate == band
    assert float(paye.paye_tax(estimator.dec(10000), decoded, Y)) == pytest.approx(
        10000 * Y["income_rates"][band]
    )


def test_nt_code_deducts_nothing():
    assert paye.paye_tax(estimator.dec(50000), paye.decode_tax_code("NT"), Y) == 0


def test_no_code_decodes_to_nothing():
    assert paye.decode_tax_code("") is None
    assert paye.decode_tax_code(None) is None


@pytest.mark.parametrize("code", ["S1257L", "1257L M1", "1257LM1", "K475W1", "not-a-code"])
def test_codes_that_cannot_be_re_run_say_so(code):
    """Scottish codes have bands this app does not model; a week 1 / month 1
    code taxed each period on its own, so a cumulative re-run never matches."""
    assert paye.decode_tax_code(code).usable is False


def test_an_unusable_code_does_not_suppress_the_shortfall():
    result = _bill(
        employments=[{"pay": "220031", "tax_deducted": "84533.40", "tax_code": "1257L M1"}],
    )
    assert result["employment_shortfall"] == pytest.approx(683.55)
    assert result["tax_code_explanation"]["explains"] is False
    assert "still stands" in result["tax_code_explanation"]["message"]


def test_k_code_adds_to_taxable_pay():
    """K475 on £50,000 taxes £54,759, not £45,241."""
    tax = paye.paye_tax(estimator.dec(50000), paye.decode_tax_code("K475"), Y)
    expected = 37700 * 0.20 + (54759 - 37700) * 0.40
    assert float(tax) == pytest.approx(expected)


# ── Student loan ──────────────────────────────────────────────────────────────


def test_student_loan_is_nine_percent_over_the_threshold():
    result = _bill(
        employments=[{"pay": "50000", "tax_deducted": "9000"}], student_loan_plan="plan_2"
    )
    loan = result["student_loan"]
    assert float(loan["threshold"]) == pytest.approx(27295)
    assert float(loan["total_due"]) == pytest.approx(int((50000 - 27295) * 0.09))


def test_postgraduate_loan_is_six_percent():
    result = _bill(
        employments=[{"pay": "50000", "tax_deducted": "9000"}], student_loan_plan="postgraduate"
    )
    assert float(result["student_loan"]["rate"]) == pytest.approx(0.06)


def test_unearned_income_under_the_limit_is_ignored_entirely():
    result = _bill(
        employments=[{"pay": "50000", "tax_deducted": "9000"}],
        uk_interest="1500",
        student_loan_plan="plan_2",
    )
    loan = result["student_loan"]
    assert float(loan["unearned_counted"]) == pytest.approx(0)
    assert float(loan["income_counted"]) == pytest.approx(50000)


def test_unearned_income_over_the_limit_counts_in_full():
    """Not just the excess — a penny over £2,000 pulls the whole amount in."""
    result = _bill(
        employments=[{"pay": "50000", "tax_deducted": "9000"}],
        uk_interest="2500",
        student_loan_plan="plan_2",
    )
    loan = result["student_loan"]
    assert float(loan["unearned_counted"]) == pytest.approx(2500)
    assert float(loan["income_counted"]) == pytest.approx(52500)


def test_student_loan_already_deducted_comes_off_the_balance():
    result = _bill(
        employments=[{"pay": "50000", "tax_deducted": "9000", "student_loan_deducted": "1500"}],
        student_loan_plan="plan_2",
    )
    loan = result["student_loan"]
    assert float(loan["balance"]) == pytest.approx(float(loan["total_due"]) - 1500)


def test_student_loan_is_not_part_of_the_balancing_payment():
    """TMA 1970 s59A: payments on account cover income tax and Class 4 NIC.
    A student loan repayment is collected through the return but is neither."""
    without = _bill(employments=[{"pay": "50000", "tax_deducted": "9000"}], uk_interest="3000")
    with_loan = _bill(
        employments=[{"pay": "50000", "tax_deducted": "9000"}],
        uk_interest="3000",
        student_loan_plan="plan_2",
    )
    assert with_loan["payments_on_account"]["liability_excluding_cgt"] == pytest.approx(
        without["payments_on_account"]["liability_excluding_cgt"]
    )
    assert float(with_loan["student_loan"]["total_due"]) > 0


def test_a_year_without_verified_thresholds_says_so_instead_of_guessing():
    result = compute(
        Inputs(
            year=tax_years.get_year(2022),
            tax_year=2022,
            employments=[{"pay": "50000", "tax_deducted": "9000"}],
            student_loan_plan="plan_2",
        )
    )
    assert result["student_loan"]["available"] is False
    assert any("thresholds for 2022/23 are not in this app" in w for w in result["warnings"])


# ── Payments on account, computed rather than assumed ─────────────────────────


def test_payments_on_account_when_paye_covers_little_of_a_large_bill():
    """Both conditions met: a five-figure balancing payment, and PAYE covering
    well under 80% of the liability."""
    result = _bill(
        employments=[{"pay": "60000", "tax_deducted": "5000"}],
        uk_interest="20000",
    )
    poa = result["payments_on_account"]
    assert poa["over_threshold"] is True
    assert poa["under_80_percent_at_source"] is True
    assert poa["required"] is True
    assert poa["each_instalment"] == pytest.approx(poa["liability_excluding_cgt"] / 2)


def test_the_eighty_percent_share_is_computed_from_the_liability():
    result = _bill(employments=[{"pay": "100000", "tax_deducted": "20000"}])
    poa = result["payments_on_account"]
    expected = float(poa["tax_collected_at_source"]) / float(result["income_tax"]["total"]) * 100
    # The API rounds to the penny, so the share is exact to two places.
    assert float(poa["percent_at_source"]) == pytest.approx(expected, abs=0.01)
    assert float(poa["percent_at_source"]) < 80
    assert poa["under_80_percent_at_source"] is True


def test_a_large_capital_gain_alone_never_triggers_payments_on_account():
    result = _bill(
        employments=[{"pay": "220031", "tax_deducted": "84533.40", "tax_code": "151T"}],
        disposals=[{"date": "2024-01-15", "gain": "200000"}],
    )
    assert result["cgt"]["cgt_total"] > 1000
    assert result["payments_on_account"]["required"] is False


# ── Already paid ──────────────────────────────────────────────────────────────


def test_payments_on_account_already_made_come_off_the_bill():
    result = _bill(**CASE_B, payments_on_account_made="500")
    assert result["sa_bill"] == pytest.approx(723.60 - 500)


def test_payments_already_made_do_not_change_the_balancing_payment_test():
    """What you have paid on account is not part of deciding whether payments on
    account are due — that test looks at the liability, not the settlement."""
    plain = _bill(**CASE_B)
    paid = _bill(**CASE_B, payments_on_account_made="500")
    assert paid["payments_on_account"]["liability_excluding_cgt"] == pytest.approx(
        plain["payments_on_account"]["liability_excluding_cgt"]
    )


def test_a_refund_shows_as_a_negative_bill():
    """PAYE over-collecting is the same arithmetic with the sign flipped."""
    result = _bill(employments=[{"pay": "220031", "tax_deducted": "86000"}])
    assert result["income_tax_shortfall"] < 0
    assert result["sa_bill"] == pytest.approx(85216.95 - 86000)


# ── Rounding ──────────────────────────────────────────────────────────────────


def test_round_for_tax_takes_income_down_and_losses_up():
    assert estimator.round_for_tax("100.99", "income") == 100
    assert estimator.round_for_tax("100.01", "loss") == 101
    assert estimator.round_for_tax("100.99", "gain") == 100
    assert estimator.round_for_tax("100.01", "relief") == 101


def test_round_for_tax_defaults_to_hmrc_behaviour():
    assert estimator.round_for_tax("100.99", "income") == estimator.round_for_tax(
        "100.99", "income", estimator.ROUNDING_HMRC
    )


def test_round_for_tax_exact_mode_keeps_the_pence():
    assert estimator.round_for_tax("100.99", "income", estimator.ROUNDING_EXACT) == estimator.dec(
        "100.99"
    )


@pytest.mark.parametrize("bad", ["nonsense", ""])
def test_round_for_tax_rejects_an_unknown_mode(bad):
    with pytest.raises(ValueError):
        estimator.round_for_tax("1", "income", bad)


def test_round_for_tax_rejects_an_unknown_kind():
    with pytest.raises(ValueError):
        estimator.round_for_tax("1", "sideways")
