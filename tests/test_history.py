"""Estimate vs. what HMRC actually charged, across years.

The comparison exists because a single year's page cannot tell you whether the
return you actually filed agreed with it. 2023/24 is the worked example: the
tool now says £723.60 and the return went in at £621.45, and the £102 gap is
made of three separate mistakes that no single figure would have surfaced.
"""

import pytest

from core import repo


@pytest.fixture
def planner(auth_client):
    def save(tax_year: int, inputs: dict):
        repo.set_planner_inputs(auth_client.user["id"], tax_year, inputs)

    return save


def test_history_is_empty_without_inputs_or_runs(auth_client):
    body = auth_client.get("/api/history").get_json()
    assert body["years"] == []
    assert body["mismatched"] == []


def test_history_reports_the_estimate_and_what_was_paid(auth_client, planner):
    planner(
        2023,
        {
            "employments": [
                {"pay": 220031.43, "tax_deducted": 84533.40, "tax_code": "151T"},
            ],
            "actual_tax_paid": 621.45,
        },
    )
    row = auth_client.get("/api/history").get_json()["years"][0]
    assert row["tax_year"] == 2023
    assert row["label"] == "2023/24"
    assert row["reconciled"] is True
    assert row["estimate"] == pytest.approx(683.55)
    assert row["actual"] == pytest.approx(621.45)
    # Negative: less was paid than these figures say was due.
    assert row["difference"] == pytest.approx(-62.10)
    assert row["matches"] is False


def test_a_year_that_agrees_is_not_flagged(auth_client, planner):
    """The filed 2023/24 figures, with no investment income in the planner, so
    the whole bill is the PAYE shortfall less the credit claimed on gains:
    85,216.95 - 84,553.40 - 54.00."""
    planner(
        2023,
        {
            "employments": [{"pay": 220031, "tax_deducted": 84553.40}],
            "tax_paid_on_gains": 54,
            "actual_tax_paid": 609.55,
        },
    )
    body = auth_client.get("/api/history").get_json()
    row = body["years"][0]
    assert row["estimate"] == pytest.approx(609.55)
    assert row["difference"] == pytest.approx(0)
    assert row["matches"] is True
    assert body["mismatched"] == []


def test_a_year_that_disagrees_is_flagged(auth_client, planner):
    planner(
        2023,
        {
            "employments": [{"pay": 220031, "tax_deducted": 84553.40}],
            "tax_paid_on_gains": 54,
            "actual_tax_paid": 500,
        },
    )
    body = auth_client.get("/api/history").get_json()
    assert body["years"][0]["difference"] == pytest.approx(-109.55)
    assert body["mismatched"] == [2023]


def test_a_year_with_no_actual_figure_is_not_compared(auth_client, planner):
    planner(2023, {"employments": [{"pay": 220031.43, "tax_deducted": 84533.40}]})
    body = auth_client.get("/api/history").get_json()
    row = body["years"][0]
    assert row["actual"] is None
    assert row["difference"] is None
    assert row["matches"] is False
    assert body["mismatched"] == []


def test_years_without_a_p60_are_listed_as_unreconciled(auth_client, planner):
    planner(2023, {"employment_income": 220031.43})
    body = auth_client.get("/api/history").get_json()
    assert body["unreconciled"] == [2023]
    assert body["years"][0]["reconciled"] is False
    # Investment income only, so the estimate is the sub-total, not a bill.
    assert body["years"][0]["estimate"] == pytest.approx(body["years"][0]["investment_only"])


def test_the_employment_shortfall_is_broken_out_per_year(auth_client, planner):
    planner(2023, {"employments": [{"pay": 220031.43, "tax_deducted": 84533.40}]})
    row = auth_client.get("/api/history").get_json()["years"][0]
    assert row["employment_shortfall"] == pytest.approx(683.55)
    assert row["investment_only"] == pytest.approx(0)


def test_history_covers_several_years_in_order(auth_client, planner):
    planner(2023, {"employments": [{"pay": 220031.43, "tax_deducted": 84533.40}]})
    planner(2024, {"employments": [{"pay": 100000, "tax_deducted": 27432}]})
    years = [r["tax_year"] for r in auth_client.get("/api/history").get_json()["years"]]
    assert years == [2023, 2024]


def test_history_needs_a_signed_in_user(client):
    assert client.get("/api/history").status_code == 401
