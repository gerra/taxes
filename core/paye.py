"""PAYE: what the employer collected, and why it was not the right amount.

PAYE is an estimate. It works from a tax code issued before the year starts, so
a code carrying an allowance you turn out not to be entitled to — or a benefit
that never got coded — leaves a shortfall that lands on the Self Assessment
bill. That shortfall is most of what a high earner's return actually collects,
and until now this app assumed it away.

Two jobs live here, and the split between them matters:

1. **Aggregating the P60s.** Pay and tax deducted are read off the P60s and
   summed, full stop. `tax_deducted` is never derived, inferred or reconciled —
   it is what the employer told HMRC it took, and it is the figure the return
   is filled in from. Everything else in this module is commentary on it.
2. **Explaining the gap.** Given the final tax code, PAYE is re-run with the
   allowance that code grants. If the result matches the P60, the code explains
   the shortfall completely and the message says so. If it does not, the code is
   not the (whole) explanation and the likely causes are listed instead. This is
   diagnostic only: it never feeds a figure into the bill.

Tax codes are decoded per HMRC's "Tax codes" guidance and the PAYE manual
(PAYE11000 onwards): a numeric code is the allowance divided by ten with the
last digit dropped, so the allowance is number x 10 + 9; K prefixes carry
negative allowances (added to pay rather than deducted); BR/D0/D1 charge every
pound at one rate with no allowance at all.
"""

from __future__ import annotations

import re
from decimal import Decimal

from core import estimator
from core.estimator import ZERO, dec

# A "tax deducted" figure this far from what the tax code implies is worth
# querying: within a pound or two it is rounding inside the payroll, beyond
# this it is usually a typo or something the code does not account for.
TAX_CODE_MISMATCH_TOLERANCE = Decimal(25)

# How close the re-run has to land for the code to be called a full explanation.
# Payroll rounds each pay period, so a year's worth of rounding drifts by a
# pound or two even when nothing is wrong.
TAX_CODE_MATCH_TOLERANCE = Decimal(2)

# Flat-rate codes: every pound of this employment's pay at one rate, no
# allowance. D2/D3 are Scottish-only and deliberately absent — see below.
FLAT_RATE_CODES = {
    "BR": ("basic", "every pound taxed at the basic rate"),
    "D0": ("higher", "every pound taxed at the higher rate"),
    "D1": ("additional", "every pound taxed at the additional rate"),
}

# A code is an optional country prefix, an optional K, the number, an optional
# suffix letter, and an optional non-cumulative marker — which can follow the
# suffix ("1257L M1") or stand in its place ("1257 X").
_CODE_RE = re.compile(
    r"^(?P<country>[SC])?(?P<k>K)?(?P<number>\d{1,6})(?P<suffix>[LMNTY])?(?P<noncum>W1|M1|X)?$"
)


class TaxCode:
    """A decoded PAYE tax code.

    `allowance` is the pay the code lets through untaxed, negative for a K code
    (which adds to taxable pay instead of sheltering it). `flat_rate` is set
    instead for BR/D0/D1. `usable` is False when the code can be read but not
    used to re-run PAYE — a Scottish code, or a non-cumulative (week 1 /
    month 1) one, where each pay period was taxed on its own rather than
    against the year to date."""

    def __init__(
        self,
        raw: str,
        *,
        allowance: Decimal | None = None,
        flat_rate: str | None = None,
        no_tax: bool = False,
        cumulative: bool = True,
        scottish: bool = False,
        welsh: bool = False,
        describe: str = "",
        problem: str | None = None,
    ):
        self.raw = raw
        self.allowance = allowance
        self.flat_rate = flat_rate
        self.no_tax = no_tax
        self.cumulative = cumulative
        self.scottish = scottish
        self.welsh = welsh
        self.describe = describe
        self.problem = problem

    @property
    def usable(self) -> bool:
        return self.problem is None

    def as_dict(self) -> dict:
        return {
            "code": self.raw,
            "allowance": str(self.allowance) if self.allowance is not None else None,
            "flat_rate": self.flat_rate,
            "no_tax": self.no_tax,
            "cumulative": self.cumulative,
            "scottish": self.scottish,
            "welsh": self.welsh,
            "describe": self.describe,
            "usable": self.usable,
            "problem": self.problem,
        }


def decode_tax_code(code: str | None) -> TaxCode | None:
    """Decode a P60 tax code, or None if there isn't one to decode.

    The numeric part is the allowance with its last digit dropped, so 151 means
    an allowance somewhere in £1,510–£1,519 and HMRC's own tables use the top of
    that range: 151 -> £1,519. A K prefix inverts it — K151 adds £1,519 to
    taxable pay rather than sheltering it."""
    raw = (code or "").strip().upper().replace(" ", "")
    if not raw:
        return None

    if raw == "NT":
        return TaxCode(raw, no_tax=True, describe="NT: no tax deducted from this employment at all")
    if raw in FLAT_RATE_CODES:
        band, describe = FLAT_RATE_CODES[raw]
        return TaxCode(
            raw, flat_rate=band, describe=f"{raw}: {describe}, with no personal allowance"
        )
    if raw in ("0T", "S0T", "C0T"):
        return TaxCode(
            raw,
            allowance=ZERO,
            scottish=raw.startswith("S"),
            welsh=raw.startswith("C"),
            describe=f"{raw}: no personal allowance, but the normal bands still apply",
            problem=(
                "Scottish tax codes are not modelled — the bands differ."
                if raw.startswith("S")
                else None
            ),
        )

    match = _CODE_RE.match(raw)
    if not match:
        return TaxCode(
            raw,
            describe=f"{raw}: not a tax code this app recognises",
            problem=f"Could not read the tax code {raw!r}, so it can't explain the shortfall.",
        )

    country = match.group("country")
    is_k = bool(match.group("k"))
    number = int(match.group("number"))
    cumulative = not match.group("noncum")
    # HMRC's own tables read the code as the top of the £10 band it names.
    amount = Decimal(number * 10 + 9)
    allowance = -amount if is_k else amount

    if is_k:
        describe = (
            f"{raw}: a K code, which adds £{amount:,.0f} to your taxable pay instead of "
            "sheltering any of it — usually untaxed benefits or an old underpayment being "
            "collected through the code"
        )
    else:
        describe = f"{raw}: gives you £{amount:,.0f} of tax-free pay over the year"

    problem = None
    if country == "S":
        problem = (
            f"{raw} is a Scottish tax code. Scottish income tax has its own five bands, "
            "which this app does not model, so PAYE can't be re-run to check it."
        )
    elif not cumulative:
        problem = (
            f"{raw} is a non-cumulative (week 1 / month 1) code: each pay period was taxed "
            "on its own rather than against the year to date, so a cumulative re-run won't "
            "match the P60 even when nothing is wrong."
        )

    return TaxCode(
        raw,
        allowance=allowance,
        cumulative=cumulative,
        scottish=country == "S",
        welsh=country == "C",
        describe=describe,
        problem=problem,
    )


def paye_tax(pay: Decimal, code: TaxCode, year: dict) -> Decimal:
    """What PAYE would collect on `pay` under `code`, on a cumulative basis.

    This is the diagnostic re-run, never a source of a figure on the return. It
    assumes one employment taxed to the year end, which is what a P60 with a
    cumulative code represents."""
    pay = dec(pay)
    if code.no_tax:
        return ZERO
    if code.flat_rate:
        return pay * dec(year["income_rates"][code.flat_rate])
    allowance = code.allowance if code.allowance is not None else ZERO
    # A K code's negative allowance is added to taxable pay, not subtracted.
    # Payroll works in whole pounds of taxable pay, so the re-run does too —
    # always, whatever rounding mode the report is showing, because the point is
    # to reproduce what the employer's payroll actually did.
    taxable = estimator.round_gain_down(max(ZERO, pay - allowance))
    slices, _ = estimator.band_slices(
        taxable,
        ZERO,
        basic_limit=dec(year["basic_band"]),
        higher_limit=dec(year["higher_rate_limit"]),
        rates=year["income_rates"],
    )
    return estimator.slices_tax(slices)


def employments_total(employments: list[dict]) -> dict:
    """Sum the P60s. `pay` and `tax_deducted` come off the forms unchanged.

    Guardrail: `tax_deducted` is only ever read from here. Nothing in this app
    derives it from a tax code, because a tax code is what HMRC *asked* the
    employer to take and the P60 is what the employer actually took — the whole
    point of the reconciliation is the difference between the two."""
    pay = ZERO
    tax = ZERO
    student_loan = ZERO
    rows = []
    for e in employments:
        row_pay = dec(e.get("pay"))
        row_tax = dec(e.get("tax_deducted"))
        row_sl = dec(e.get("student_loan_deducted"))
        pay += row_pay
        tax += row_tax
        student_loan += row_sl
        rows.append(
            {
                "name": e.get("name") or "Employment",
                "pay": row_pay,
                "tax_deducted": row_tax,
                "student_loan_deducted": row_sl,
                "tax_code": (e.get("tax_code") or "").strip().upper() or None,
            }
        )
    return {
        "rows": rows,
        "pay": pay,
        "tax_deducted": tax,
        "student_loan_deducted": student_loan,
        "count": len(rows),
    }


def explain_shortfall(
    *,
    employments: list[dict],
    benefits: Decimal,
    shortfall: Decimal,
    year: dict,
) -> dict | None:
    """Whether the final tax code accounts for the PAYE shortfall.

    Only attempted for a single employment with a usable cumulative code: with
    two employments the codes split an allowance between them and neither can be
    re-run on its own, and a non-cumulative code never reconciles.

    Returns None when there is no code to work from. Otherwise a dict with the
    message, the code-implied tax, and whether it explains the gap."""
    totals = employments_total(employments)
    rows = totals["rows"]
    coded = [r for r in rows if r["tax_code"]]
    if not coded:
        return None

    benefits = dec(benefits)
    shortfall = dec(shortfall)
    code = decode_tax_code(coded[0]["tax_code"])
    if code is None:
        return None

    if totals["count"] > 1:
        return {
            "code": code.as_dict(),
            "implied_tax": None,
            "explains": False,
            "message": (
                f"You have {totals['count']} PAYE employments, so no single tax code can be "
                "re-run against a single P60: HMRC splits your allowance between them and "
                f"each code only covers its own pay. The shortfall of £{shortfall:,.2f} is "
                "still real — it comes from the P60 figures — but the usual cause with more "
                "than one employment is that the second job's code assumed a band it did not "
                "end up in. Check each P60 against its own code."
            ),
        }

    if not code.usable:
        return {
            "code": code.as_dict(),
            "implied_tax": None,
            "explains": False,
            "message": f"{code.problem} The shortfall of £{shortfall:,.2f} still stands: it comes "
            "from the P60 pay and tax deducted, not from the code.",
        }

    # Benefits in kind are taxed through the code when they are coded, so the
    # fairer comparison charges the code's allowance against pay plus benefits.
    coded_pay = dec(rows[0]["pay"]) + benefits
    implied = paye_tax(coded_pay, code, year)
    actual = dec(rows[0]["tax_deducted"])
    gap = actual - implied
    explains = abs(gap) <= TAX_CODE_MATCH_TOLERANCE

    allowance = code.allowance if code.allowance is not None else ZERO
    if explains and shortfall > ZERO:
        message = (
            f"Your PAYE shortfall of £{shortfall:,.2f} is fully explained by tax code "
            f"{code.raw} giving you £{abs(allowance):,.0f} of personal allowance you "
            "weren't entitled to. Re-running PAYE with that allowance gives "
            f"£{implied:,.2f}, which is what your P60 says was deducted. The allowance "
            "tapers away £1 for every £2 of income over "
            f"£{dec(year['pa_taper_start']):,.0f} and is nil from "
            f"£{dec(year['additional_threshold']):,.0f}, so the code was out of date the "
            "moment your pay passed that point."
        )
    elif explains:
        message = (
            f"Tax code {code.raw} implies £{implied:,.2f} of PAYE, which matches your P60. "
            "The code and the deduction agree, so nothing about this employment is "
            "unexplained."
        )
    else:
        direction = "more" if gap > ZERO else "less"
        message = (
            f"Tax code {code.raw} implies £{implied:,.2f} of PAYE, but your P60 says "
            f"£{actual:,.2f} was deducted — £{abs(gap):,.2f} {direction}. The code does not "
            "explain the difference on its own. The usual causes are benefits in kind that "
            "were never coded, a code that changed part-way through the year (the P60 shows "
            "only the final one), a bonus month that pushed a period into a higher band, or "
            "a second job taxed under its own code. Whichever it is, the shortfall itself "
            "comes from the P60 figures and is unaffected."
        )

    return {
        "code": code.as_dict(),
        "implied_tax": implied,
        "actual_tax": actual,
        "gap": gap,
        "explains": explains,
        "message": message,
    }


def tax_deducted_warning(*, employments: list[dict], benefits: Decimal, year: dict) -> str | None:
    """The typo guard: a "tax deducted" a long way from what the code implies.

    A single digit typed wrong in a six-figure PAYE total moves the bill by the
    same amount and nothing else on the return contradicts it, so the code is
    the only cross-check available."""
    totals = employments_total(employments)
    if totals["count"] != 1 or not totals["rows"][0]["tax_code"]:
        return None
    code = decode_tax_code(totals["rows"][0]["tax_code"])
    if code is None or not code.usable:
        return None
    implied = paye_tax(dec(totals["rows"][0]["pay"]) + dec(benefits), code, year)
    actual = dec(totals["rows"][0]["tax_deducted"])
    gap = actual - implied
    if abs(gap) <= TAX_CODE_MISMATCH_TOLERANCE:
        return None
    return (
        f"Check the tax deducted: you entered £{actual:,.2f}, but tax code {code.raw} on "
        f"£{dec(totals['rows'][0]['pay']):,.2f} of pay implies £{implied:,.2f} — a difference of "
        f"£{abs(gap):,.2f}. Every penny of that difference goes straight onto your bill, so "
        "check the figure against the P60 before filing. If the P60 really does say "
        f"£{actual:,.2f}, the code isn't the whole story: benefits in kind, a mid-year code "
        "change or a second employment would all do this."
    )
