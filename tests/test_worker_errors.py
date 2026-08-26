"""describe_error turns engine exceptions into the structured error the UI
renders; an InvalidTransactionError carries its row as fields rather than as a
Python repr glued to the message."""

from datetime import date
from decimal import Decimal

from cgt_calc.exceptions import CgtError, InvalidTransactionError, QuantityMissingError
from cgt_calc.model import ActionType, BrokerTransaction

from engine.worker import describe_error

TX = BrokerTransaction(
    date=date(2023, 5, 17),
    action=ActionType.BUY,
    symbol="IE00B3VWLG82",
    description="MSCI UK Small Cap ActionType.BUY",
    quantity=Decimal("1.00000000"),
    price=Decimal(0),
    fees=Decimal(0),
    amount=Decimal("-0"),
    currency="GBP",
    broker="Freetrade",
    isin="IE00B3VWLG82",
)


def test_invalid_transaction_error_is_structured():
    err = InvalidTransactionError(
        TX, "Ticker IE00B3VWLG82 does not match existing mapping: ISIN is linked to CUKS"
    )
    out = describe_error(err)
    assert out["type"] == "InvalidTransactionError"
    assert out["message"] == (
        "Ticker IE00B3VWLG82 does not match existing mapping: ISIN is linked to CUKS"
    )
    assert "FreetradeTransaction(" not in out["message"]
    assert "BrokerTransaction(" not in out["message"]
    assert out["transaction"] == {
        "date": "2023-05-17",
        "action": "BUY",
        "symbol": "IE00B3VWLG82",
        "isin": "IE00B3VWLG82",
        "description": "MSCI UK Small Cap ActionType.BUY",
        "quantity": "1.00000000",
        "price": "0",
        "fees": "0",
        "amount": "-0",
        "currency": "GBP",
        "broker": "Freetrade",
    }


def test_subclasses_keep_their_own_type_name():
    out = describe_error(QuantityMissingError(TX))
    assert out["type"] == "QuantityMissingError"
    assert out["message"] == "Quantity missing"
    assert out["transaction"]["symbol"] == "IE00B3VWLG82"


def test_plain_cgt_error_keeps_full_message():
    out = describe_error(CgtError("Something\nmulti-line"))
    assert out == {"type": "CgtError", "message": "Something\nmulti-line"}
