"""Access requests + admin panel: a stranger signs in with Google, the admin
approves/declines/revokes from /api/admin, and sessions honour the decision."""

import pytest

from core import auth, repo


def _google_signin(client, monkeypatch, email, name="Someone"):
    """Drive /oauth/google/callback with a stubbed code exchange."""
    monkeypatch.setattr(
        auth, "exchange_google_code", lambda code: {"sub": "g-1", "email": email, "name": name}
    )
    with client.session_transaction() as sess:
        sess["oauth_state"] = "st"
    return client.get("/oauth/google/callback?state=st&code=abc")


def _cookie(client, name):
    return client.get_cookie(name)


@pytest.fixture(autouse=True)
def _clean_access():
    for email in ("stranger@example.com", "friend@example.com", "manual@example.com"):
        repo.forget_email(email)
    yield


# ── Requester side ─────────────────────────────────────────────────────────────


def test_rejected_signin_records_request_and_sets_access_cookie(client, monkeypatch):
    resp = _google_signin(client, monkeypatch, "Stranger@example.com", "Stra Nger")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
    assert _cookie(client, auth.COOKIE_NAME) is None
    assert _cookie(client, auth.ACCESS_COOKIE_NAME) is not None

    req = repo.get_access_request("stranger@example.com")
    assert req["status"] == "pending" and req["name"] == "Stra Nger" and req["attempts"] == 1

    # Second attempt bumps the counter, stays pending.
    _google_signin(client, monkeypatch, "stranger@example.com")
    assert repo.get_access_request("stranger@example.com")["attempts"] == 2
    assert repo.count_pending_requests() >= 1


def test_access_me_and_note(client, monkeypatch):
    assert client.get("/api/access/me").get_json() is None
    assert client.put("/api/access/me", json={"note": "hi"}).status_code == 401

    _google_signin(client, monkeypatch, "stranger@example.com")
    me = client.get("/api/access/me").get_json()
    assert me == {
        "email": "stranger@example.com",
        "name": "Someone",
        "status": "pending",
        "note": "",
    }

    resp = client.put("/api/access/me", json={"note": "  It's me, from the pub  "})
    assert resp.status_code == 200
    assert client.get("/api/access/me").get_json()["note"] == "It's me, from the pub"


def test_access_token_is_not_a_session(client):
    client.set_cookie(auth.COOKIE_NAME, auth.make_access_token("stranger@example.com"))
    assert client.get("/api/accounts").status_code == 401
    assert client.get("/api/auth/me").get_json() is None


# ── Admin side ─────────────────────────────────────────────────────────────────


def test_admin_endpoints_require_admin(client):
    repo.approve_email("friend@example.com")
    friend = repo.get_or_create_user("friend@example.com", "Friend")
    client.set_cookie(auth.COOKIE_NAME, auth.make_token(friend["id"], friend["email"]))
    assert client.get("/api/auth/me").get_json()["is_admin"] is False
    assert client.get("/api/admin/access").status_code == 403
    assert client.post("/api/admin/access/approve", json={"email": "x@y.z"}).status_code == 403


def test_admin_sees_pending_and_can_approve(auth_client, monkeypatch):
    stranger = auth_client.application.test_client()
    _google_signin(stranger, monkeypatch, "stranger@example.com", "Stra Nger")

    me = auth_client.get("/api/auth/me").get_json()
    assert me["is_admin"] is True and me["pending_requests"] >= 1

    data = auth_client.get("/api/admin/access").get_json()
    pend = [r for r in data["pending"] if r["email"] == "stranger@example.com"]
    assert len(pend) == 1 and pend[0]["name"] == "Stra Nger"
    assert any(r["admin"] for r in data["allowed"])

    assert (
        auth_client.post(
            "/api/admin/access/approve", json={"email": "stranger@example.com"}
        ).status_code
        == 200
    )

    data = auth_client.get("/api/admin/access").get_json()
    assert not any(r["email"] == "stranger@example.com" for r in data["pending"])
    assert any(r["email"] == "stranger@example.com" for r in data["allowed"])

    # …and now they can sign in; the access cookie is cleared on success.
    resp = _google_signin(stranger, monkeypatch, "stranger@example.com", "Stra Nger")
    assert resp.status_code == 302
    assert _cookie(stranger, auth.COOKIE_NAME) is not None
    assert _cookie(stranger, auth.ACCESS_COOKIE_NAME) is None
    assert stranger.get("/api/auth/me").get_json()["email"] == "stranger@example.com"
    assert repo.get_user(stranger.get("/api/auth/me").get_json()["id"])["last_login_at"]


def test_decline_blocks_signin_and_stays_declined(auth_client, monkeypatch):
    stranger = auth_client.application.test_client()
    _google_signin(stranger, monkeypatch, "stranger@example.com")
    assert (
        auth_client.post(
            "/api/admin/access/decline", json={"email": "stranger@example.com"}
        ).status_code
        == 200
    )

    _google_signin(stranger, monkeypatch, "stranger@example.com")
    assert stranger.get("/api/access/me").get_json()["status"] == "declined"
    data = auth_client.get("/api/admin/access").get_json()
    assert any(r["email"] == "stranger@example.com" for r in data["declined"])
    assert not any(r["email"] == "stranger@example.com" for r in data["pending"])


def test_revoke_kills_existing_session(auth_client, monkeypatch):
    auth_client.post("/api/admin/access/approve", json={"email": "friend@example.com"})
    friend = auth_client.application.test_client()
    _google_signin(friend, monkeypatch, "friend@example.com", "Friend")
    assert friend.get("/api/accounts").status_code == 200

    assert (
        auth_client.post(
            "/api/admin/access/decline", json={"email": "friend@example.com"}
        ).status_code
        == 200
    )
    resp = friend.get("/api/accounts")
    assert resp.status_code == 401 and resp.get_json()["error"] == "Access revoked"
    assert friend.get("/api/auth/me").get_json() is None


def test_manual_preapprove_and_forget(auth_client):
    assert auth_client.post("/api/admin/access/approve", json={"email": "nope"}).status_code == 400
    auth_client.post("/api/admin/access/approve", json={"email": " Manual@Example.com "})
    assert repo.is_email_allowed("manual@example.com")
    data = auth_client.get("/api/admin/access").get_json()
    assert any(r["email"] == "manual@example.com" for r in data["allowed"])

    auth_client.post("/api/admin/access/forget", json={"email": "manual@example.com"})
    assert not repo.is_email_allowed("manual@example.com")
    assert repo.get_access_request("manual@example.com") is None


def test_admin_cannot_lock_themselves_out(auth_client):
    for path in ("decline", "forget"):
        resp = auth_client.post(f"/api/admin/access/{path}", json={"email": "admin@example.com"})
        assert resp.status_code == 400
    assert auth_client.get("/api/accounts").status_code == 200
