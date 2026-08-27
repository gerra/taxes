"""Auth HTTP routes: Google OAuth flow, /logout, /api/auth/me, and the
access-request endpoints a not-yet-allowed visitor can use from the login page."""

import logging
import re
import secrets

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
        req = repo.record_access_request(info["email"], info["name"])
        if req["is_new"]:
            _log.warning(
                "ACCESS REQUEST from %s (%s) — approve it in the Admin tab",
                req["email"],
                req["name"],
            )
        else:
            _log.info("sign-in attempt %d by %s (%s)", req["attempts"], req["email"], req["status"])
        resp = redirect("/")
        auth.set_access_cookie(resp, req["email"])
        return resp

    repo.touch_last_login(user["id"])
    resp = redirect("/")
    auth.set_auth_cookie(resp, user["id"], user["email"])
    resp.delete_cookie(auth.ACCESS_COOKIE_NAME)
    _log.info("user %s signed in", user["email"])
    return resp


@bp.get("/logout")
def logout():
    """Drop every trace of the session this browser holds: the auth cookie, the
    access-request cookie a rejected visitor may still carry, and the Flask
    session holding the OAuth state. Google's own session is untouched (signing
    someone out of Gmail is not ours to do) — but /oauth/google/start asks for
    the account chooser, so the next sign-in can be a different person.
    """
    session.clear()
    resp = redirect("/")
    resp.delete_cookie(auth.COOKIE_NAME)
    resp.delete_cookie(auth.ACCESS_COOKIE_NAME)
    return resp


@bp.get("/api/auth/me")
def me():
    """Login-state probe — returns null instead of 401 so the SPA can check quietly."""
    token = request.cookies.get(auth.COOKIE_NAME)
    payload = auth.decode_token(token) if token else None
    if not payload:
        return jsonify(None)
    user = repo.get_user(int(payload["sub"]))
    if not user or not repo.is_email_allowed(user["email"]):
        return jsonify(None)
    out = {"id": user["id"], "email": user["email"], "name": user["name"], "is_admin": False}
    if auth.is_admin(user["email"]):
        out["is_admin"] = True
        out["pending_requests"] = repo.count_pending_requests()
    return jsonify(out)


# ── Access requests (unauthenticated; identified by the tx_access cookie) ─────


def _access_email() -> str | None:
    token = request.cookies.get(auth.ACCESS_COOKIE_NAME)
    return auth.decode_access_token(token) if token else None


@bp.get("/api/access/me")
def access_me():
    """Status of the visitor's access request, or null if they haven't signed in
    with Google recently. Exempt from the auth middleware (see app.py)."""
    email = _access_email()
    req = repo.get_access_request(email) if email else None
    if not req:
        return jsonify(None)
    return jsonify(
        {"email": req["email"], "name": req["name"], "status": req["status"], "note": req["note"]}
    )


# Deliberately loose — Google is the real check. This only keeps obvious junk
# (and anything with a newline in it) out of the pending list.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


@bp.post("/api/access/request")
def access_request():
    """Ask for access from the login page WITHOUT signing in with Google first.

    Public and unauthenticated, so the pending list is capped
    (repo.MAX_PENDING_REQUESTS) — past that, requests are refused rather than
    stored. The reply is the same whether the email is new, already waiting or
    already allowed: it must not report who is on the allowed list.
    """
    body = request.get_json(silent=True) or {}
    email = str(body.get("email") or "").strip().lower()[:254]
    name = str(body.get("name") or "").strip()[:100]
    note = str(body.get("note") or "").strip()[:500]
    if not _EMAIL_RE.match(email):
        return jsonify({"error": "That doesn’t look like an email address"}), 400

    outcome = repo.request_access(email, name, note)
    if outcome == "full":
        _log.warning(
            "access request from %s refused: %d requests already unanswered",
            email,
            repo.MAX_PENDING_REQUESTS,
        )
        return jsonify(
            {
                "error": "There are too many unanswered requests right now. "
                "Try again in a few days, or reach the owner another way."
            }
        ), 429
    if outcome == "created":
        _log.warning(
            "ACCESS REQUEST from %s (%s) — approve it in the Admin tab: %s",
            email,
            name or "no name",
            note[:200] or "no note",
        )
    else:
        _log.info("access request from %s: %s", email, outcome)
    return jsonify({"ok": True})


@bp.put("/api/access/me")
def access_note():
    """Let the requester leave a short message for the admin."""
    email = _access_email()
    req = repo.get_access_request(email) if email else None
    if not req:
        return jsonify({"error": "No access request for this browser"}), 401
    body = request.get_json(force=True) or {}
    note = str(body.get("note") or "").strip()[:500]
    repo.set_access_request_note(email, note)
    _log.info("access request note from %s: %s", email, note[:200])
    return jsonify({"ok": True, "note": note})
