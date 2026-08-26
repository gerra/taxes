from core.notices import build_notices

DISCREPANCY = (
    "Amount discrepancy for SchwabTransaction(date=datetime.date(2025, 2, 25), "
    "action=<ActionType.SELL: 2>, symbol='META', description='META PLATFORMS INC CLASS A', "
    "quantity=Decimal('70'), price=Decimal('652.795'), fees=Decimal('1.28'), "
    "amount=Decimal('34727.41'), currency='USD', broker='Charles Schwab', isin=None): "
    "supplied=34727.41, calculated=45694.370. Using calculated amount for CGT purposes."
)
BNB_1 = "Bed and breakfasting for META. Disposed on 2023-05-10 and acquired again on 2023-05-16"
BNB_2 = "Bed and breakfasting for META. Disposed on 2024-02-09 and acquired again on 2024-02-16"
TREATY_1 = (
    "Determined double taxation treaty does not match the base taxation rules "
    "(expected -5.33 base tax for USA but -10.65 was deducted) for META ticker!"
)
TREATY_2 = (
    "Determined double taxation treaty does not match the base taxation rules "
    "(expected -6.15 base tax for USA but -12.30 was deducted) for META ticker!"
)


def test_discrepancy_is_human():
    [n] = build_notices([DISCREPANCY])
    assert n["kind"] == "warning"
    assert n["category"] == "amount_adjusted"
    assert "[[25 Feb 2025]]" in n["title"]
    assert "[[$34,727.41]]" in n["summary"]
    assert "[[70]]" in n["summary"]
    assert "[[$652.795]]" in n["summary"]
    assert "[[$45,694.37]]" in n["summary"]
    assert "SchwabTransaction" not in n["title"] + n["summary"]
    assert n["raw"] == [DISCREPANCY]


def test_bnb_grouped_and_informational():
    [n] = build_notices([BNB_1, BNB_2])
    assert n["kind"] == "info"
    assert n["count"] == 2
    assert n["occurrences"][0] == "Sold [[10 May 2023]], bought again [[16 May 2023]]"
    assert "[[META]]" in n["title"]


def test_treaty_grouped_with_rate_and_overpayment():
    [n] = build_notices([TREATY_1, TREATY_2])
    assert n["kind"] == "warning"
    assert n["count"] == 2
    assert "[[30%]]" in n["summary"]
    assert "[[15%]]" in n["summary"]
    # (10.65-5.33) + (12.30-6.15) = 11.47
    assert "[[$11.47]]" in n["summary"]
    assert "W-8BEN" in n["action"]
    assert "_expected" not in n


def test_unknown_message_preserved():
    [n] = build_notices(["Something odd happened"])
    assert n["kind"] == "warning"
    assert n["summary"] == "Something odd happened"


def test_sorted_warnings_before_info():
    notices = build_notices([BNB_1, DISCREPANCY, TREATY_1])
    assert [n["kind"] for n in notices] == ["warning", "warning", "info"]
