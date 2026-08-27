"""Planner: income inputs + computed profile + tips."""

import json
from datetime import date

from flask import Blueprint, g, jsonify, request

from core import repo, report_view, tax_profile, tax_years, tips

bp = Blueprint("planner", __name__, url_prefix="/api/planner")


@bp.get("/<int:tax_year>/inputs")
def get_inputs(tax_year: int):
    return jsonify(repo.get_planner_inputs(g.user_id, tax_year))


# One P60 per row. `pay` and `tax_deducted` are money; `tax_code` is text HMRC
# issued and is only ever used to explain a shortfall, never to compute one.
_EMPLOYMENT_MONEY = ("pay", "tax_deducted", "student_loan_deducted")
_EMPLOYMENT_TEXT = ("name", "tax_code")
# Employment rows are the only nested value the form stores; everything else is
# a scalar, and a list or dict anywhere else is a bug on the way in.
_LIST_KEYS = ("employments",)


def _clean_employments(rows) -> list[dict]:
    """Validate the P60 rows. A row that cannot be parsed is rejected outright
    rather than stored: a bad figure here moves the whole bill."""
    if not isinstance(rows, list):
        raise ValueError("employments must be a list")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each employment must be an object")
        clean: dict = {}
        for key in _EMPLOYMENT_MONEY:
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                clean[key] = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"employment {key} must be a number") from exc
        for key in _EMPLOYMENT_TEXT:
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                clean[key] = value.strip()[:64]
        if clean:
            out.append(clean)
    return out


@bp.put("/<int:tax_year>/inputs")
def set_inputs(tax_year: int):
    body = request.get_json(force=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Expected an object"}), 400
    try:
        for key in _LIST_KEYS:
            if key in body:
                body[key] = _clean_employments(body[key])
        for key, value in body.items():
            if key not in _LIST_KEYS and isinstance(value, (list, dict)):
                raise ValueError(f"{key} must be a single value")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
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
    _rebalance_dividends(invest)
    return invest, bundle


def _rebalance_dividends(invest: dict) -> None:
    """Keep the UK/foreign dividend split in step with an overridden total.

    The tax computation charges the two separately — the dividend allowance goes
    to the UK ones so the foreign tax credit is not wasted — so a total that no
    longer matches its parts would be charged on the parts and the override
    silently ignored. Split proportionally where there is a split to preserve,
    otherwise treat it all as UK dividends, which claims no foreign credit."""
    total = invest.get("dividends_total")
    if total is None:
        return
    uk = float(invest.get("uk_dividends") or 0)
    foreign = float(invest.get("foreign_dividends") or 0)
    parts = uk + foreign
    total = float(total)
    if abs(parts - total) < 0.005:
        return
    if parts > 0:
        share = total / parts
        invest["uk_dividends"] = round(uk * share, 2)
        invest["foreign_dividends"] = round(total - uk * share, 2)
    else:
        invest["uk_dividends"] = round(total, 2)
        invest["foreign_dividends"] = 0.0


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
                    "pa_taper_end",
                    "basic_band",
                    "higher_rate_limit",
                    "cgt_allowance",
                    "dividend_allowance",
                    "income_rates",
                    "dividend_rates",
                    "cgt_rates_shares",
                )
                if k in year
            },
            # The whole parameter table for the year, grouped and sourced, so it
            # can be checked against gov.uk in the UI rather than in the source.
            "year_parameters": tax_years.parameters(tax_year),
        }
    )
