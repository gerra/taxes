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
    """Decode and verify a JWT. Returns payload dict or None on any error."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        return None


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
