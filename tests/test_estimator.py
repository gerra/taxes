"""The Self Assessment estimator, checked against a real 2024/25 return.

Figures come from an HMRC-accepted 2024/25 return for an additional-rate
taxpayer (employment income ~£332k, so every gain sits above the basic rate
band and every allowance except the £500 dividend allowance is nil).

HMRC rounds gains down and reliefs up to whole pounds before applying rates,
and the return itself only ever computes CGT at the pre-30-Oct-2024 rates —
the extra due on later disposals goes in Capital Gains Summary box 51. Each
assertion therefore allows the £1 the rounding can move a figure by, except
where the spec pins an exact arithmetic identity.
"""

from decimal import Decimal

import pytest

from core import estimator, tax_years

Y2024 = tax_years.get_year(2024)
Y2023 = tax_years.get_year(2023)
Y2025 = tax_years.get_year(2025)

# META disposals, USD already converted to GBP, dealing fees already deducted.
META_2024 = [
    {"date": "2024-05-16", "symbol": "META", "gain": "185.90"},
    {"date": "2024-08-26", "symbol": "META", "gain": "2339.05"},
    {"date": "2025-02-25", "symbol": "META", "gain": "6038.57"},
]


def f(value) -> float:
    return float(value)


# ── Capital gains: the 2024/25 split-rate year ────────────────────────────────


def test_total_and_taxable_gain():
    r = estimator.cgt_for_year(META_2024, Y2024, basic_room=0)
    assert f(r["total_gain"]) == pytest.approx(8563.52)
    assert f(r["taxable_gain"]) == pytest.approx(5563.52)
    assert r["annual_exempt_amount"] == Decimal(3000)


def test_sa_return_computes_the_whole_year_at_pre_october_rates():
    """What the SA return's own calculation produces: 5,563 × 20%."""
    r = estimator.cgt_for_year(META_2024, Y2024, basic_room=0)
    assert f(r["sa_cgt_at_pre_oct_rates"]) == pytest.approx(1112.60, abs=0.01)


def test_cgt_adjustment_matches_hmrcs_own_calculator():
    """Box 51 on the Capital Gains Summary: HMRC's calculator returned £122."""
    r = estimator.cgt_for_year(META_2024, Y2024, basic_room=0)
    assert f(r["cgt_adjustment"]) == pytest.approx(122, abs=1)


def test_cgt_total_splits_at_30_october_and_is_not_a_flat_24_percent():
    r = estimator.cgt_for_year(META_2024, Y2024, basic_room=0)
    # 2,525 @ 20% (pre-30-Oct) + (6,039 − 3,000) @ 24% (post-30-Oct)
    assert f(r["cgt_total"]) == pytest.approx(1234.36, abs=1)
    # The old flat-24% answer must not survive.
    assert f(r["cgt_total"]) != pytest.approx(1335.24, abs=1)
    assert f(r["cgt_total"]) == pytest.approx(
        f(r["sa_cgt_at_pre_oct_rates"]) + f(r["cgt_adjustment"])
    )


def test_annual_exempt_amount_goes_against_the_highest_rate_gains_first():
    """An additional-rate payer's post-30-Oct gains are taxed at 24%, so the
    £3,000 must land there, not on the 20% pre-30-Oct gains."""
    r = estimator.cgt_for_year(META_2024, Y2024, basic_room=0)
    by_key = {b["key"]: b for b in r["buckets"]}
    assert f(by_key["post_30_oct"]["relief"]) == pytest.approx(3000)
    assert f(by_key["pre_30_oct"]["relief"]) == pytest.approx(0)


def test_losses_also_go_against_the_highest_rate_gains_first():
    disposals = [
        {"date": "2024-05-16", "gain": "10000.00"},
        {"date": "2025-02-25", "gain": "10000.00"},
        {"date": "2025-03-01", "gain": "-4000.00"},
    ]
    r = estimator.cgt_for_year(disposals, Y2024, basic_room=0)
    by_key = {b["key"]: b for b in r["buckets"]}
    # £4,000 loss + £3,000 AEA = £7,000 of relief, all against the 24% gains.
    assert f(by_key["post_30_oct"]["relief"]) == pytest.approx(7000)
    assert f(by_key["pre_30_oct"]["relief"]) == pytest.approx(0)
    assert f(r["cgt_total"]) == pytest.approx(10000 * 0.20 + 3000 * 0.24, abs=1)


def test_exempt_disposals_are_left_out_entirely():
    disposals = [
        *META_2024,
        {"date": "2024-07-15", "symbol": "GILT", "gain": "500.00", "exempt": True},
    ]
    r = estimator.cgt_for_year(disposals, Y2024, basic_room=0)
    assert f(r["total_gain"]) == pytest.approx(8563.52)


# ── Capital gains: band filling for a basic-rate taxpayer ─────────────────────


def test_basic_rate_band_is_filled_with_the_lowest_rate_gains_first():
    """Gains straddling the band, disposals either side of 30 Oct 2024.

    £10,000 of room in the basic rate band, £10,000 of gains on each side of
    the change. The pre-30-Oct gains save 10 points by sitting in the band
    (10% vs 20%) and the post-30-Oct ones only 6 (18% vs 24%), so the band goes
    to the pre-30-Oct gains.
    """
    disposals = [
        {"date": "2024-06-01", "gain": "10000.00"},
        {"date": "2024-12-01", "gain": "10000.00"},
    ]
    r = estimator.cgt_for_year(disposals, Y2024, basic_room=10000)
    by_key = {b["key"]: b for b in r["buckets"]}
    # AEA (£3,000) still goes against the 24% gains first.
    assert f(by_key["post_30_oct"]["relief"]) == pytest.approx(3000)
    # £10,000 pre-30-Oct fills the band at 10%; £7,000 post-30-Oct sits at 24%.
    assert f(by_key["pre_30_oct"]["at_basic"]) == pytest.approx(10000)
    assert f(by_key["pre_30_oct"]["at_higher"]) == pytest.approx(0)
    assert f(by_key["post_30_oct"]["at_basic"]) == pytest.approx(0)
    assert f(by_key["post_30_oct"]["at_higher"]) == pytest.approx(7000)
    assert f(r["cgt_total"]) == pytest.approx(10000 * 0.10 + 7000 * 0.24, abs=1)
    # The naive alternative — band to the later gains — costs more.
    assert f(r["cgt_total"]) < 10000 * 0.18 + 7000 * 0.20


def test_basic_rate_payer_with_only_pre_october_gains_pays_ten_percent():
    disposals = [{"date": "2024-06-01", "gain": "5000.00"}]
    r = estimator.cgt_for_year(disposals, Y2024, basic_room=50000)
    assert f(r["cgt_total"]) == pytest.approx(2000 * 0.10, abs=1)
    assert f(r["cgt_adjustment"]) == pytest.approx(0, abs=0.01)


def test_basic_rate_payer_with_only_post_october_gains_pays_eighteen_percent():
    disposals = [{"date": "2024-12-01", "gain": "5000.00"}]
    r = estimator.cgt_for_year(disposals, Y2024, basic_room=50000)
    assert f(r["cgt_total"]) == pytest.approx(2000 * 0.18, abs=1)
    # The return computes 10%; box 51 carries the other 8 points.
    assert f(r["sa_cgt_at_pre_oct_rates"]) == pytest.approx(2000 * 0.10, abs=1)
    assert f(r["cgt_adjustment"]) == pytest.approx(2000 * 0.08, abs=1)


def test_gains_straddling_the_band_within_one_rate_period():
    disposals = [{"date": "2024-12-01", "gain": "13000.00"}]
    r = estimator.cgt_for_year(disposals, Y2024, basic_room=4000)
    assert f(r["cgt_total"]) == pytest.approx(4000 * 0.18 + 6000 * 0.24, abs=1)


# ── Capital gains: years without a mid-year change ────────────────────────────


@pytest.mark.parametrize(
    "tax_year,year,dates",
    [
        (2023, Y2023, ("2023-06-01", "2024-01-15")),
        (2025, Y2025, ("2025-06-01", "2026-01-15")),
    ],
)
def test_single_rate_year_has_no_split_and_no_adjustment(tax_year, year, dates):
    disposals = [{"date": d, "gain": "5000.00"} for d in dates]
    r = estimator.cgt_for_year(disposals, year, basic_room=0)
    assert r["split_applies"] is False
    assert len([b for b in r["buckets"] if b["gain"]]) == 1
    assert f(r["cgt_adjustment"]) == pytest.approx(0, abs=0.005)
    assert f(r["cgt_total"]) == pytest.approx(f(r["sa_cgt_at_pre_oct_rates"]), abs=0.005)


def test_2023_24_charges_twenty_percent_and_2025_26_charges_twenty_four():
    d23 = [{"date": "2023-06-01", "gain": "10000.00"}]
    d25 = [{"date": "2025-06-01", "gain": "10000.00"}]
    assert f(estimator.cgt_for_year(d23, Y2023, basic_room=0)["cgt_total"]) == pytest.approx(
        4000 * 0.20, abs=1
    )
    assert f(estimator.cgt_for_year(d25, Y2025, basic_room=0)["cgt_total"]) == pytest.approx(
        7000 * 0.24, abs=1
    )


def test_2024_25_flags_the_box_51_adjustment_for_the_ui():
    r = estimator.cgt_for_year(META_2024, Y2024, basic_room=0)
    assert r["split_applies"] is True
    assert r["needs_box_51_adjustment"] is True
    assert "51" in r["adjustment_note"]
    assert "30 Oct 2024" in r["adjustment_note"]


def test_no_box_51_note_when_every_disposal_is_after_the_change():
    r = estimator.cgt_for_year([{"date": "2024-12-01", "gain": "100.00"}], Y2024, basic_room=0)
    # Under the AEA: nothing to adjust.
    assert r["needs_box_51_adjustment"] is False


# ── Distribution classification ───────────────────────────────────────────────


def _div(symbol, amount, *, country="GB", tax="0", date="2024-08-01", is_interest=False):
    return {
        "date": date,
        "symbol": symbol,
        "country": country,
        "isin": f"{country}00{symbol}0000",
        "amount_gbp": amount,
        "tax_at_source_gbp": tax,
        "is_interest": is_interest,
        "treaty": None,
    }


CLASSIFY_BUNDLE = {
    "dividends": [
        _div("META", "183.10", country="US", tax="-27.47", date="2024-06-26"),
        _div("LAND", "120.00", tax="-30.00"),
        _div("PHP", "80.64", tax="-20.16"),
        _div("VGOV", "45.00", country="IE"),
        _div("VUSC", "30.00", country="IE"),
        _div("ERNS", "25.00", country="IE"),
        _div("ULVR", "60.00"),
    ],
    "interest": [
        {
            "date": "2024-09-01",
            "broker": "Freetrade",
            "currency": "GBP",
            "uk": True,
            "amount_gbp": "5.28",
        },
        {
            "date": "2024-09-01",
            "broker": "Charles Schwab",
            "currency": "USD",
            "uk": False,
            "amount_gbp": "9.37",
        },
    ],
    "other_income": [],
    "eri_distributions": [],
}


def _by_symbol(rows):
    return {r["symbol"]: r for r in rows}


def test_reit_distributions_are_property_income_not_dividends():
    rows = _by_symbol(estimator.classify_distributions(CLASSIFY_BUNDLE))
    for ticker in ("LAND", "PHP"):
        assert rows[ticker]["kind"] == "property_income_distribution"
        assert rows[ticker]["taxed_as"] == "property"
        assert not rows[ticker]["uses_dividend_allowance"]
    assert f(rows["PHP"]["withheld_gbp"]) == pytest.approx(20.16)


def test_bond_fund_distributions_are_interest_not_dividends():
    rows = _by_symbol(estimator.classify_distributions(CLASSIFY_BUNDLE))
    for ticker in ("VGOV", "VUSC", "ERNS"):
        assert rows[ticker]["kind"] == "interest_distribution"
        assert rows[ticker]["taxed_as"] == "savings"
        assert not rows[ticker]["uses_dividend_allowance"]


def test_ordinary_uk_and_foreign_dividends_stay_dividends():
    rows = _by_symbol(estimator.classify_distributions(CLASSIFY_BUNDLE))
    assert rows["ULVR"]["kind"] == "uk_dividend"
    assert rows["META"]["kind"] == "foreign_dividend"
    assert rows["META"]["taxed_as"] == "dividend"
    assert rows["META"]["uses_dividend_allowance"]


def test_cash_interest_is_split_uk_and_foreign():
    rows = estimator.classify_distributions(CLASSIFY_BUNDLE)
    kinds = {r["kind"] for r in rows}
    assert "uk_interest" in kinds and "foreign_interest" in kinds


def test_itemised_table_carries_the_audit_columns():
    for row in estimator.classify_distributions(CLASSIFY_BUNDLE):
        assert set(row) >= {
            "date",
            "symbol",
            "gross_gbp",
            "withheld_gbp",
            "kind",
            "label",
            "why",
            "amount_gbp",
            "currency",
            "fx_rate",
        }


def test_classified_totals_move_reits_and_bond_funds_out_of_dividends():
    t = estimator.income_totals(estimator.classify_distributions(CLASSIFY_BUNDLE))
    assert f(t["uk_dividends"]) == pytest.approx(60.00)
    assert f(t["foreign_dividends"]) == pytest.approx(183.10)
    assert f(t["dividends_total"]) == pytest.approx(243.10)
    assert f(t["property_income"]) == pytest.approx(200.64)
    assert f(t["property_income_tax"]) == pytest.approx(50.16)
    # £100 of bond-fund distributions land in savings income, not dividends.
    assert f(t["interest_distributions"]) == pytest.approx(100.00)
    assert f(t["uk_interest"]) == pytest.approx(5.28)
    assert f(t["foreign_interest"]) == pytest.approx(9.37)
    assert f(t["savings_total"]) == pytest.approx(114.65)
    assert f(t["foreign_dividend_tax"]) == pytest.approx(27.47)


def test_gilt_and_tbill_gains_are_not_capital_gains():
    assert estimator.is_cgt_exempt({"exempt": True}) is True


# ── Foreign tax credit relief ─────────────────────────────────────────────────


def test_ftcr_is_the_lower_of_withheld_treaty_rate_and_uk_tax():
    relief = estimator.ftcr(
        gross=Decimal("183.10"),
        withheld=Decimal("27.47"),
        treaty_rate=Decimal("0.15"),
        uk_tax_on_income=Decimal("72.05"),
    )
    assert f(relief) == pytest.approx(27.47, abs=0.01)


def test_ftcr_is_capped_at_the_treaty_rate_when_more_was_withheld():
    # 30% withheld because the W-8BEN lapsed: only 15% is creditable.
    relief = estimator.ftcr(
        gross=Decimal("183.10"),
        withheld=Decimal("54.93"),
        treaty_rate=Decimal("0.15"),
        uk_tax_on_income=Decimal("72.05"),
    )
    assert f(relief) == pytest.approx(27.47, abs=0.01)


def test_ftcr_is_capped_at_the_uk_tax_on_that_income():
    relief = estimator.ftcr(
        gross=Decimal("183.10"),
        withheld=Decimal("27.47"),
        treaty_rate=Decimal("0.15"),
        uk_tax_on_income=Decimal("10.00"),
    )
    assert f(relief) == pytest.approx(10.00)


# ── Payments on account ───────────────────────────────────────────────────────


def test_payments_on_account_ignore_cgt():
    """The real 2024/25 return: £160.94 of non-CGT liability, so nothing due,
    even though the headline bill including CGT is over £1,000."""
    r = estimator.payments_on_account(
        liability_excluding_cgt=Decimal("160.94"),
        tax_collected_at_source=Decimal("120000"),
        total_liability_excluding_cgt=Decimal("120160.94"),
    )
    assert r["required"] is False
    assert f(r["each_instalment"]) == pytest.approx(0)
    assert r["over_threshold"] is False
    assert r["under_80_percent_at_source"] is False


def test_payments_on_account_when_both_conditions_are_met():
    r = estimator.payments_on_account(
        liability_excluding_cgt=Decimal("4000"),
        tax_collected_at_source=Decimal("5000"),
        total_liability_excluding_cgt=Decimal("9000"),
    )
    assert r["over_threshold"] is True
    assert r["under_80_percent_at_source"] is True
    assert r["required"] is True
    assert f(r["each_instalment"]) == pytest.approx(2000)


def test_payments_on_account_not_required_when_enough_was_taxed_at_source():
    r = estimator.payments_on_account(
        liability_excluding_cgt=Decimal("1500"),
        tax_collected_at_source=Decimal("50000"),
        total_liability_excluding_cgt=Decimal("51500"),
    )
    assert r["over_threshold"] is True
    assert r["under_80_percent_at_source"] is False
    assert r["required"] is False


def test_payments_on_account_reports_both_conditions_for_display():
    r = estimator.payments_on_account(
        liability_excluding_cgt=Decimal("160.94"),
        tax_collected_at_source=Decimal("120000"),
        total_liability_excluding_cgt=Decimal("120160.94"),
    )
    assert f(r["threshold"]) == 1000
    assert f(r["percent_at_source"]) == pytest.approx(99.87, abs=0.01)
    assert r["explain"]
