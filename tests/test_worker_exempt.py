"""Gilt/T-bill recognition and the Accrued Income Scheme facts the worker adds
to the bundle (real cgt_calc model objects, no network)."""

from datetime import date
from decimal import Decimal

from cgt_calc.model import ActionType, BrokerTransaction, Isin

from engine.worker import detect_exempt_securities, exempt_summary, peak_nominal_held


def _tx(day, action, symbol, title, isin, qty="100"):
    return BrokerTransaction(
        date=date.fromisoformat(day),
        action=action,
        symbol=symbol,
        description=f"{title} {action}",
        quantity=Decimal(qty),
        price=Decimal("0.95"),
        fees=Decimal(0),
        amount=Decimal("95"),
        currency="GBP",
        broker="Freetrade",
        isin=Isin(isin) if isin else None,
    )


GILT = _tx("2026-06-15", ActionType.BUY, "TN28", "1/8% Gilt 2028", "GB00BMBL1G81", "17005.77")
TBILL = _tx("2024-06-14", ActionType.BUY, "GB00BP243M73", "UK T-Bill 15/07/24", "GB00BP243M73")
ETF = _tx("2024-06-14", ActionType.BUY, "VGOV", "UK Gilt UCITS ETF", "IE00B42WWV65")
FUND = _tx("2024-06-14", ActionType.BUY, "LGGI", "All Stocks Gilt Index Trust", "GB00B8344798")
SHARE = _tx("2024-06-14", ActionType.BUY, "LAND", "Landsec", "GB00BYW0PQ60")


def test_detects_gilts_and_tbills_by_name_and_gb_isin():
    found = detect_exempt_securities([GILT, TBILL, ETF, FUND, SHARE])
    assert [(f["symbol"], f["kind"]) for f in found] == [
        ("GB00BP243M73", "tbill"),
        ("TN28", "gilt"),
    ]
    assert found[1]["title"] == "1/8% Gilt 2028"
    assert found[1]["isin"] == "GB00BMBL1G81"


def test_fancy_coupon_names_are_gilts():
    for title in ("4¼% Treasury Gilt 2032", "0.125% Treasury Gilt 2028", "3½% Treasury Stock 2045"):
        tx = _tx("2026-01-01", ActionType.BUY, "TG32", title, "GB00B3KJDS62")
        assert detect_exempt_securities([tx])[0]["kind"] == "gilt", title


def test_peak_nominal_counts_positions_carried_into_the_year():
    txs = [
        _tx("2025-03-01", ActionType.BUY, "TN28", "1/8% Gilt 2028", "GB00BMBL1G81", "4000"),
        _tx("2026-06-15", ActionType.BUY, "TN28", "1/8% Gilt 2028", "GB00BMBL1G81", "3000"),
        _tx("2026-08-25", ActionType.SELL, "TN28", "1/8% Gilt 2028", "GB00BMBL1G81", "7000"),
    ]
    assert peak_nominal_held(txs, {"TN28"}, 2026) == Decimal(7000)
    assert peak_nominal_held(txs, {"TN28"}, 2025) == Decimal(4000)
    assert peak_nominal_held(txs, {"TN28"}, 2027) == Decimal(0)


def test_exempt_summary_merges_configured_names_and_parses_accrued_interest():
    job = {"tax_year": 2026, "exempt_securities": ["gb00bp243m73", "TR30"]}
    warning = (
        "Accrued interest of 8.04 GBP in the purchase of exempt security TN28 on "
        "2026-06-15: supplied=-16000.00, calculated=-15991.96. Not part of the capital "
        "gains computation; the Accrued Income Scheme may apply."
    )
    names, summary = exempt_summary(job, [GILT, TBILL, SHARE], [warning, "something else"])
    assert names == ["GB00BP243M73", "TN28", "TR30"]
    sources = {s["symbol"]: s["source"] for s in summary["securities"]}
    assert sources == {"TN28": "detected", "GB00BP243M73": "detected", "TR30": "configured"}
    assert summary["ais_applies"] is True
    assert summary["ais_nominal_peak"] == "17005.77"
    assert summary["accrued_interest"] == [
        {
            "symbol": "TN28",
            "date": "2026-06-15",
            "side": "purchase",
            "amount": "8.04",
            "currency": "GBP",
        }
    ]


def test_small_gilt_holding_does_not_trigger_ais():
    small = _tx("2026-06-15", ActionType.BUY, "TN28", "1/8% Gilt 2028", "GB00BMBL1G81", "4000")
    _, summary = exempt_summary({"tax_year": 2026}, [small], [])
    assert summary["ais_applies"] is False
    assert summary["ais_nominal_peak"] == "4000"


def _buy(day, symbol, title, qty, price, isin=None):
    t = _tx(day, ActionType.BUY, symbol, title, isin or symbol, qty)
    t.price = Decimal(price)
    t.amount = -(Decimal(qty) * Decimal(price)).quantize(Decimal("0.01"))
    return t


def test_tbill_returns_reconstruct_redemption_at_par():
    from engine.worker import tbill_returns

    bills = [
        {"symbol": "GB00BP243M73", "title": "UK T-Bill 15/07/24", "kind": "tbill"},
        {"symbol": "GB00BSGNLX88", "title": "UK T-Bill 10/03/25", "kind": "tbill"},
        {"symbol": "GB00BSGHT927", "title": "UK T-Bill 20/05/25", "kind": "tbill"},
    ]
    txs = [
        _buy("2024-06-14", "GB00BP243M73", "UK T-Bill 15/07/24", "3047.95", "0.99602511"),
        _buy("2025-02-10", "GB00BSGNLX88", "UK T-Bill 10/03/25", "1000", "0.996"),
        _tx("2025-03-01", ActionType.SELL, "GB00BSGNLX88", "UK T-Bill 10/03/25", None, "1000"),
        _buy("2025-04-20", "GB00BSGHT927", "UK T-Bill 20/05/25", "1000", "0.99"),
    ]
    txs[2].amount = Decimal("998")
    by = {t["symbol"]: t for t in tbill_returns(txs, bills, 2024)}
    matured = by["GB00BP243M73"]
    assert matured["status"] == "matured"
    assert matured["maturity"] == "2024-07-15"
    assert Decimal(matured["cost"]) == Decimal("3035.83")
    assert Decimal(matured["profit"]) == Decimal("12.12")
    assert matured["in_year"] is True
    sold = by["GB00BSGNLX88"]
    assert sold["status"] == "sold"
    assert Decimal(sold["profit"]) == Decimal("2.00")
    assert sold["event_date"] == "2025-03-01" and sold["in_year"] is True
    # Matures in 2025/26: reported, but not this year's income.
    assert by["GB00BSGHT927"]["in_year"] is False


def test_offshore_funds_without_eri_flags_irish_etfs_held_in_year():
    from engine.worker import held_in_year, offshore_funds_without_eri

    txs = [
        _tx("2024-01-10", ActionType.BUY, "VUSC", "S&P 500 UCITS ETF", "IE00BFMXXD54"),
        _tx("2024-06-10", ActionType.BUY, "VGOV", "UK Gilt UCITS ETF", "IE00B42WWV65"),
        _tx("2024-06-20", ActionType.SELL, "VGOV", "UK Gilt UCITS ETF", "IE00B42WWV65"),
        _tx("2023-01-10", ActionType.BUY, "OLD", "Old Fund", "IE00B0000000"),
        _tx("2023-02-10", ActionType.SELL, "OLD", "Old Fund", "IE00B0000000"),
        _tx("2024-06-14", ActionType.BUY, "LAND", "Landsec", "GB00BYW0PQ60"),
    ]
    assert held_in_year(txs, 2024) == {"VUSC", "VGOV", "LAND"}
    isins = {t.symbol: t.isin for t in txs}
    out = offshore_funds_without_eri(txs, isins, {"VUSC"}, 2024)
    assert out == [{"symbol": "VGOV", "isin": "IE00B42WWV65"}]
