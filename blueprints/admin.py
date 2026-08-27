"""Admin panel API: who can sign in. Only ADMIN_EMAIL may call these."""

import logging

from flask import Blueprint, g, jsonify, request

from core import auth, repo

_log = logging.getLogger(__name__)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.before_request
def _admin_only():
    if not auth.is_admin(g.get("email")):
        return jsonify({"error": "Admin only"}), 403


def _email_from_body() -> tuple[str | None, str]:
    body = request.get_json(force=True) or {}
    email = str(body.get("email") or "").strip().lower()
    if "@" not in email or " " in email:
        return None, ""
    return email, str(body.get("name") or "").strip()


@bp.get("/access")
def list_access():
    data = repo.list_access()
    admin = auth.ADMIN_EMAIL.lower()
    for row in data["allowed"]:
        row["admin"] = row["email"] == admin
    # The admin is allowed by env, not by allowed_emails — show them anyway.
    if not any(row["admin"] for row in data["allowed"]):
        me = repo.get_user(g.user_id) or {}
        data["allowed"].insert(
            0,
            {
                "email": admin,
                "name": me.get("name", ""),
                "note": "",
                "decided_at": None,
                "first_seen": None,
                "user_since": me.get("created_at"),
                "last_login_at": me.get("last_login_at"),
                "admin": True,
            },
        )
    # The login page refuses new requests past this many pending ones.
    data["pending_limit"] = repo.MAX_PENDING_REQUESTS
    return jsonify(data)


@bp.post("/access/approve")
def approve():
    email, name = _email_from_body()
    if not email:
        return jsonify({"error": "A valid email is required"}), 400
    repo.approve_email(email, name)
    _log.info("admin approved access for %s", email)
    return jsonify({"ok": True})


@bp.post("/access/decline")
def decline():
    email, _ = _email_from_body()
    if not email:
        return jsonify({"error": "A valid email is required"}), 400
    if auth.is_admin(email):
        return jsonify({"error": "You can't revoke your own access"}), 400
    repo.decline_email(email)
    _log.info("admin declined/revoked access for %s", email)
    return jsonify({"ok": True})


@bp.post("/access/forget")
def forget():
    email, _ = _email_from_body()
    if not email:
        return jsonify({"error": "A valid email is required"}), 400
    if auth.is_admin(email):
        return jsonify({"error": "You can't remove your own access"}), 400
    repo.forget_email(email)
    _log.info("admin removed access record for %s", email)
    return jsonify({"ok": True})
