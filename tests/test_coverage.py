from datetime import date

from core.coverage import _gaps, _merge_ranges, account_coverage


def _d(s):
    return date.fromisoformat(s)


def test_merge_overlapping_and_adjacent():
    merged = _merge_ranges(
        [
            (_d("2024-01-01"), _d("2024-06-30")),
            (_d("2024-05-01"), _d("2024-12-31")),
            (_d("2025-01-01"), _d("2025-03-01")),
        ]
    )
    # adjacent (1 day apart) ranges merge too
    assert merged == [(_d("2024-01-01"), _d("2025-03-01"))]


def test_gap_in_middle():
    gaps = _gaps(
        (_d("2022-01-01"), _d("2024-12-31")),
        [(_d("2022-01-01"), _d("2022-12-31")), (_d("2024-01-01"), _d("2024-12-31"))],
    )
    assert gaps == [(_d("2023-01-01"), _d("2023-12-31"))]


def test_gap_at_both_ends():
    gaps = _gaps(
        (_d("2022-01-01"), _d("2024-12-31")),
        [(_d("2023-01-01"), _d("2023-06-30"))],
    )
    assert gaps == [
        (_d("2022-01-01"), _d("2022-12-31")),
        (_d("2023-07-01"), _d("2024-12-31")),
    ]


def test_account_coverage_missing_and_soft_gaps():
    account = {
        "id": 1,
        "type": "schwab_individual",
        "name": "S",
        "first_activity_date": "2024-05-01",
    }
    result = account_coverage(account, [], 2024)
    assert result["status"] == "missing"

    docs = [
        {"date_min": "2024-05-01", "date_max": "2024-09-30"},
        # 10-day seam — soft gap, still "ok"
        {"date_min": "2024-10-10", "date_max": "2026-12-31"},
    ]
    result = account_coverage(account, docs, 2024)
    assert result["status"] == "ok"
    assert len(result["soft_gaps"]) == 1


def test_bank_account_only_needs_tax_year():
    account = {"id": 2, "type": "bank_generic", "name": "R", "first_activity_date": "2015-01-01"}
    docs = [{"date_min": "2024-04-06", "date_max": "2025-04-05"}]
    result = account_coverage(account, docs, 2024)
    assert result["status"] == "ok"
    assert result["required"]["start"] == "2024-04-06"


def test_confirmed_no_activity_closes_gap():
    account = {
        "id": 3,
        "type": "schwab_individual",
        "name": "S",
        "first_activity_date": "2022-01-01",
    }
    docs = [
        {"date_min": "2022-01-01", "date_max": "2022-12-31", "warnings": []},
        {"date_min": "2024-01-01", "date_max": "2026-12-31", "warnings": []},
    ]
    without = account_coverage(account, docs, 2024)
    assert without["status"] == "gaps"
    assert without["gaps"] == [{"start": "2023-01-01", "end": "2023-12-31"}]

    overrides = [{"id": 9, "start": "2023-01-01", "end": "2023-12-31", "note": "no trades"}]
    with_override = account_coverage(account, docs, 2024, overrides)
    assert with_override["status"] == "ok"
    assert with_override["gaps"] == []
    assert with_override["confirmed_empty"][0]["id"] == 9
    # documents-only coverage still reported separately for the bar
    assert len(with_override["covered"]) == 2
