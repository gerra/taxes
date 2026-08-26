"""detect_withholding_refunds pairs a short-paid sale with the broker's later
refund adjustment (real cgt_calc model objects, no network)."""

from datetime import date
from decimal import Decimal

from cgt_calc.model import ActionType, BrokerTransaction

from engine.worker import detect_withholding_refunds


def _tx(day, action, symbol, qty=None, price=None, fees=Decimal(0), amount=None):
    return BrokerTransaction(
        date=date.fromisoformat(day),
        action=action,
        symbol=symbol,
        description="",
        quantity=Decimal(qty) if qty is not None else None,
        price=Decimal(price) if price is not None else None,
        fees=fees,
        amount=Decimal(amount) if amount is not None else None,
        currency="USD",
        broker="Charles Schwab",
    )


def test_pairs_sale_with_refund_adjustment():
    txs = [
        _tx("2025-02-25", ActionType.SELL, "META", "70", "652.795", Decimal("1.28"), "34727.41"),
        _tx("2025-03-04", ActionType.ADJUSTMENT, "META", amount="10966.96"),
        _tx("2025-03-06", ActionType.ADJUSTMENT, None, amount="0.01"),
    ]
    [r] = detect_withholding_refunds(txs)
    assert r["symbol"] == "META"
    assert r["sale_date"] == "2025-02-25"
    assert r["refund_date"] == "2025-03-04"
    assert Decimal(r["amount"]) == Decimal("10966.96")
    assert r["days"] == 7


def test_no_pairing_when_amount_or_window_differ():
    sale = _tx("2025-02-25", ActionType.SELL, "META", "70", "652.795", Decimal("1.28"), "34727.41")
    assert (
        detect_withholding_refunds(
            [sale, _tx("2025-03-04", ActionType.ADJUSTMENT, "META", amount="100")]
        )
        == []
    )
    assert (
        detect_withholding_refunds(
            [sale, _tx("2025-06-01", ActionType.ADJUSTMENT, "META", amount="10966.96")]
        )
        == []
    )
    assert (
        detect_withholding_refunds(
            [sale, _tx("2025-03-04", ActionType.ADJUSTMENT, "AAPL", amount="10966.96")]
        )
        == []
    )


def test_full_price_sale_is_ignored():
    sale = _tx("2025-02-25", ActionType.SELL, "META", "10", "100", Decimal("1"), "999")
    assert (
        detect_withholding_refunds(
            [sale, _tx("2025-03-01", ActionType.ADJUSTMENT, "META", amount="1")]
        )
        == []
    )
