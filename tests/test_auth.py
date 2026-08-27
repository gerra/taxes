from core import auth, repo


def test_api_requires_auth(client):
    assert client.get("/api/accounts").status_code == 401


def test_me_returns_null_when_logged_out(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.get_json() is None


def test_me_returns_user_when_logged_in(auth_client):
    data = auth_client.get("/api/auth/me").get_json()
    assert data["email"] == "admin@example.com"


def test_unknown_email_rejected():
    assert repo.get_or_create_user("stranger@example.com", "X") is None


def test_admin_email_always_allowed():
    user = repo.get_or_create_user("admin@example.com", "Admin")
    assert user is not None and user["email"] == "admin@example.com"


def test_signin_always_asks_google_for_the_account_chooser(client):
    """No silent auto-redirect: a signed-out browser must be able to come back
    as a different Google account."""
    resp = client.get("/oauth/google/start")
    assert resp.status_code == 302
    dest = resp.headers["Location"]
    assert dest.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "prompt=select_account" in dest


def test_logout_clears_auth_and_access_cookies(auth_client, monkeypatch):
    """Signing out drops both cookies, so the browser keeps no identity at all."""
    monkeypatch.setattr(
        auth,
        "exchange_google_code",
        lambda code: {"sub": "g-1", "email": "stranger@example.com", "name": "S"},
    )
    with auth_client.session_transaction() as sess:
        sess["oauth_state"] = "st"
    auth_client.get("/oauth/google/callback?state=st&code=abc")  # leaves a tx_access cookie
    user = auth_client.user
    auth_client.set_cookie(auth.COOKIE_NAME, auth.make_token(user["id"], user["email"]))
    assert auth_client.get_cookie(auth.ACCESS_COOKIE_NAME) is not None
    try:
        resp = auth_client.get("/logout")
        assert resp.status_code == 302
        assert auth_client.get_cookie(auth.COOKIE_NAME) is None
        assert auth_client.get_cookie(auth.ACCESS_COOKIE_NAME) is None
        assert auth_client.get("/api/auth/me").get_json() is None
        assert auth_client.get("/api/access/me").get_json() is None
    finally:
        repo.forget_email("stranger@example.com")
