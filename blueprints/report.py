"""Tax-year report: view model (cards, SA boxes, explanations) from the latest
successful calc run, plus the raw bundle for drill-downs."""

import json

from flask import Blueprint, g, jsonify

from core import coverage, repo, report_view, tax_profile, tax_years

bp = Blueprint("report", __name__, url_prefix="/api/report")


def _profile_or_none(user_id: int, tax_year: int, bundle: dict) -> dict | None:
    inputs = repo.get_planner_inputs(user_id, tax_year)
    year = tax_years.get_year(tax_year)
    if not inputs or not year:
        return None
    return tax_profile.build_profile(inputs, year, report_view.summary_for_planner(bundle))


@bp.get("/<int:tax_year>")
def report(tax_year: int):
    run = repo.latest_ok_run(g.user_id, tax_year)
    if not run:
        return jsonify({"status": "no_run"}), 404
    bundle = json.loads(run["bundle"])
    profile = _profile_or_none(g.user_id, tax_year, bundle)
    view = report_view.build_view(bundle, tax_year, profile)
    checklist = coverage.checklist(g.user_id, tax_year)
    return jsonify(
        {
            "status": "ok",
            "run_id": run["id"],
            "has_pdf": bool(run["pdf_path"]),
            "provisional": checklist["overall"] != "ok",
            "coverage_overall": checklist["overall"],
            "view": view,
            "bundle": bundle,
        }
    )


@bp.get("/<int:tax_year>/summary")
def summary(tax_year: int):
    run = repo.latest_ok_run(g.user_id, tax_year)
    if not run:
        return jsonify(None)
    return jsonify(report_view.summary_for_planner(json.loads(run["bundle"])))
