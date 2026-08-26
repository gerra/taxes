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


def test_keys_are_stable_and_url_safe():
    import re

    for n in build_notices(
        [DISCREPANCY, BNB_1, TREATY_1, "Cash balance didn't reconcile — x", "odd"]
    ):
        assert re.match(r"^[A-Za-z0-9_.\-]+$", n["key"]), n["key"]
    [n] = build_notices([DISCREPANCY])
    assert n["key"] == "amount_adjusted__META__2025-02-25"


def test_resolution_verifies_sell_to_cover_arithmetic():
    from core.notices import apply_resolutions

    notices = build_notices([DISCREPANCY, BNB_1])
    resolutions = {
        "amount_adjusted__META__2025-02-25": {
            "note": "backup withholding",
            "data": {"principal": "45695.65", "withholding": "10966.96", "reason": "backup"},
            "evidence_name": "trade.pdf",
            "created_at": "2026-08-26 10:00:00",
        }
    }
    apply_resolutions(notices, resolutions)
    # fully verified notices sort last
    assert notices[-1]["category"] == "amount_adjusted"
    res = notices[-1]["resolution"]
    assert res["status"] == "verified"
    assert res["verified"] is True
    labels = {c["label"]: c["status"] for c in res["checks"]}
    assert labels["Principal matches quantity × price"] == "ok"
    assert labels["Withholding explains the missing amount"] == "ok"
    assert labels["Tax treatment"] == "info"
    assert "$45,694.37 (after $1.28 fees) − $10,966.96 = $34,727.41" in res["check"]
    assert notices[0]["resolution"] is None
    assert notices[0]["verification"]["fields"] == []  # info notice: nothing to verify


def test_resolution_flags_mismatch():
    from core.notices import apply_resolutions

    notices = build_notices([DISCREPANCY])
    apply_resolutions(
        notices,
        {
            "amount_adjusted__META__2025-02-25": {
                "note": "",
                "data": {"withholding": "100"},
                "evidence_name": None,
                "created_at": "",
            }
        },
    )
    res = notices[0]["resolution"]
    assert res["status"] == "mismatch"
    assert res["verified"] is False
    assert "off by" in res["check"]
    assert "Principal" in " ".join(res["missing"])


def test_partial_resolution_stays_open():
    from core.notices import apply_resolutions

    notices = build_notices([TREATY_1])
    apply_resolutions(
        notices,
        {
            "withholding__META": {
                "note": "looking",
                "data": {},
                "evidence_name": None,
                "created_at": "",
            }
        },
    )
    assert notices[0]["resolution"]["status"] == "partial"
    assert notices[0]["resolution"]["checks"][0]["status"] == "pending"


def test_discrepancy_detects_backup_withholding():
    [n] = build_notices([DISCREPANCY])
    # 45,694.37 - 34,727.41 = 10,966.96 = 24.0% of proceeds
    assert "[[$10,966.96]]" in n["summary"]
    assert "[[24%]]" in n["summary"]
    assert "tax withheld" in n["title"]
    assert "W-8BEN" in n["why"]
    assert "sell-to-cover" not in n["why"]


def test_refund_turns_discrepancy_into_info():
    refunds = [
        {
            "symbol": "META",
            "sale_date": "2025-02-25",
            "refund_date": "2025-03-04",
            "amount": "10966.96",
            "currency": "USD",
            "days": 7,
        }
    ]
    [n] = build_notices([DISCREPANCY], refunds)
    assert n["kind"] == "info"
    assert "then refunded" in n["title"]
    assert "[[$10,966.96]]" in n["summary"] and "[[4 Mar 2025]]" in n["summary"]
    assert "nothing to reclaim" in n["summary"]
    assert n["action"] is None
    assert "1040-NR" not in n["why"]
    # a refund for a different sale doesn't match
    [n2] = build_notices([DISCREPANCY], [{**refunds[0], "sale_date": "2025-01-01"}])
    assert n2["kind"] == "warning"


def test_dated_notices_carry_their_tax_year():
    [n] = build_notices([DISCREPANCY])
    assert n["tax_year"] == 2024  # 25 Feb 2025 is in 2024/25
    [t] = build_notices([TREATY_1])
    assert t["tax_year"] is None  # engine already limits treaty checks to the reported year
    [o] = build_notices(["Something odd happened"])
    assert o["tax_year"] is None
    [a] = build_notices(["No tax constants for 2021/22 — allowances/rates missing"])
    assert a["tax_year"] is None


def test_generic_engine_message_dated_from_its_text():
    [n] = build_notices(
        ["Dividend tax of 5.00 USD for META on 2024-03-01 has no dividend in the 30 days before it"]
    )
    assert n["tax_year"] == 2023
    [n] = build_notices(["Skipping duplicated ERI transaction: X(date=datetime.date(2024, 4, 6))"])
    assert n["tax_year"] == 2024


def test_bnb_grouped_per_tax_year():
    bnb_3 = "Bed and breakfasting for META. Disposed on 2024-06-03 and acquired again on 2024-06-10"
    by_key = {n["key"]: n for n in build_notices([BNB_1, BNB_2, bnb_3])}
    assert set(by_key) == {"bed_and_breakfast__META__2023", "bed_and_breakfast__META__2024"}
    assert by_key["bed_and_breakfast__META__2023"]["count"] == 2
    assert by_key["bed_and_breakfast__META__2024"]["tax_year"] == 2024


EXEMPT = {
    "securities": [
        {
            "symbol": "TN28",
            "isin": "GB00BMBL1G81",
            "kind": "gilt",
            "title": "1/8% Gilt 2028",
            "source": "detected",
        },
        {
            "symbol": "GB00BP243M73",
            "isin": "GB00BP243M73",
            "kind": "tbill",
            "title": "UK T-Bill 15/07/24",
            "source": "detected",
        },
    ],
    "ais_nominal_peak": "17005.77",
    "ais_limit": "5000",
    "ais_applies": True,
    "accrued_interest": [
        {
            "symbol": "TN28",
            "date": "2026-06-15",
            "side": "purchase",
            "amount": "8.04",
            "currency": "GBP",
        },
        {
            "symbol": "TN28",
            "date": "2026-08-25",
            "side": "sale",
            "amount": "1.53",
            "currency": "GBP",
        },
        {
            "symbol": "TN28",
            "date": "2025-08-25",
            "side": "sale",
            "amount": "0.40",
            "currency": "GBP",
        },
    ],
}


def test_exempt_and_accrued_income_notices():
    notices = build_notices([], None, EXEMPT, 2026)
    by_key = {n["key"]: n for n in notices}
    exempt = by_key["exempt_securities"]
    assert exempt["kind"] == "info"
    assert exempt["tax_year"] is None
    assert "[[TN28]] — 1/8% Gilt 2028 (GB00BMBL1G81) — recognised by name" in exempt["occurrences"]
    assert "T-bill" in exempt["action"]
    ais = by_key["accrued_income_scheme"]
    assert ais["kind"] == "warning"
    assert ais["tax_year"] == 2026
    assert "[[£17,005.77]]" in ais["summary"]
    # Only this year's trades are listed; the 2025 sale belongs to 2025/26.
    assert ais["occurrences"] == [
        "[[£8.04]] accrued interest paid on the purchase of [[TN28]] on [[15 Jun 2026]]",
        "[[£1.53]] accrued interest received on the sale of [[TN28]] on [[25 Aug 2026]]",
    ]


def test_no_ais_notice_below_the_limit():
    notices = build_notices([], None, {**EXEMPT, "ais_applies": False}, 2026)
    assert [n["key"] for n in notices] == ["exempt_securities"]


def test_no_exempt_notices_without_securities():
    assert build_notices([], None, {"securities": [], "ais_applies": False}, 2026) == []
