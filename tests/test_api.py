def test_accounts_crud(auth_client):
    resp = auth_client.post(
        "/api/accounts",
        json={"type": "schwab_individual", "name": "Schwab", "first_activity_date": "2020-01-15"},
    )
    assert resp.status_code == 201
    account = resp.get_json()

    resp = auth_client.get("/api/accounts")
    assert any(a["id"] == account["id"] for a in resp.get_json())

    resp = auth_client.put(f"/api/accounts/{account['id']}", json={"name": "Schwab US"})
    assert resp.get_json()["name"] == "Schwab US"

    assert auth_client.delete(f"/api/accounts/{account['id']}").status_code == 200
    assert not any(a["id"] == account["id"] for a in auth_client.get("/api/accounts").get_json())


def test_bad_account_type_rejected(auth_client):
    resp = auth_client.post("/api/accounts", json={"type": "nonsense", "name": "X"})
    assert resp.status_code == 400


def test_mapping_roundtrip(auth_client):
    account = auth_client.post(
        "/api/accounts", json={"type": "bank_generic", "name": "Revolut"}
    ).get_json()
    resp = auth_client.put(
        f"/api/accounts/{account['id']}/mapping",
        json={"date_col": "Date", "amount_col": "Amount", "include_contains": "interest"},
    )
    assert resp.status_code == 200
    assert (
        auth_client.get(f"/api/accounts/{account['id']}/mapping").get_json()["date_col"] == "Date"
    )


def test_planner_inputs_roundtrip(auth_client):
    resp = auth_client.put("/api/planner/2025/inputs", json={"employment_income": 60000})
    assert resp.status_code == 200
    assert auth_client.get("/api/planner/2025/inputs").get_json()["employment_income"] == 60000


def test_planner_without_report(auth_client):
    auth_client.put("/api/planner/2025/inputs", json={"employment_income": 120000})
    data = auth_client.get("/api/planner/2025").get_json()
    assert data["has_report"] is False
    assert any(t["id"] == "sixty_trap" for t in data["tips"])


def test_planner_pension_uses_prior_year_planners(auth_client):
    """Prior years' saved planners supply the income for their taper test; the
    selected year's "Pension total, YYYY/YY" boxes supply the pension inputs."""
    auth_client.put(
        "/api/planner/2023/inputs",
        json={
            "employment_income": 220031.00,
            "pension_employee": 3681.41,
            "pension_employer": 5522.11,
        },
    )
    auth_client.put("/api/planner/2024/inputs", json={"employment_income": 332826.00})
    auth_client.put(
        "/api/planner/2025/inputs",
        json={
            "employment_income": 376182.79,
            "pension_employee": 7067.47,
            "pension_employer": 10601.27,
            "pension_prior_1": 16987.32,
            "pension_prior_2": 9203.52,
            "pension_prior_3": 7509.93,
        },
    )
    try:
        data = auth_client.get("/api/planner/2025").get_json()
        tip = next(t for t in data["tips"] if t["id"] == "pension_headroom")
        assert "= £73,724.49" in tip["detail"]
        assert "£15,094.00" in tip["detail"]  # 2024/25 tapered from its own planner's income
        assert [w for w in tip["warnings"] if "2022/23" in w and "unverified" in w]
        assert not [w for w in tip["warnings"] if "2023/24" in w or "2024/25" in w]
    finally:
        for y in (2023, 2024, 2025):
            auth_client.put(f"/api/planner/{y}/inputs", json={})


def test_checklist_empty(auth_client):
    data = auth_client.get("/api/checklist/2025").get_json()
    assert data["overall"] in ("no_accounts", "missing")


def test_report_404_without_run(auth_client):
    assert auth_client.get("/api/report/2025").status_code == 404


def test_duplicate_account_rejected(auth_client):
    body = {"type": "freetrade_gia", "name": "Freetrade — GIA"}
    assert auth_client.post("/api/accounts", json=body).status_code == 201
    assert auth_client.post("/api/accounts", json=body).status_code == 409
    assert (
        auth_client.post("/api/accounts", json={**body, "name": "freetrade — gia"}).status_code
        == 409
    )


def test_notice_resolution_roundtrip(auth_client):
    import io

    key = "amount_adjusted__META__2025-02-25"
    resp = auth_client.put(
        f"/api/notices/{key}",
        data={
            "note": "sell to cover",
            "withholding": "$10,966.96",
            "file": (io.BytesIO(b"%PDF-1.4 fake"), "trade.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["data"]["withholding"] == "10966.96"
    assert body["evidence_name"] == "trade.pdf"

    ev = auth_client.get(f"/api/notices/{key}/evidence")
    assert ev.status_code == 200
    assert ev.data == b"%PDF-1.4 fake"  # decrypted transparently

    assert auth_client.put(f"/api/notices/{key}", data={"withholding": "abc"}).status_code == 400
    assert auth_client.put("/api/notices/bad key!", data={}).status_code == 400

    assert auth_client.delete(f"/api/notices/{key}").status_code == 200
    assert auth_client.get(f"/api/notices/{key}/evidence").status_code == 404


def test_no_activity_roundtrip(auth_client):
    account = auth_client.post(
        "/api/accounts",
        json={"type": "schwab_individual", "name": "Gap test", "first_activity_date": "2020-01-01"},
    ).get_json()
    bad = auth_client.post(
        f"/api/accounts/{account['id']}/no-activity",
        json={"start": "2021-01-01", "end": "2020-01-01"},
    )
    assert bad.status_code == 400
    ok = auth_client.post(
        f"/api/accounts/{account['id']}/no-activity",
        json={"start": "2020-01-01", "end": "2020-06-30", "note": "account opened, nothing bought"},
    )
    assert ok.status_code == 201
    override_id = ok.get_json()["id"]
    item = next(
        a
        for a in auth_client.get("/api/checklist/2025").get_json()["accounts"]
        if a["account"]["id"] == account["id"]
    )
    assert item["confirmed_empty"][0]["id"] == override_id
    assert auth_client.delete(f"/api/no-activity/{override_id}").status_code == 200


def test_checklist_flags_missing_awards_export(auth_client):
    from core import repo

    account = auth_client.post(
        "/api/accounts", json={"type": "schwab_individual", "name": "Needs awards"}
    ).get_json()
    repo.create_document(
        auth_client.user["id"],
        account["id"],
        "ind.csv",
        "sha-needs",
        10,
        5,
        "2024-01-01",
        "2024-12-31",
        ["3 RSU vest rows (stock-plan activity: META on 2024-05-16) have no price"],
    )
    data = auth_client.get("/api/checklist/2024").get_json()
    assert data["needs"] and data["needs"][0]["type"] == "schwab_awards"

    awards = auth_client.post(
        "/api/accounts", json={"type": "schwab_awards", "name": "Awards"}
    ).get_json()
    repo.create_document(
        auth_client.user["id"],
        awards["id"],
        "eac.csv",
        "sha-eac",
        10,
        5,
        "2024-01-01",
        "2024-12-31",
        [],
    )
    data = auth_client.get("/api/checklist/2024").get_json()
    assert data["needs"] == []
    ind = next(a for a in data["accounts"] if a["account"]["id"] == account["id"])
    assert ind["documents"][0]["warnings"] == []  # explained by the awards doc → hidden


def test_report_years_lists_configured_years(auth_client):
    from core import tax_years

    years = auth_client.get("/api/report/years").get_json()["years"]
    assert years == sorted(tax_years.YEARS)
    assert years == sorted(years)


def test_rejected_upload_is_logged_with_context(auth_client, monkeypatch, caplog):
    """A failed upload must leave the reason in the logs, not just a bare 400."""
    import io
    import logging

    from blueprints import documents

    account = auth_client.post(
        "/api/accounts", json={"type": "freetrade_gia", "name": "GIA"}
    ).get_json()
    monkeypatch.setattr(
        documents.runner,
        "validate_upload",
        lambda _account, _path: {
            "ok": False,
            "error": {"type": "ParsingError", "message": "row 18: Unknown type: 'X'"},
        },
    )
    caplog.set_level(logging.INFO)

    resp = auth_client.post(
        f"/api/accounts/{account['id']}/documents",
        data={"file": (io.BytesIO(b"Title,Type\n"), "GIA_26_08_26.csv")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["message"] == "row 18: Unknown type: 'X'"
    rejected = [r for r in caplog.records if r.name == "blueprints.documents"]
    assert len(rejected) == 1
    assert rejected[0].levelno == logging.WARNING
    assert "GIA_26_08_26.csv" in rejected[0].getMessage()
    assert "freetrade" in rejected[0].getMessage()
    assert "row 18: Unknown type: 'X'" in rejected[0].getMessage()
    api = [r for r in caplog.records if r.name == "api"]
    assert len(api) == 1
    assert api[0].levelno == logging.WARNING
    assert f"POST /api/accounts/{account['id']}/documents -> 400" in api[0].getMessage()
    assert "Unknown type" in api[0].getMessage()


def test_unauthenticated_api_error_logged_at_info(client, caplog):
    """Routine 401s are logged, but must not be warnings."""
    import logging

    caplog.set_level(logging.INFO)
    assert client.get("/api/accounts").status_code == 401
    api = [r for r in caplog.records if r.name == "api"]
    assert len(api) == 1
    assert api[0].levelno == logging.INFO
    assert "GET /api/accounts -> 401" in api[0].getMessage()
