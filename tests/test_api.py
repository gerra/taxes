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
