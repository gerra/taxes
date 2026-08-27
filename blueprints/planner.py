"""Planner: income inputs + computed profile + tips."""

import json
from datetime import date

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


def _invest_for(user_id: int, tax_year: int, inputs: dict) -> tuple[dict, dict | None]:
    """Investment summary for the year from its latest report run, with the
    planner's manual overrides applied. Returns (summary, bundle-or-None)."""
    run = repo.latest_ok_run(user_id, tax_year)
    bundle = json.loads(run["bundle"]) if run else None
    invest = report_view.summary_for_planner(bundle) if bundle else {}
    for key in (
        "dividends_total",
        "uk_interest",
        "foreign_interest",
        "other_income",
        "other_income_tax",
        "taxable_gain",
        "total_gain",
    ):
        if inputs.get(f"override_{key}") not in (None, ""):
            invest[key] = float(inputs[f"override_{key}"])
    # A typed-in gain figure replaces the report's disposals outright — keeping
    # them would silently win over the override when the tax is computed.
    if inputs.get("override_taxable_gain") not in (None, "") or inputs.get(
        "override_total_gain"
    ) not in (None, ""):
        invest.pop("disposals", None)
    return invest, bundle


@bp.get("/<int:tax_year>")
def planner(tax_year: int):
    year = tax_years.get_year(tax_year)
    if not year:
        return jsonify({"error": f"No tax constants for {tax_year}"}), 400
    inputs = repo.get_planner_inputs(g.user_id, tax_year) or {}
    invest, bundle = _invest_for(g.user_id, tax_year, inputs)

    # Earlier years' saved planners feed the pension carry-forward: their income
    # drives that year's taper test, and their pension fields stand in when this
    # year's "Pension total, YYYY/YY" boxes are blank. Six years back, because a
    # prior year's own excess reaches three years further than the selected one.
    prior_years = {}
    for ty in range(tax_year - 6, tax_year):
        prior_inputs = repo.get_planner_inputs(g.user_id, ty)
        if prior_inputs:
            prior_years[ty] = {
                "inputs": prior_inputs,
                "invest": _invest_for(g.user_id, ty, prior_inputs)[0],
            }

    profile = tax_profile.build_profile(inputs, year, invest)
    ctx = {
        "inputs": inputs,
        "year": year,
        "profile": profile,
        "invest": invest,
        "bundle": bundle,
        "tax_year": tax_year,
        "prior_years": prior_years,
        "today": date.today(),
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
            "year": {
                k: year[k]
                for k in (
                    "cgt_mid_year_change",
                    "personal_allowance",
                    "pa_taper_start",
                    "basic_band",
                    "additional_threshold",
                    "cgt_allowance",
                    "dividend_allowance",
                    "income_rates",
                    "dividend_rates",
                    "cgt_rates_shares",
                )
                if k in year
            },
        }
    )
