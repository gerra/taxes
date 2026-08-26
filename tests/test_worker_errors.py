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


BALANCE_MESSAGE = (
    "Reached a negative balance(-2532.71) for broker Freetrade (GBP) after processing "
    "the following transactions:\n"
    "... 1 earlier transaction(s) omitted ...\n"
    "FreetradeTransaction(date=datetime.date(2023, 9, 14), action=<ActionType.TRANSFER: 3>, "
    "symbol=None, description='Top up ActionType.TRANSFER', quantity=None, price=None, "
    "fees=Decimal('0'), amount=Decimal('1000.00'), currency='GBP', broker='Freetrade', "
    "isin=None, foreign_fees={}, ambiguous_quantity=None)\n"
    "Balance after transaction=1000.00\n"
    "FreetradeTransaction(date=datetime.date(2024, 6, 14), action=<ActionType.BUY: 1>, "
    "symbol='GB00BP243M73', description='UK T-Bill 15/07/24 ActionType.BUY', "
    "quantity=Decimal('3047.95000000'), price=Decimal('0.99602511'), fees=Decimal('0.00'), "
    "amount=Decimal('-3035.83'), currency='GBP', broker='Freetrade', isin='GB00BP243M73', "
    "foreign_fees={}, ambiguous_quantity=None)\n"
    "Balance after transaction=-2532.71\n"
    "Tip: If your input file is missing deposits/withdrawals use --no-balance-check."
)


def test_negative_balance_becomes_a_headline_plus_ledger_rows():
    from cgt_calc.exceptions import CalculationError

    out = describe_error(CalculationError(BALANCE_MESSAGE))
    assert out["type"] == "negative_balance"
    assert out["broker"] == "Freetrade"
    assert out["currency"] == "GBP"
    assert out["balance"] == "-2532.71"
    # The headline is one readable sentence, not the ledger or the CLI tip.
    assert "FreetradeTransaction(" not in out["message"]
    assert "--no-balance-check" not in out["message"]
    assert len(out["message"]) < 200
    assert out["ledger"] == [
        {"note": "1 earlier transaction(s) omitted"},
        {
            "date": "2023-09-14",
            "action": "TRANSFER",
            "symbol": None,
            "description": "Top up",
            "amount": "1000.00",
            "balance": "1000.00",
        },
        {
            "date": "2024-06-14",
            "action": "BUY",
            "symbol": "GB00BP243M73",
            "description": "UK T-Bill 15/07/24",
            "amount": "-3035.83",
            "balance": "-2532.71",
        },
    ]


def test_other_calculation_errors_are_untouched():
    from cgt_calc.exceptions import CalculationError

    out = describe_error(CalculationError("Ambiguous quantity"))
    assert out == {"type": "CalculationError", "message": "Ambiguous quantity"}
