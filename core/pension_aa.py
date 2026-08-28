"""Pension annual allowance: per-year tapered allowance and carry-forward.

Pure functions over Decimal money (pence precision). Rules implemented:

- FA 2004 s228: standard annual allowance per tax year (`tax_years.pension_rules`).
- s228ZA: taper for "high-income individuals" — applies only when threshold
  income exceeds the threshold limit AND adjusted income exceeds the adjusted
  limit; the reduction is half the excess over the adjusted limit, rounded
  down to a whole £, and the allowance never drops below that year's floor.
    threshold income = net income + salary sacrificed for pension (post-8 Jul
      2015 arrangements) − gross relief-at-source personal contributions
    adjusted income  = net income + employer and net-pay/sacrifice contributions
      (RAS contributions are already inside net income, so they're not re-added)
- s228A: unused allowance carries forward from the three previous tax years,
  used oldest-first after the current year's own allowance, and only from years
  the individual was a member of a registered pension scheme.
- s227: an excess not covered by carry-forward is charged at marginal rates.

`compute` replays every known year in date order so a prior year's own excess
consumes the carry-forward that was available to IT, leaving less for later
years — exactly as HMRC's calculator does."""

from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from core import tax_years

ZERO = Decimal("0.00")
PENNY = Decimal("0.01")


def money(x) -> Decimal:
    """Decimal pence from a float/int/str/Decimal (floats via their repr, so
    7067.47 stays 7067.47)."""
    return Decimal(str(x)).quantize(PENNY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PensionYear:
    tax_year: int
    pension_input: Decimal | None  # total pension input amount; None = not entered
    net_income: Decimal | None  # None = not entered → taper can't be checked
    sacrifice: Decimal = ZERO  # pay sacrificed for pension (added back to threshold income)
    ras_gross: Decimal = ZERO  # relief-at-source personal contributions, gross
    member: bool = True  # member of a registered scheme this year (else no carry-forward)


def allowance_for(
    tax_year: int,
    net_income: Decimal | None,
    pension_input: Decimal,
    sacrifice: Decimal = ZERO,
    ras_gross: Decimal = ZERO,
) -> dict | None:
    """The year's annual allowance after taper, with the workings.

    Returns None for years with no rules. With unknown income the standard
    allowance is returned and ``verified`` is False."""
    rules = tax_years.pension_rules(tax_year)
    if rules is None:
        return None
    standard = money(rules["aa"])
    out = {
        "tax_year": tax_year,
        "standard": standard,
        "allowance": standard,
        "floor": money(rules["aa_min"]),
        "threshold_limit": money(rules["threshold_income"]),
        "adjusted_limit": money(rules["adjusted_income"]),
        "threshold_income": None,
        "adjusted_income": None,
        "tapered": False,
        "reduction": ZERO,
        "verified": net_income is not None,
    }
    if net_income is None:
        return out
    threshold = net_income + sacrifice - ras_gross
    adjusted = net_income + pension_input - ras_gross
    out["threshold_income"] = threshold
    out["adjusted_income"] = adjusted
    if threshold > out["threshold_limit"] and adjusted > out["adjusted_limit"]:
        reduction = ((adjusted - out["adjusted_limit"]) / 2).to_integral_value(rounding=ROUND_FLOOR)
        out["tapered"] = True
        out["reduction"] = reduction
        out["allowance"] = max(out["floor"], standard - reduction)
    return out


def _consume(excess: Decimal, tax_year: int, available: dict[int, Decimal]) -> tuple[dict, Decimal]:
    """Cover ``excess`` from the three prior years' remaining allowance, oldest
    first. Mutates ``available``; returns (consumed-by-year, uncovered excess)."""
    consumed = {}
    for src in (tax_year - 3, tax_year - 2, tax_year - 1):
        if excess <= 0:
            break
        room = available.get(src, ZERO)
        take = min(room, excess)
        if take > 0:
            available[src] = room - take
            consumed[src] = take
            excess -= take
    return consumed, excess


def compute(selected_year: int, years: list[PensionYear]) -> dict:
    """Carry-forward position for ``selected_year`` given every known year.

    Years without a pension input are ignored (they contribute no allowance
    and consume none). Prior years' own excesses are settled in order, so what
    reaches the selected year is what actually remains."""
    by_year = {y.tax_year: y for y in years}
    selected = by_year.get(selected_year) or PensionYear(selected_year, ZERO, None)
    results: dict[int, dict] = {}
    available: dict[int, Decimal] = {}  # remaining unused allowance, by year

    def settle(py: PensionYear) -> dict | None:
        if py.pension_input is None:
            return None
        a = allowance_for(py.tax_year, py.net_income, py.pension_input, py.sacrifice, py.ras_gross)
        if a is None:
            return None
        used = py.pension_input
        r = {
            **a,
            "pension_input": used,
            "member": py.member,
            "unused": max(ZERO, a["allowance"] - used),
            "excess": max(ZERO, used - a["allowance"]),
            "consumed": {},
            "charge": ZERO,
        }
        if r["excess"] > 0:
            r["consumed"], r["charge"] = _consume(r["excess"], py.tax_year, available)
        available[py.tax_year] = r["unused"] if py.member else ZERO
        results[py.tax_year] = r
        return r

    # Prior years first, oldest to newest. Anything older than 6 years back can't
    # affect the selected year (its carry-forward would have expired).
    for ty in range(selected_year - 6, selected_year):
        py = by_year.get(ty)
        if py is not None:
            settle(py)

    window = [
        ty for ty in (selected_year - 3, selected_year - 2, selected_year - 1) if ty in results
    ]
    carry_available = {ty: available[ty] for ty in window}
    carry_total = sum(carry_available.values(), ZERO)
    unverified_total = sum(
        (v for ty, v in carry_available.items() if not results[ty]["verified"]), ZERO
    )

    sel = settle(selected)
    assert sel is not None, "selected year must have pension rules"
    headroom = sel["allowance"] - sel["pension_input"] + carry_total

    next_window = (selected_year - 2, selected_year - 1, selected_year)
    carry_next = {ty: available[ty] for ty in next_window if ty in results}
    expired = available.get(selected_year - 3, ZERO)

    warnings = []
    # The selected year's own allowance is the biggest number in the tip. Without
    # an income figure the taper can't be tested, so it is the standard allowance
    # by assumption — say so, or a tapered year reads as having ~50k more room
    # than it has.
    if not sel["verified"]:
        warnings.append(
            f"{tax_years.label(selected_year)}: no income entered in its Planner, so the "
            f"£{sel['standard']:,.2f} allowance is assumed untapered — the headroom is an "
            "upper bound, and a taper would cut it"
        )
    for ty in (selected_year - 3, selected_year - 2, selected_year - 1):
        label = tax_years.label(ty)
        r = results.get(ty)
        if r is None:
            if tax_years.pension_rules(ty) is not None:
                warnings.append(
                    f"{label}: no pension figure entered — no carry-forward counted for it"
                )
        elif not r["member"]:
            warnings.append(
                f"{label}: no contributions, so treated as not a scheme member — "
                "nothing carried forward from it"
            )
        elif not r["verified"]:
            warnings.append(
                f"{label}: no income entered in its Planner, so the £{r['standard']:,.2f} "
                f"allowance is assumed untapered — its £{carry_available[ty]:,.2f} "
                "carry-forward is unverified"
            )
    for ty, r in results.items():
        if ty != selected_year and r["charge"] > 0:
            warnings.append(
                f"{tax_years.label(ty)}: £{r['charge']:,.2f} over the allowance was not covered "
                "by carry-forward — an annual allowance charge should have been declared "
                "for that year"
            )

    return {
        "selected": sel,
        "years": results,
        "carry_available": carry_available,
        "carry_total": carry_total,
        "unverified_total": unverified_total,
        "headroom": headroom,
        "charge": sel["charge"],
        "carry_next": carry_next,
        "carry_next_total": sum(carry_next.values(), ZERO),
        "expired": expired,
        "warnings": warnings,
    }
