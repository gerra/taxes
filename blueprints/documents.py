"""Document uploads (parse-validated), listing, deletion, checklist, spin-offs."""

import hashlib
import logging
import os
import shutil
import uuid

from flask import Blueprint, g, jsonify, request

from core import coverage, crypto, paths, repo
from engine import runner

_log = logging.getLogger(__name__)

bp = Blueprint("documents", __name__)


def _safe_basename(filename: str) -> str:
    """The upload's own filename with any directory stripped. It is kept as sent,
    spaces and all, rather than slugified: Morgan Stanley and Sharesight reports
    are recognised by their exact names, and an HL contract note is matched to
    its trade by the reference its filename starts with."""
    name = os.path.basename(filename.replace("\\", "/")).strip()
    return "upload" if name in ("", ".", "..") else name


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

    tmp_dir = os.path.join(paths.TMP_DIR, f"upload_{uuid.uuid4().hex}")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, _safe_basename(file.filename))
    with open(tmp_path, "wb") as f:
        f.write(data)
    try:
        result = runner.validate_upload(account, tmp_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if result.get("needs_mapping"):
        _log.info(
            "upload %r for account %s (%s) needs a column mapping",
            file.filename,
            account_id,
            account["type"],
        )
        return jsonify(
            {
                "needs_mapping": True,
                "headers": result.get("headers", []),
                "sample": result.get("sample", []),
            }
        ), 409
    if not result.get("ok"):
        err = result.get("error") or {}
        _log.warning(
            "rejected upload %r for account %s (%s, %s bytes): %s: %s",
            file.filename,
            account_id,
            account["type"],
            len(data),
            err.get("type") if isinstance(err, dict) else "error",
            err.get("message") if isinstance(err, dict) else err,
        )
        return jsonify({"error": err}), 400

    doc = repo.create_document(
        g.user_id,
        account_id,
        # Stored under the same name the parsers will see when the document set
        # is rebuilt, so a directory broker's reports keep identifying themselves.
        _safe_basename(file.filename),
        sha,
        len(data),
        result.get("tx_count", 0),
        result.get("date_min"),
        result.get("date_max"),
        result.get("warnings", []),
    )
    if doc is None:
        _log.info("duplicate upload %r for account %s ignored", file.filename, account_id)
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


@bp.get("/api/exempt-securities")
def list_exempt_securities():
    """Securities the user has marked CGT-exempt (gilts, T-bills), by ticker or ISIN.
    Gilts and T-bills in Freetrade exports are recognised automatically; this
    list is for anything the detection cannot see."""
    return jsonify(repo.list_exempt_securities(g.user_id))


@bp.post("/api/exempt-securities")
def add_exempt_security():
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip().upper()
    if not name or len(name) > 20 or not name.replace(".", "").replace("-", "").isalnum():
        return jsonify({"error": "name must be a ticker or ISIN"}), 400
    row = repo.add_exempt_security(g.user_id, name, (body.get("note") or "").strip())
    return jsonify(row), 201


@bp.delete("/api/exempt-securities/<name>")
def delete_exempt_security(name: str):
    repo.delete_exempt_security(g.user_id, name.strip().upper())
    return jsonify({"ok": True})


@bp.post("/api/accounts/<int:account_id>/no-activity")
def add_no_activity(account_id: int):
    """User confirms an account had no transactions in [start, end] — counts as covered."""
    from datetime import date

    if not repo.get_account(g.user_id, account_id):
        return jsonify({"error": "Not found"}), 404
    body = request.get_json(force=True)
    try:
        start = date.fromisoformat(body.get("start", ""))
        end = date.fromisoformat(body.get("end", ""))
    except ValueError:
        return jsonify({"error": "start and end must be ISO dates"}), 400
    if end < start:
        return jsonify({"error": "end must be on or after start"}), 400
    row = repo.add_coverage_override(
        g.user_id, account_id, start.isoformat(), end.isoformat(), (body.get("note") or "").strip()
    )
    return jsonify(row), 201


@bp.delete("/api/no-activity/<int:override_id>")
def delete_no_activity(override_id: int):
    repo.delete_coverage_override(g.user_id, override_id)
    return jsonify({"ok": True})
