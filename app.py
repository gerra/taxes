"""taxes.gerra.sh backend.

Dev:  python app.py   (API on :5002)  +  cd web && npm run dev  (UI on :5173)
Prod: cd web && npm run build,  then gunicorn serves everything on :5002
"""

import logging
import os
import secrets
import sys

from dotenv import load_dotenv

# Load env vars BEFORE any project imports that read them at module level
# (core.auth captures GOOGLE_CLIENT_ID / BASE_URL on import). secrets/.env holds
# shared + prod-default values (deployed verbatim); secrets/.env.local overlays
# dev-only keys and is git-ignored and never deployed.
load_dotenv("secrets/.env")
load_dotenv("secrets/.env.local", override=True)

# Send all loggers to stdout so systemd's journald captures them.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    stream=sys.stdout,
)

from flask import Flask, g, jsonify, request, send_from_directory  # noqa: E402

from blueprints import accounts, calc, documents, planner, report  # noqa: E402
from blueprints import auth as auth_bp  # noqa: E402
from core import auth, db  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # statement uploads

DIST = os.path.join(os.path.dirname(__file__), "web", "dist")

db.ensure_db()

# ── Register blueprints ────────────────────────────────────────────────────────

app.register_blueprint(auth_bp.bp)
app.register_blueprint(accounts.bp)
app.register_blueprint(documents.bp)
app.register_blueprint(calc.bp)
app.register_blueprint(report.bp)
app.register_blueprint(planner.bp)

# ── Auth middleware ────────────────────────────────────────────────────────────


@app.before_request
def _check_auth():
    """Populate g.user_id/g.email for all /api/* routes.

    /api/auth/me is exempted — it returns null gracefully when not logged in
    so the browser doesn't show a red 401 on the initial page load.
    """
    if not request.path.startswith("/api/"):
        return
    if request.path == "/api/auth/me":
        return
    token = request.cookies.get(auth.COOKIE_NAME)
    payload = auth.decode_token(token) if token else None
    if not payload:
        return jsonify({"error": "Not authenticated"}), 401
    g.user_id = int(payload["sub"])
    g.email = payload["email"]
    g.auth_payload = payload


@app.after_request
def _refresh_auth_cookie(response):
    """Sliding session: re-issue the auth cookie when it nears expiry."""
    payload = g.get("auth_payload")
    if payload and auth.needs_refresh(payload):
        from core import repo

        user = repo.get_user(g.user_id)
        if user:
            auth.set_auth_cookie(response, user["id"], user["email"])
        else:
            response.delete_cookie(auth.COOKIE_NAME)
    return response


# ── Serve React SPA (production) ──────────────────────────────────────────────


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    if os.path.isdir(DIST):
        target = os.path.join(DIST, path)
        if path and os.path.isfile(target):
            return send_from_directory(DIST, path)
        return send_from_directory(DIST, "index.html")
    return (
        "<p>Frontend not built. Run: <code>cd web && npm install && npm run build</code></p>",
        503,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5002)
