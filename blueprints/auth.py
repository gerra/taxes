"""Auth HTTP routes: Google OAuth flow, /logout, /api/auth/me."""

import logging
import secrets
import urllib.parse

import requests
from flask import Blueprint, jsonify, redirect, request, session

from core import auth, repo

_log = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)


@bp.get("/oauth/google/start")
def google_start():
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    return redirect(auth.google_auth_url(state))


@bp.get("/oauth/google/callback")
def google_callback():
    if request.args.get("state") != session.pop("oauth_state", None):
        return "Invalid OAuth state", 400
    code = request.args.get("code")
    if not code:
        return "Missing authorization code", 400
    try:
        info = auth.exchange_google_code(code)
    except requests.RequestException:
        _log.exception("Google code exchange failed")
        return "Google sign-in failed, try again", 502

    user = repo.get_or_create_user(info["email"], info["name"])
    if user is None:
        _log.warning("sign-in rejected for %s (not in allowed_emails)", info["email"])
        return redirect("/?denied=" + urllib.parse.quote(info["email"]))

    resp = redirect("/")
    auth.set_auth_cookie(resp, user["id"], user["email"])
    _log.info("user %s signed in", user["email"])
    return resp


@bp.get("/logout")
def logout():
    resp = redirect("/")
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp


@bp.get("/api/auth/me")
def me():
    """Login-state probe — returns null instead of 401 so the SPA can check quietly."""
    token = request.cookies.get(auth.COOKIE_NAME)
    payload = auth.decode_token(token) if token else None
    if not payload:
        return jsonify(None)
    user = repo.get_user(int(payload["sub"]))
    if not user:
        return jsonify(None)
    return jsonify({"id": user["id"], "email": user["email"], "name": user["name"]})
