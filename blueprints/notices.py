"""Notice resolutions: the user verifies a warning through the guided form
(core.notices.VERIFICATION) — typed answers, optional evidence file (e.g. the
broker's trade-details PDF), and a note. Evidence is Fernet-encrypted at rest."""

import io
import mimetypes
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, g, jsonify, request, send_file

from core import crypto, paths, repo
from core.notices import verification_for

bp = Blueprint("notices", __name__, url_prefix="/api/notices")

_KEY_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")
_ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MAX_EVIDENCE = 15 * 1024 * 1024


def _valid_key(key: str) -> bool:
    return bool(_KEY_RE.match(key))


def _parse_fields(category: str, form) -> tuple[dict, str | None]:
    """Validate submitted answers against the category's field spec.
    Returns (data, error)."""
    data: dict = {}
    for field in verification_for(category)["fields"]:
        raw = (form.get(field["key"]) or "").strip()
        if not raw:
            continue
        kind = field["type"]
        if kind == "money":
            try:
                data[field["key"]] = str(Decimal(raw.replace(",", "").lstrip("$£€")))
            except InvalidOperation:
                return {}, f"{field['label']} must be a number"
        elif kind == "date":
            try:
                data[field["key"]] = date.fromisoformat(raw).isoformat()
            except ValueError:
                return {}, f"{field['label']} must be a date (YYYY-MM-DD)"
        elif kind == "choice":
            allowed = {o["value"] for o in field.get("options", [])}
            if raw not in allowed:
                return {}, f"{field['label']}: invalid choice"
            data[field["key"]] = raw
        elif kind == "checkbox":
            data[field["key"]] = "true" if raw.lower() in ("true", "1", "on", "yes") else "false"
        else:
            data[field["key"]] = raw[:500]
    return data, None


@bp.put("/<key>")
def resolve(key: str):
    if not _valid_key(key):
        return jsonify({"error": "Bad notice key"}), 400
    category = key.split("__", 1)[0]
    note = (request.form.get("note") or "").strip()
    data, err = _parse_fields(category, request.form)
    if err:
        return jsonify({"error": err}), 400

    evidence_name = None
    file = request.files.get("file")
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in _ALLOWED_EXT:
            return jsonify({"error": "Evidence must be a PDF or image"}), 400
        blob = file.read()
        if not blob:
            return jsonify({"error": "Empty file"}), 400
        if len(blob) > _MAX_EVIDENCE:
            return jsonify({"error": "Evidence file too large (max 15 MB)"}), 400
        dest = paths.evidence_path(g.user_id, key)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(crypto.encrypt(blob))
        evidence_name = file.filename

    if not note and not data and not evidence_name:
        return jsonify(
            {"error": "Nothing to save — answer a question, attach a file or add a note"}
        ), 400

    repo.upsert_resolution(g.user_id, key, note, data, evidence_name)
    return jsonify(repo.get_resolution(g.user_id, key))


@bp.delete("/<key>")
def unresolve(key: str):
    if not _valid_key(key):
        return jsonify({"error": "Bad notice key"}), 400
    repo.delete_resolution(g.user_id, key)
    path = paths.evidence_path(g.user_id, key)
    if os.path.exists(path):
        os.unlink(path)
    return jsonify({"ok": True})


@bp.get("/<key>/evidence")
def evidence(key: str):
    if not _valid_key(key):
        return jsonify({"error": "Bad notice key"}), 400
    res = repo.get_resolution(g.user_id, key)
    path = paths.evidence_path(g.user_id, key)
    if not res or not res["evidence_name"] or not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    with open(path, "rb") as f:
        blob = crypto.decrypt(f.read())
    mimetype = mimetypes.guess_type(res["evidence_name"])[0] or "application/octet-stream"
    return send_file(
        io.BytesIO(blob),
        mimetype=mimetype,
        as_attachment=False,
        download_name=res["evidence_name"],
    )
