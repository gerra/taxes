"""Document uploads (parse-validated), listing, deletion, checklist, spin-offs."""

import hashlib
import logging
import os
import uuid

from flask import Blueprint, g, jsonify, request

from core import coverage, crypto, paths, repo
from engine import runner

_log = logging.getLogger(__name__)

bp = Blueprint("documents", __name__)


@bp.post("/api/accounts/<int:account_id>/documents")
def upload(account_id: int):
    account = repo.get_account(g.user_id, account_id)
    if not account:
        return jsonify({"error": "Not found"}), 404
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file provided"}), 400

    data = file.read()
    if not data:
        return jsonify({"error": "Empty file"}), 400
    sha = hashlib.sha256(data).hexdigest()

    tmp_path = os.path.join(paths.TMP_DIR, f"upload_{uuid.uuid4().hex}")
    os.makedirs(paths.TMP_DIR, exist_ok=True)
    with open(tmp_path, "wb") as f:
        f.write(data)
    try:
        result = runner.validate_upload(account, tmp_path)
    finally:
        os.unlink(tmp_path)

    if result.get("needs_mapping"):
        return jsonify(
            {
                "needs_mapping": True,
                "headers": result.get("headers", []),
                "sample": result.get("sample", []),
            }
        ), 409
    if not result.get("ok"):
        return jsonify({"error": result.get("error")}), 400

    doc = repo.create_document(
        g.user_id,
        account_id,
        file.filename,
        sha,
        len(data),
        result.get("tx_count", 0),
        result.get("date_min"),
        result.get("date_max"),
        result.get("warnings", []),
    )
    if doc is None:
        return jsonify(
            {"error": {"type": "duplicate", "message": "Identical file already uploaded"}}
        ), 409

    dest = paths.doc_path(account_id, doc["id"])
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(crypto.encrypt(data))
    _log.info(
        "stored document %s for account %s (%s transactions)",
        doc["id"],
        account_id,
        doc["tx_count"],
    )
    return jsonify(doc), 201


@bp.get("/api/documents")
def list_docs():
    account_id = request.args.get("account_id", type=int)
    return jsonify(repo.list_documents(g.user_id, account_id))


@bp.delete("/api/documents/<int:doc_id>")
def delete_doc(doc_id: int):
    doc = repo.get_document(g.user_id, doc_id)
    if not doc:
        return jsonify({"error": "Not found"}), 404
    repo.delete_document(g.user_id, doc_id)
    path = paths.doc_path(doc["account_id"], doc_id)
    if os.path.exists(path):
        os.unlink(path)
    return jsonify({"ok": True})


@bp.get("/api/checklist/<int:tax_year>")
def checklist(tax_year: int):
    return jsonify(coverage.checklist(g.user_id, tax_year))


@bp.get("/api/spin-offs")
def list_spin_offs():
    return jsonify(repo.list_spin_offs(g.user_id))


@bp.post("/api/spin-offs")
def add_spin_off():
    body = request.get_json(force=True)
    dst, src = (body.get("dst") or "").strip(), (body.get("src") or "").strip()
    if not dst or not src:
        return jsonify({"error": "dst and src are required"}), 400
    repo.upsert_spin_off(g.user_id, dst, src)
    return jsonify({"ok": True}), 201
