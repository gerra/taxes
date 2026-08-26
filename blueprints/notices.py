"""Notice resolutions: the user confirms a warning with a note, optional
sell-to-cover withholding amount, and optional evidence file (e.g. the broker's
trade-details PDF). Evidence is Fernet-encrypted at rest like documents."""

import io
import mimetypes
import os
import re
from decimal import Decimal, InvalidOperation

from flask import Blueprint, g, jsonify, request, send_file

from core import crypto, paths, repo

bp = Blueprint("notices", __name__, url_prefix="/api/notices")

_KEY_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")
_ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MAX_EVIDENCE = 15 * 1024 * 1024


def _valid_key(key: str) -> bool:
    return bool(_KEY_RE.match(key))


@bp.put("/<key>")
def resolve(key: str):
    if not _valid_key(key):
        return jsonify({"error": "Bad notice key"}), 400
    note = (request.form.get("note") or "").strip()
    data: dict = {}
    raw_withholding = (request.form.get("withholding") or "").strip()
    if raw_withholding:
        try:
            data["withholding"] = str(Decimal(raw_withholding.replace(",", "").lstrip("$£€")))
        except InvalidOperation:
            return jsonify({"error": "Withholding must be a number"}), 400

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
