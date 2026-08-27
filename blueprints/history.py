"""Estimate vs. what HMRC actually charged, across every year with figures.

The point of the comparison is to catch the years where they disagree. A gap
means either the return was filed on figures this tool would not have produced
— a line left off, a credit claimed that wasn't due — or this tool is wrong.
Both are worth knowing, and neither is visible from a single year's page.
"""

import json

from flask import Blueprint, g, jsonify

from core import repo, report_view, self_assessment, tax_years

bp = Blueprint("history", __name__, url_prefix="/api/history")

# What you actually paid, typed in from the HMRC statement. There is no way to
# read it: HMRC has no API for it, and a figure derived from this app's own
# estimate would make the comparison circular.
ACTUAL_KEY = "actual_tax_paid"

# A difference smaller than this is rounding between HMRC's calculation and
# this one, not a discrepancy worth chasing.
MATCH_TOLERANCE = 1.0


def _year_row(user_id: int, tax_year: int) -> dict | None:
    year = tax_years.get_year(tax_year)
    if not year:
        return None
    inputs = repo.get_planner_inputs(user_id, tax_year) or {}
    run = repo.latest_ok_run(user_id, tax_year)
    bundle = json.loads(run["bundle"]) if run else None
    invest = report_view.summary_for_planner(bundle) if bundle else {}
    if not inputs and not bundle:
        return None

    result = self_assessment.compute_for(inputs, year, invest)
    estimate = round(float(result["sa_bill"]), 2)
    actual = inputs.get(ACTUAL_KEY)
    actual = float(actual) if actual not in (None, "") else None
    difference = round(actual - estimate, 2) if actual is not None else None

    return {
        "tax_year": tax_year,
        "label": tax_years.label(tax_year),
        "due_date": tax_years.balancing_payment_due(tax_year).isoformat(),
        "estimate": estimate,
        "investment_only": round(float(result["investment_only"]), 2),
        "employment_shortfall": round(float(result["employment_shortfall"]), 2),
        "reconciled": result["reconciled"],
        "has_report": bundle is not None,
        "actual": actual,
        "difference": difference,
        "matches": difference is not None and abs(difference) <= MATCH_TOLERANCE,
    }


@bp.get("")
def history():
    """One row per tax year with either planner inputs or a calculation run.

    `difference` is what you paid less what this tool estimates: positive means
    you paid HMRC more than these figures say was due, negative means less."""
    rows = [r for r in (_year_row(g.user_id, y) for y in tax_years.configured_years()) if r]
    compared = [r for r in rows if r["difference"] is not None]
    return jsonify(
        {
            "years": rows,
            "explain": (
                "Your estimate against what HMRC actually charged. A gap means the return was "
                "filed on different figures — income left off, a credit claimed that wasn't due, "
                "a typo in a P60 total — or that this tool has something wrong. Enter what you "
                "actually paid for each year to compare; nothing here is read from HMRC."
            ),
            "unreconciled": [r["tax_year"] for r in rows if not r["reconciled"]],
            "mismatched": [r["tax_year"] for r in compared if not r["matches"]],
        }
    )
