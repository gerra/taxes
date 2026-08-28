"""Planner: income inputs + computed profile + tips."""

from flask import Blueprint, g, jsonify, request

from core import planner_ctx, repo, tax_years, tips

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


@bp.get("/<int:tax_year>")
def planner(tax_year: int):
    ctx = planner_ctx.build(g.user_id, tax_year)
    if ctx is None:
        return jsonify({"error": f"No tax constants for {tax_year}"}), 400
    year = ctx["year"]
    return jsonify(
        {
            "tax_year": tax_year,
            "label": tax_years.label(tax_year),
            "has_report": ctx["bundle"] is not None,
            "invest": ctx["invest"],
            "profile": ctx["profile"],
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
