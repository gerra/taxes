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


INCOME_BUNDLE = {
    **BUNDLE,
    "totals": {
        **BUNDLE["totals"],
        "other_income": "80.76",
        "other_income_tax": "16.13",
        "exempt_disposal_count": 1,
        "exempt_disposal_proceeds": "95.20",
    },
    "disposals": [
        *BUNDLE["disposals"],
        {
            "date": "2024-08-25",
            "symbol": "TN28",
            "gain": "1.00",
            "entries": [],
            "amount": "95.20",
            "exempt": True,
        },
    ],
    "other_income": [
        {"date": "2024-05-08", "source": "PHP", "amount_gbp": "80.64", "tax_gbp": "16.13"},
        {"date": "2024-08-17", "source": "Freetrade", "amount_gbp": "0.12", "tax_gbp": "0"},
    ],
    "interest": [
        {
            "date": "2024-05-16",
            "broker": "Freetrade",
            "currency": "GBP",
            "uk": True,
            "amount_gbp": "2",
        }
    ],
}


def test_other_income_boxes_and_card():
    view = build_view(INCOME_BUNDLE, 2024, None)
    boxes = {(b["form"], b["box"]): b for b in view["sa_boxes"]}
    box17 = boxes[("SA100 TR3", "17")]
    assert box17["value"] == 80.76
    assert "£80.64 of property income distributions from UK REITs (PHP)" in box17["explain"]
    assert "£0.12 of share-lending fees" in box17["explain"]
    assert boxes[("SA100 TR3", "19")]["value"] == 16.13
    assert view["cards"]["other_income"] == {
        "value": 80.76,
        "tax_taken_off": 16.13,
        "estimated_tax": None,
    }
    for box in view["sa_boxes"]:
        assert box["explain"]


def test_no_other_income_boxes_when_none():
    view = build_view(BUNDLE, 2024, None)
    assert not [b for b in view["sa_boxes"] if b["box"] in ("17", "19")]
    assert view["exempt_disposals"] is None


def test_exempt_disposals_summarised_and_kept_out_of_the_split():
    view = build_view(INCOME_BUNDLE, 2024, None)
    ex = view["exempt_disposals"]
    assert ex["count"] == 1
    assert ex["tbill_count"] == 0
    assert ex["proceeds"] == 95.2
    assert ex["gain"] == 1.0
    assert ex["symbols"] == ["TN28"]
    assert "TCGA 1992 s115" in ex["explain"]
    # The 2024/25 rate-change split ignores the exempt disposal.
    assert view["rate_change_split"]["after"] == 4210.55


def test_summary_for_planner_carries_other_income():
    s = summary_for_planner(INCOME_BUNDLE)
    assert s["other_income"] == 80.76
    assert s["other_income_tax"] == 16.13
    assert summary_for_planner(BUNDLE)["other_income"] == 0.0


def test_dividends_split_by_isin_country_and_tbill_row():
    bundle = {
        **INCOME_BUNDLE,
        "dividends": [
            {
                "date": "2024-06-26",
                "symbol": "META",
                "country": "US",
                "amount_gbp": "700.00",
                "tax_at_source_gbp": "0",
                "is_interest": False,
                "treaty": None,
            },
            {
                "date": "2025-01-08",
                "symbol": "LAND",
                "country": "GB",
                "amount_gbp": "300.00",
                "tax_at_source_gbp": "0",
                "is_interest": False,
                "treaty": None,
            },
            {
                "date": "2025-01-09",
                "symbol": "VGOV",
                "country": "IE",
                "amount_gbp": "100.00",
                "tax_at_source_gbp": "0",
                "is_interest": False,
                "treaty": None,
            },
        ],
        "exempt": {
            "securities": [],
            "ais_applies": False,
            "tbills": [
                {
                    "symbol": "A",
                    "title": "UK T-Bill 15/07/24",
                    "nominal": "3047.95",
                    "cost": "3035.83",
                    "profit": "12.12",
                    "status": "matured",
                    "event_date": "2024-07-15",
                    "in_year": True,
                },
                {
                    "symbol": "B",
                    "title": "UK T-Bill 20/05/25",
                    "nominal": "1000",
                    "cost": "990",
                    "profit": "10",
                    "status": "open",
                    "event_date": "2025-05-20",
                    "in_year": False,
                },
            ],
        },
    }
    view = build_view(bundle, 2024, None)
    boxes = {(b["form"], b["box"]): b for b in view["sa_boxes"]}
    # LAND paid gross, so it stays an ordinary dividend (a REIT PID always has
    # 20% deducted); VGOV is a bond fund, so its distribution is interest.
    assert boxes[("SA100 TR3", "4")]["value"] == 300.0
    assert "LAND" in boxes[("SA100 TR3", "4")]["explain"]
    assert boxes[("SA106", "dividends")]["value"] == 700.0
    assert "META" in boxes[("SA106", "dividends")]["explain"]
    assert boxes[("SA106", "interest")]["value"] == 100.0
    assert "VGOV" in boxes[("SA106", "interest")]["explain"]
    assert "VGOV" not in boxes[("SA106", "dividends")]["explain"]
    assert boxes[("SA101 Ai1", "3")]["value"] == 12.12
    assert "1 UK Treasury bill matured" in boxes[("SA101 Ai1", "3")]["explain"]
    keys = {n["key"] for n in view["notices"]}
    assert "tbill_returns" in keys


def test_tbill_redemptions_kept_apart_from_gilt_gains():
    bundle = {
        **INCOME_BUNDLE,
        "disposals": [
            *INCOME_BUNDLE["disposals"],
            {
                "date": "2024-07-15",
                "symbol": "GB00BP243M73",
                "gain": "12.12",
                "entries": [],
                "amount": "3047.95",
                "exempt": True,
            },
        ],
        "exempt": {
            "securities": [
                {
                    "symbol": "GB00BP243M73",
                    "isin": "GB00BP243M73",
                    "kind": "tbill",
                    "title": "UK T-Bill 15/07/24",
                    "source": "detected",
                },
                {
                    "symbol": "TN28",
                    "isin": "GB00BMBL1G81",
                    "kind": "gilt",
                    "title": "1/8% Gilt 2028",
                    "source": "detected",
                },
            ],
            "ais_applies": False,
            "tbills": [],
        },
    }
    ex = build_view(bundle, 2024, None)["exempt_disposals"]
    assert ex["count"] == 1 and ex["tbill_count"] == 1
    assert ex["gain"] == 1.0  # the T-bill's 12.12 is income, not a notional gain
    assert ex["symbols"] == ["TN28"]
    assert "1 UK T-bill redemption whose discount is income" in ex["explain"]
