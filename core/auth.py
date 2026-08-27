"""JWT cookie + Google OAuth helpers (fintrack's auth trimmed to Google-only)."""

import os
import time
import urllib.parse

import jwt
import requests

COOKIE_NAME = "tx_auth"
JWT_ALGO = "HS256"
JWT_EXPIRY = 7 * 24 * 3600  # 7 days
REFRESH_THRESHOLD = 3 * 24 * 3600  # re-issue cookie when less than 3 days remain

# Set after a Google sign-in by an email that isn't allowed yet, so the login page
# can show that email's request status and let them leave a note for the admin.
ACCESS_COOKIE_NAME = "tx_access"
ACCESS_EXPIRY = 24 * 3600

# Required in secrets/.env
JWT_SECRET = os.environ.get("JWT_SECRET", "")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5002")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"


def make_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": int(time.time()) + JWT_EXPIRY,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token: str) -> dict | None:
    """Decode and verify a JWT. Returns payload dict or None on any error.

    Access-request tokens carry purpose=access and are never accepted here.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        return None
    return None if payload.get("purpose") else payload


def is_admin(email: str | None) -> bool:
    return bool(email and ADMIN_EMAIL and email.lower() == ADMIN_EMAIL.lower())


def make_access_token(email: str) -> str:
    payload = {
        "purpose": "access",
        "email": email,
        "exp": int(time.time()) + ACCESS_EXPIRY,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_access_token(token: str) -> str | None:
    """Return the email an access-request token was issued for, or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != "access":
        return None
    return payload.get("email") or None


def set_access_cookie(response, email: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        make_access_token(email),
        httponly=True,
        samesite="Lax",
        secure=BASE_URL.startswith("https://"),
        max_age=ACCESS_EXPIRY,
    )


def needs_refresh(payload: dict) -> bool:
    exp = payload.get("exp")
    if not isinstance(exp, int):
        return False
    return exp - int(time.time()) < REFRESH_THRESHOLD


def set_auth_cookie(response, user_id: int, email: str) -> None:
    token = make_token(user_id, email)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="Lax",
        secure=BASE_URL.startswith("https://"),
        max_age=JWT_EXPIRY,
    )


def google_auth_url(state: str) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{BASE_URL}/oauth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        # Always show Google's account chooser, even when the browser already
        # has a live Google session: signing out here must let you come back as
        # somebody else, and a silent auto-redirect looks like no auth at all.
        "prompt": "select_account",
    }
    return _GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_google_code(code: str) -> dict:
    """Exchange an authorization code for Google user info: {sub, email, name}.

    Raises requests.HTTPError on network/API failures.
    """
    token_resp = requests.post(
        _GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": f"{BASE_URL}/oauth/google/callback",
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    userinfo_resp = requests.get(
        _GOOGLE_USERINFO,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    userinfo_resp.raise_for_status()
    info = userinfo_resp.json()
    return {"sub": info["sub"], "email": info["email"], "name": info.get("name", "")}
