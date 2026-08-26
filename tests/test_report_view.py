from core.report_view import build_view, summary_for_planner

BUNDLE = {
    "totals": {
        "disposal_count": 3,
        "disposal_proceeds": "48210.55",
        "allowable_costs": "40000.00",
        "capital_gain_before_losses": "9000.00",
        "capital_loss": "-789.45",
        "total_gain": "8210.55",
        "capital_gain_allowance": "3000",
        "taxable_gain": "5210.55",
        "dividends_total": "1200.00",
        "dividend_treaty_relief": "180.00",
        "dividend_allowance": "500",
        "dividends_taxable": "520.00",
        "uk_interest": "42.00",
        "foreign_interest": "310.00",
        "eri_dividends": "0",
        "eri_interest": "0",
    },
    "disposals": [
        {"date": "2024-06-01", "symbol": "A", "gain": "4000.00", "entries": [], "amount": "0"},
        {"date": "2024-12-01", "symbol": "B", "gain": "4210.55", "entries": [], "amount": "0"},
    ],
    "dividends": [],
    "interest": [],
    "portfolio_eoy": [],
    "warnings": ["something to know"],
}


def test_sa_boxes_and_cards():
    view = build_view(BUNDLE, 2024, None)
    boxes = {(b["form"], b["box"]): b for b in view["sa_boxes"]}
    assert boxes[("SA108", "23")]["value"] == 3
    assert boxes[("SA108", "24")]["value"] == 48210.55
    assert boxes[("SA108", "27")]["value"] == 789.45  # losses shown positive
    assert view["cards"]["taxable_gain"]["value"] == 5210.55
    assert "something to know" in view["warnings"]
    for box in view["sa_boxes"]:
        assert box["explain"]  # every figure must carry an explanation


def test_2024_rate_change_split():
    view = build_view(BUNDLE, 2024, None)
    split = view["rate_change_split"]
    assert split["before"] == 4000.00
    assert split["after"] == 4210.55


def test_no_split_for_2025():
    assert build_view(BUNDLE, 2025, None)["rate_change_split"] is None


def test_summary_for_planner():
    s = summary_for_planner(BUNDLE)
    assert s["taxable_gain"] == 5210.55
    assert s["uk_interest"] == 42.0
