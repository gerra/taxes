from core import repo


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
