"""Test environment: isolated data dir + secrets BEFORE any project import
(core.paths and core.auth capture env at import time)."""

import os
import tempfile

from cryptography.fernet import Fernet

_DATA_DIR = tempfile.mkdtemp(prefix="taxes_test_")
os.environ["TAXES_DATA_DIR"] = _DATA_DIR
os.environ["JWT_SECRET"] = "test-jwt-secret"
os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["BASE_URL"] = "http://localhost:5002"

import pytest  # noqa: E402

from app import app as flask_app  # noqa: E402
from core import auth, repo  # noqa: E402


@pytest.fixture
def app():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user():
    return repo.get_or_create_user("admin@example.com", "Admin")


@pytest.fixture
def auth_client(client, user):
    token = auth.make_token(user["id"], user["email"])
    client.set_cookie(auth.COOKIE_NAME, token)
    client.user = user
    return client
