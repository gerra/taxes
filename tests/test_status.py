"""The step rail's source of truth: what state each step is in, and what the
app should tell the user to do next.

The four tabs used to say only what existed. This says what order the work
happens in and what is blocking, which is the whole reason the rail can answer
"what do I do now" without the user having to hold the pipeline in their head.
"""

import json
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


def _report(uid, **kwargs):
    data = status.build(uid, YEAR, today=TODAY, **kwargs)
    return next(s for s in data["steps"] if s["key"] == "report")


def _ok_run(uid, material: dict | None):
    run = repo.create_calc_run(
        uid, YEAR, "irrelevant", json.dumps(material) if material is not None else None
    )
    repo.set_calc_run_status(run["id"], "ok", bundle="{}")


BASE = {
    "tax_year": YEAR,
    "fork": "abc",
    "engine": 4,
    "balance_check": True,
    "docs": [[1, "sha-a"]],
    "spin_offs": [],
    "exempt": [],
    "interest_funds": [],
    "mappings": [],
}


def test_out_of_date_names_what_changed(uid):
    """An assertion nobody can check is how the false positive survived: a
    wrong "out of date" looked exactly like a right one."""
    _ok_run(uid, BASE)

    report = _report(uid, current_material={**BASE, "docs": [[1, "sha-a"], [1, "sha-b"]]})
    assert report["stale"] is True
    assert report["headline"] == "Out of date"
    assert report["changes"] == ["uploaded documents (1 added)"]
    assert "1 added" in report["detail"]


def test_a_waived_balance_check_is_a_run_option_not_a_changed_input(uid):
    """The regression: every report read "Out of date" the moment it finished.

    The engine folds `balance_check` into its cache key, because a waived run is
    a different calculation and must not be served from a checked run's cache.
    Treating it as an input condemned every waived run — which, for a document
    set that cannot pass the check (a Freetrade export missing its old top-ups),
    is every run there will ever be."""
    _ok_run(uid, {**BASE, "balance_check": False})
    report = _report(uid, current_material={**BASE, "balance_check": True})
    assert report["stale"] is False
    assert report["changes"] == []


def test_unchanged_inputs_are_never_stale(uid):
    _ok_run(uid, BASE)
    assert _report(uid, current_material=dict(BASE))["stale"] is False


def test_the_material_survives_the_database_round_trip(uid):
    """The second way "Out of date" became permanent.

    The material is stored as JSON. A Python tuple hashes identically to a list,
    so the cache never noticed, but it comes back out of SQLite as a list — so
    every stored run differed from every live one on `docs`, `spin_offs` and
    `mappings`, and no amount of regenerating could ever clear it."""
    from engine import runner

    live = runner.input_material(uid, YEAR)
    assert json.loads(json.dumps(live)) == live

    _ok_run(uid, live)
    assert _report(uid, current_material=runner.input_material(uid, YEAR))["stale"] is False


def test_a_run_predating_the_recorded_material_claims_nothing(uid):
    """Guessing is worse than silence here: a wrong guess condemns a good report
    and re-running never clears it, because the next run is judged the same."""
    _ok_run(uid, None)
    assert _report(uid, current_material=dict(BASE))["stale"] is False
    assert _report(uid)["stale"] is False


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


def test_a_freshly_finished_run_is_never_out_of_date(auth_client):
    """End to end, through the engine's own recording, both ways round.

    The bug this pins was invisible to a unit test with made-up values: it lived
    in the gap between what the engine stores and what status asked it for."""
    from engine import runner

    uid = auth_client.user["id"]
    for waived in (False, True):
        material = runner.input_material(uid, 2022, balance_check=not waived)
        run = repo.create_calc_run(uid, 2022, runner.hash_material(material), json.dumps(material))
        repo.set_calc_run_status(run["id"], "ok", bundle="{}")
        report = next(
            s
            for s in auth_client.get("/api/status/2022").get_json()["steps"]
            if s["key"] == "report"
        )
        assert report["stale"] is False, f"waived={waived} run read as out of date"


def test_the_status_response_is_never_cached(auth_client):
    """An endpoint whose job is to say whether what you see is current must not
    itself be served from cache: one stale reading would keep saying "out of
    date" however many times the report is regenerated."""
    resp = auth_client.get(f"/api/status/{YEAR}")
    assert "no-store" in resp.headers.get("Cache-Control", "")


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
