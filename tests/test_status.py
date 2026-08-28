"""The step rail's source of truth: what state each step is in, and what the
app should tell the user to do next.

The four tabs used to say only what existed. This says what order the work
happens in and what is blocking, which is the whole reason the rail can answer
"what do I do now" without the user having to hold the pipeline in their head.
"""

from datetime import date

import pytest

from core import repo, status

# The suite shares one database, and 2024 is the worked example half the other
# tests write to. A user of its own keeps these assertions about what is and
# isn't done from depending on what ran before them.
_seq = iter(range(1000))


@pytest.fixture
def uid():
    email = f"status-{next(_seq)}@example.com"
    repo.approve_email(email)
    return repo.get_or_create_user(email, "Status")["id"]


@pytest.fixture
def planner(uid):
    def save(tax_year: int, inputs: dict):
        repo.set_planner_inputs(uid, tax_year, inputs)

    return save


YEAR = 2024
TODAY = date(2025, 6, 1)


def test_a_brand_new_year_points_at_documents_first(uid):
    data = status.build(uid, YEAR, today=TODAY)
    steps = {s["key"]: s for s in data["steps"]}
    assert steps["documents"]["state"] == "todo"
    assert steps["income"]["state"] == "todo"
    assert steps["report"]["state"] == "todo"
    # The one thing to do now is the first broken link in the chain, not the
    # last: everything downstream is computed from it.
    assert data["next"]["key"] == "documents"


def test_pay_without_tax_deducted_is_not_a_reconciled_p60(uid, planner):
    """Pay alone can't reconcile PAYE — a missing tax figure read as nil would
    turn the whole year's PAYE into a shortfall."""
    planner(YEAR, {"employments": [{"pay": 90000}]})
    steps = {s["key"]: s for s in status.build(uid, YEAR, today=TODAY)["steps"]}
    assert steps["income"]["state"] == "attention"
    assert "investments only" in steps["income"]["headline"]

    planner(YEAR, {"employments": [{"pay": 90000, "tax_deducted": 25000}]})
    steps = {s["key"]: s for s in status.build(uid, YEAR, today=TODAY)["steps"]}
    assert steps["income"]["state"] == "done"


def test_a_report_run_from_documents_that_have_since_changed_reads_stale(uid):
    run = repo.create_calc_run(uid, YEAR, "hash-at-the-time")
    repo.set_calc_run_status(run["id"], "ok", bundle="{}")

    fresh = status.build(uid, YEAR, today=TODAY, current_hash="hash-at-the-time")
    report = next(s for s in fresh["steps"] if s["key"] == "report")
    # Documents are still incomplete, so it reads provisional rather than
    # settled — but it is not out of date, which is a different complaint.
    assert report["stale"] is False
    assert report["headline"] == "Provisional"

    moved = status.build(uid, YEAR, today=TODAY, current_hash="a-different-hash")
    report = next(s for s in moved["steps"] if s["key"] == "report")
    assert report["stale"] is True
    assert report["state"] == "attention"
    assert report["headline"] == "Out of date"


def test_staleness_is_unknown_rather_than_asserted_without_a_hash(uid):
    """Better to say nothing than to call a good report out of date."""
    run = repo.create_calc_run(uid, YEAR, "h")
    repo.set_calc_run_status(run["id"], "ok", bundle="{}")
    report = next(s for s in status.build(uid, YEAR, today=TODAY)["steps"] if s["key"] == "report")
    assert report["stale"] is False


def test_the_deadline_is_what_the_year_is_actually_running_towards(uid):
    """A year still open has moves left in it; a closed one only has a return."""
    running = status.build(uid, 2025, today=date(2025, 6, 1))
    assert running["in_progress"] is True
    assert running["deadline"]["what"] == "act"
    assert running["deadline"]["date"] == "2026-04-05"

    closed = status.build(uid, 2024, today=date(2025, 6, 1))
    assert closed["in_progress"] is False
    assert closed["deadline"]["what"] == "file"
    assert closed["deadline"]["date"] == "2026-01-31"


def test_the_endpoint_serves_the_same_picture(auth_client):
    body = auth_client.get(f"/api/status/{YEAR}").get_json()
    assert [s["key"] for s in body["steps"]] == ["documents", "income", "report", "plan"]
    assert body["label"] == "2024/25"
    # The endpoint is the only caller that supplies the engine's hash, so
    # staleness comes back decided rather than unknown.
    assert isinstance(body["steps"][2]["stale"], bool)
    assert body["next"]["key"] in {"documents", "income", "report", "plan"}


def test_an_unknown_tax_year_is_refused(auth_client):
    assert auth_client.get("/api/status/1999").status_code == 400
