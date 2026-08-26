"""Account registry + bank column mappings."""

from flask import Blueprint, g, jsonify, request

from core import repo

bp = Blueprint("accounts", __name__, url_prefix="/api/accounts")


@bp.get("")
def list_accounts():
    return jsonify(repo.list_accounts(g.user_id))


@bp.post("")
def create_account():
    body = request.get_json(force=True)
    type_ = body.get("type")
    if type_ not in repo.ACCOUNT_TYPES:
        return jsonify({"error": f"type must be one of {repo.ACCOUNT_TYPES}"}), 400
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    account = repo.create_account(g.user_id, type_, name, body.get("first_activity_date"))
    return jsonify(account), 201


@bp.put("/<int:account_id>")
def update_account(account_id: int):
    account = repo.get_account(g.user_id, account_id)
    if not account:
        return jsonify({"error": "Not found"}), 404
    body = request.get_json(force=True)
    repo.update_account(
        g.user_id,
        account_id,
        (body.get("name") or account["name"]).strip(),
        body.get("first_activity_date", account["first_activity_date"]),
    )
    return jsonify(repo.get_account(g.user_id, account_id))


@bp.delete("/<int:account_id>")
def delete_account(account_id: int):
    if not repo.get_account(g.user_id, account_id):
        return jsonify({"error": "Not found"}), 404
    repo.delete_account(g.user_id, account_id)
    return jsonify({"ok": True})


@bp.get("/<int:account_id>/mapping")
def get_mapping(account_id: int):
    if not repo.get_account(g.user_id, account_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(repo.get_column_mapping(account_id))


@bp.put("/<int:account_id>/mapping")
def set_mapping(account_id: int):
    account = repo.get_account(g.user_id, account_id)
    if not account:
        return jsonify({"error": "Not found"}), 404
    body = request.get_json(force=True)
    for key in ("date_col", "amount_col"):
        if not body.get(key):
            return jsonify({"error": f"{key} is required"}), 400
    repo.set_column_mapping(account_id, body)
    return jsonify(body)
