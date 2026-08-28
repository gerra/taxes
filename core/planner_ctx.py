"""The picture a tax year is judged from: saved inputs, the year's constants,
the investment summary from its latest run, and the earlier years the pension
carry-forward reaches back to.

Both the planner endpoint and the status rail need exactly this, and building
it is the expensive half of either. Assembling it twice, in two places, is how
the rail would come to disagree with the page it points at.
"""

import json
from datetime import date

from core import repo, report_view, tax_profile, tax_years

# Report figures the planner may override by hand, e.g. when a broker's own tax
# statement disagrees with what its export adds up to.
OVERRIDABLE = (
    "dividends_total",
    "uk_interest",
    "foreign_interest",
    "other_income",
    "other_income_tax",
    "taxable_gain",
    "total_gain",
)

# How far back the pension carry-forward can reach from the selected year: three
# years for this year's own allowance, and three more because a prior year's own
# excess reaches three years further than the selected one.
CARRY_FORWARD_YEARS = 6


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


def invest_for(user_id: int, tax_year: int, inputs: dict) -> tuple[dict, dict | None]:
    """Investment summary for the year from its latest report run, with the
    planner's manual overrides applied. Returns (summary, bundle-or-None)."""
    run = repo.latest_ok_run(user_id, tax_year)
    bundle = json.loads(run["bundle"]) if run else None
    invest = report_view.summary_for_planner(bundle) if bundle else {}
    for key in OVERRIDABLE:
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


def build(user_id: int, tax_year: int, today: date | None = None) -> dict | None:
    """The full tips context for a year, or None if there are no constants for it."""
    year = tax_years.get_year(tax_year)
    if not year:
        return None
    inputs = repo.get_planner_inputs(user_id, tax_year) or {}
    invest, bundle = invest_for(user_id, tax_year, inputs)

    # Earlier years' saved planners feed the pension carry-forward: their income
    # drives that year's taper test, and their pension fields stand in when this
    # year's "Pension total, YYYY/YY" boxes are blank.
    prior_years = {}
    for ty in range(tax_year - CARRY_FORWARD_YEARS, tax_year):
        prior_inputs = repo.get_planner_inputs(user_id, ty)
        if prior_inputs:
            prior_years[ty] = {
                "inputs": prior_inputs,
                "invest": invest_for(user_id, ty, prior_inputs)[0],
            }

    return {
        "inputs": inputs,
        "year": year,
        "profile": tax_profile.build_profile(inputs, year, invest),
        "invest": invest,
        "bundle": bundle,
        "tax_year": tax_year,
        "prior_years": prior_years,
        "today": today or date.today(),
    }
