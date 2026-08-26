"""Planner: income inputs + computed profile + tips."""

import json

from flask import Blueprint, g, jsonify, request

from core import repo, report_view, tax_profile, tax_years, tips

bp = Blueprint("planner", __name__, url_prefix="/api/planner")


@bp.get("/<int:tax_year>/inputs")
def get_inputs(tax_year: int):
    return jsonify(repo.get_planner_inputs(g.user_id, tax_year))


@bp.put("/<int:tax_year>/inputs")
def set_inputs(tax_year: int):
    body = request.get_json(force=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Expected an object"}), 400
    repo.set_planner_inputs(g.user_id, tax_year, body)
    return jsonify(body)


@bp.get("/<int:tax_year>")
def planner(tax_year: int):
    year = tax_years.get_year(tax_year)
    if not year:
        return jsonify({"error": f"No tax constants for {tax_year}"}), 400
    inputs = repo.get_planner_inputs(g.user_id, tax_year) or {}

    run = repo.latest_ok_run(g.user_id, tax_year)
    bundle = json.loads(run["bundle"]) if run else None
    invest = report_view.summary_for_planner(bundle) if bundle else {}
    # Manual overrides win over report-derived figures
    for key in ("dividends_total", "uk_interest", "foreign_interest", "taxable_gain", "total_gain"):
        if inputs.get(f"override_{key}") not in (None, ""):
            invest[key] = float(inputs[f"override_{key}"])

    profile = tax_profile.build_profile(inputs, year, invest)
    ctx = {
        "inputs": inputs,
        "year": year,
        "profile": profile,
        "invest": invest,
        "bundle": bundle,
        "tax_year": tax_year,
    }
    return jsonify(
        {
            "tax_year": tax_year,
            "label": tax_years.label(tax_year),
            "has_report": bundle is not None,
            "invest": invest,
            "profile": profile,
            "tips": tips.build_tips(ctx),
            "filing_deadline": tax_years.filing_deadline(tax_year).isoformat(),
        }
    )
