"""End-to-end estimator check against the filed 2024/25 return.

Additional-rate taxpayer: employment income £332,000, so the personal
allowance and the personal savings allowance are both nil and only the £500
dividend allowance survives. Every gain sits above the basic rate band.
"""

import pytest

from core import report_view, tax_years
from core.tax_profile import build_profile

Y = tax_years.get_year(2024)
INPUTS = {"employment_income": 332000}

BUNDLE = {
    "totals": {
        "disposal_count": 3,
        "disposal_proceeds": "60000.00",
        "allowable_costs": "51436.48",
        "capital_gain_before_losses": "8563.52",
        "capital_loss": "0",
        "total_gain": "8563.52",
        "capital_gain_allowance": "3000",
        "taxable_gain": "5563.52",
        "dividends_total": "821.53",
        "dividend_treaty_relief": "27.47",
        "dividend_allowance": "500",
        "dividends_taxable": "294.06",
        "uk_interest": "5.28",
        "foreign_interest": "9.37",
        "other_income": "0",
        "other_income_tax": "0",
        "eri_dividends": "0",
        "eri_interest": "0",
    },
    "disposals": [
        {"date": "2024-05-16", "symbol": "META", "gain": "185.90", "amount": "0", "entries": []},
        {"date": "2024-08-26", "symbol": "META", "gain": "2339.05", "amount": "0", "entries": []},
        {"date": "2025-02-25", "symbol": "META", "gain": "6038.57", "amount": "0", "entries": []},
    ],
    "dividends": [
        {
            "date": "2024-06-26",
            "symbol": "META",
            "country": "US",
            "isin": "US30303M1027",
            "amount_gbp": "183.10",
            "tax_at_source_gbp": "-27.47",
            "is_interest": False,
            "currency": "USD",
            "gross": "231.73",
            "fx_rate": "1.2657",
            "treaty": {
                "country": "USA",
                "country_rate": "0.15",
                "treaty_rate": "0.15",
                "relief_gbp": "27.47",
            },
        },
        # UK-listed holdings the broker labelled "dividend".
        {
            "date": "2024-08-08",
            "symbol": "LAND",
            "country": "GB",
            "isin": "GB00BYW0PQ60",
            "amount_gbp": "150.00",
            "gross": "150.00",
            "tax_at_source_gbp": "-37.50",
            "is_interest": False,
            "currency": "GBP",
            "fx_rate": "1",
            "treaty": None,
        },
        {
            "date": "2024-05-08",
            "symbol": "PHP",
            "country": "GB",
            "isin": "GB00BYRJ5J14",
            "amount_gbp": "80.64",
            "gross": "80.64",
            "tax_at_source_gbp": "-20.16",
            "is_interest": False,
            "currency": "GBP",
            "fx_rate": "1",
            "treaty": None,
        },
        {
            "date": "2024-07-15",
            "symbol": "VGOV",
            "country": "IE",
            "isin": "IE00B42WWV65",
            "amount_gbp": "180.20",
            "gross": "180.20",
            "tax_at_source_gbp": "0",
            "is_interest": False,
            "currency": "GBP",
            "fx_rate": "1",
            "treaty": None,
        },
        {
            "date": "2024-10-15",
            "symbol": "VUSC",
            "country": "IE",
            "isin": "IE00BGYWT403",
            "amount_gbp": "120.09",
            "gross": "120.09",
            "tax_at_source_gbp": "0",
            "is_interest": False,
            "currency": "GBP",
            "fx_rate": "1",
            "treaty": None,
        },
        {
            "date": "2025-01-15",
            "symbol": "ERNS",
            "country": "IE",
            "isin": "IE00B3VTMJ91",
            "amount_gbp": "107.50",
            "gross": "107.50",
            "tax_at_source_gbp": "0",
            "is_interest": False,
            "currency": "GBP",
            "fx_rate": "1",
            "treaty": None,
        },
    ],
    "interest": [
        {
            "date": "2024-09-30",
            "broker": "Freetrade",
            "currency": "GBP",
            "uk": True,
            "amount_gbp": "5.28",
        },
        {
            "date": "2024-09-30",
            "broker": "Charles Schwab",
            "currency": "USD",
            "uk": False,
            "amount_gbp": "9.37",
        },
    ],
    "other_income": [],
    "eri_distributions": [],
    "interest_by_source": [
        {"broker": "Charles Schwab", "currency": "USD", "amount_gbp": "9.37"},
        {"broker": "Freetrade", "currency": "GBP", "amount_gbp": "5.28"},
    ],
    "acquisitions": [],
    "portfolio_eoy": [],
    "warnings": [],
}


@pytest.fixture
def profile():
    return build_profile(INPUTS, Y, report_view.summary_for_planner(BUNDLE))


# ── Capital gains ─────────────────────────────────────────────────────────────


def test_cgt_is_split_at_30_october(profile):
    tx = profile["tax"]
    assert tx["sa_cgt_at_pre_oct_rates"] == pytest.approx(1112.60, abs=0.01)
    assert tx["cgt_adjustment"] == pytest.approx(122, abs=1)
    assert tx["cgt_total"] == pytest.approx(1234.36, abs=1)
    assert tx["cgt_total"] != pytest.approx(1335.24, abs=1)
    assert tx["cgt_estimate"] == tx["cgt_total"]


# ── Interest ──────────────────────────────────────────────────────────────────


def test_cash_interest_taxed_at_45_percent():
    """£5.28 UK + £9.37 foreign cash interest, no savings allowance: £6.59."""
    p = build_profile(INPUTS, Y, {"uk_interest": 5.28, "foreign_interest": 9.37})
    assert p["allowances"]["psa"] == 0
    assert p["tax"]["savings_tax"] == pytest.approx(6.59, abs=0.005)


def test_bond_fund_distributions_join_the_savings_income(profile):
    assert profile["allowances"]["psa"] == 0
    assert profile["income"]["savings"] == pytest.approx(5.28 + 9.37 + 407.79)


# ── Distribution classification ───────────────────────────────────────────────


def test_reits_and_bond_funds_leave_the_dividend_figure(profile):
    # Only META (£183.10) survives as a dividend; LAND/PHP are property income
    # and VGOV/VUSC/ERNS are interest.
    assert profile["income"]["dividends"] == pytest.approx(183.10)
    assert profile["income"]["other_income"] == pytest.approx(230.64)
    assert profile["income"]["savings"] == pytest.approx(5.28 + 9.37 + 407.79)


def test_previous_total_dividends_figure_is_gone(profile):
    assert profile["income"]["dividends"] != pytest.approx(821.53)


def test_itemised_table_is_available_for_hand_checking():
    view = report_view.build_view(BUNDLE, 2024, None)
    rows = view["distributions"]
    assert len(rows) == 8  # 6 dividend rows + 2 interest rows
    kinds = {r["symbol"]: r["kind"] for r in rows if r.get("symbol")}
    assert kinds["LAND"] == "property_income_distribution"
    assert kinds["PHP"] == "property_income_distribution"
    assert kinds["VGOV"] == "interest_distribution"
    assert kinds["VUSC"] == "interest_distribution"
    assert kinds["ERNS"] == "interest_distribution"
    assert kinds["META"] == "foreign_dividend"
    for r in rows:
        assert r["why"]
        assert "fx_rate" in r


# ── Foreign tax credit relief ─────────────────────────────────────────────────


def test_ftcr_reduces_tax_not_the_taxable_amount(profile):
    tx = profile["tax"]
    # £183.10 of foreign dividends, the £500 allowance spent on... nothing else
    # here, so check the mechanism on a profile where it is fully used.
    assert tx["ftcr"] >= 0
    assert tx["dividend_tax"] == pytest.approx(tx["dividend_tax_before_ftcr"] - tx["ftcr"])


def test_ftcr_when_the_dividend_allowance_is_already_spent():
    invest = {
        "dividends_total": 683.10,
        "uk_dividends": 500.00,
        "foreign_dividends": 183.10,
        "foreign_dividend_tax": 27.47,
        "foreign_dividend_treaty_rate": 0.15,
    }
    p = build_profile(INPUTS, Y, invest)
    tx = p["tax"]
    # The allowance goes to the UK dividends, so all £183.10 is taxed at 39.35%.
    assert tx["uk_tax_on_foreign_dividends"] == pytest.approx(72.05, abs=0.01)
    assert tx["ftcr"] == pytest.approx(27.47, abs=0.01)
    assert tx["dividend_tax_before_ftcr"] == pytest.approx(183.10 * 0.3935, abs=0.01)
    assert tx["dividend_tax"] == pytest.approx(183.10 * 0.3935 - 27.47, abs=0.01)


def test_taxable_dividend_base_is_not_reduced_by_treaty_relief():
    view = report_view.build_view(BUNDLE, 2024, None)
    card = view["cards"]["dividends_taxable"]
    assert "treaty relief" not in (card["sub"] or "")


# ── Payments on account ───────────────────────────────────────────────────────


def test_payments_on_account_exclude_cgt(profile):
    poa = profile["payments_on_account"]
    assert poa["required"] is False
    assert poa["each_instalment"] == pytest.approx(0)
    # The headline bill, CGT included, is over £1,000 — and must not trigger it.
    assert profile["tax"]["total_sa"] > 1000
    assert poa["liability_excluding_cgt"] < 1000


def test_payments_on_account_show_both_conditions(profile):
    poa = profile["payments_on_account"]
    assert poa["over_threshold"] is False
    assert poa["under_80_percent_at_source"] is False
    assert poa["explain"]


# ── The UI note about box 51 ──────────────────────────────────────────────────


def test_report_view_explains_the_box_51_adjustment():
    view = report_view.build_view(BUNDLE, 2024, None)
    split = view["rate_change_split"]
    assert split["before"] == pytest.approx(2524.95)
    assert split["after"] == pytest.approx(6038.57)
    assert split["needs_box_51_adjustment"] is True
    assert split["cgt_adjustment"] == pytest.approx(122, abs=1)
    assert "51" in split["note"]


def test_no_box_51_note_when_no_disposal_precedes_the_change():
    bundle = {
        **BUNDLE,
        "disposals": [d for d in BUNDLE["disposals"] if d["date"] >= "2024-10-30"],
    }
    view = report_view.build_view(bundle, 2024, None)
    assert view["rate_change_split"]["has_pre_change_disposals"] is False
