"""Calculation runs: trigger, poll, fetch PDF."""

import json

from flask import Blueprint, g, jsonify, request, send_file

from core import repo
from engine import runner

bp = Blueprint("calc", __name__, url_prefix="/api/calc")


def _run_json(run: dict) -> dict:
    out = {
        "id": run["id"],
        "tax_year": run["tax_year"],
        "status": run["status"],
        "created_at": run["created_at"],
        "finished_at": run["finished_at"],
        "has_pdf": bool(run["pdf_path"]),
    }
    if run["error"]:
        out["error"] = json.loads(run["error"])
    return out


@bp.post("/run")
def run():
    body = request.get_json(force=True)
    tax_year = int(body["year"])
    force = bool(body.get("force"))
    # Waiving the cash-balance check is deliberate and per-run; it never sticks.
    balance_check = body.get("balance_check", True) is not False
    run_row = runner.run_calculation(g.user_id, tax_year, force=force, balance_check=balance_check)
    return jsonify(_run_json(run_row))


@bp.get("/runs/<int:run_id>")
def get_run(run_id: int):
    run_row = repo.get_calc_run(g.user_id, run_id)
    if not run_row:
        return jsonify({"error": "Not found"}), 404
    out = _run_json(run_row)
    if run_row["status"] == "ok" and request.args.get("bundle") == "1":
        out["bundle"] = json.loads(run_row["bundle"])
    return jsonify(out)


@bp.get("/runs/<int:run_id>/pdf")
def get_pdf(run_id: int):
    run_row = repo.get_calc_run(g.user_id, run_id)
    if not run_row or not run_row["pdf_path"]:
        return jsonify({"error": "Not found"}), 404
    return send_file(
        run_row["pdf_path"],
        as_attachment=True,
        download_name=f"capital-gains-{run_row['tax_year']}.pdf",
    )
