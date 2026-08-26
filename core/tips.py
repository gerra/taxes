"""Tip catalogue: each tip is a pure function (ctx) -> tip dict | None.

ctx = {inputs, year (tax_years constants), profile (tax_profile.build_profile),
invest (report summary), bundle (full ReportBundle or None), tax_year,
prior_years ({tax_year: {inputs, invest}} for earlier saved planners),
today (date; lets tests pin the open/closed-year branch)}.

Every tip states its assumptions; the UI renders a disclaimer that these are
computed hints, not advice. ``detail`` is the "how it was computed" block the
UI shows on expand; ``warnings`` are gaps in the inputs the figure relies on."""

from datetime import date
from decimal import Decimal

from core import pension_aa, tax_profile, tax_years
from core.pension_aa import ZERO, PensionYear, money


def _tip(
    id_, title, what, why, win, deadline=None, confidence="medium", detail=None, warnings=None
):
    return {
        "id": id_,
        "title": title,
        "what_to_do": what,
        "why": why,
        "estimated_win_gbp": round(win, 0) if win is not None else None,
        "deadline": deadline,
        "confidence": confidence,
        "detail": detail,
        "warnings": warnings or [],
    }


def _gbp(d) -> str:
    return f"£{d:,.2f}"


# ── Pension annual allowance ───────────────────────────────────────────────────


def _ras_gross(inputs: dict) -> Decimal:
    """Gross relief-at-source contribution: HMRC adds 25% to the net SIPP payment."""
    return money(money(inputs.get("sipp_paid") or 0) / Decimal("0.8"))


def _pension_input_from(inputs: dict) -> Decimal | None:
    """Total pension input amount from a year's own planner fields, or None if
    none of them were entered. "Pension via payroll — yours" is salary sacrifice
    for this user, so it is an employer contribution for allowance purposes."""
    keys = ("pension_employee", "pension_employer", "sipp_paid")
    if all(inputs.get(k) is None for k in keys):
        return None
    employee = money(inputs.get("pension_employee") or 0)
    employer = money(inputs.get("pension_employer") or 0)
    return employee + employer + _ras_gross(inputs)


def _pension_years(ctx) -> list[PensionYear]:
    """Selected year from its inputs + profile; prior years from this year's
    "Pension total, YYYY/YY" boxes (explicit) or, failing that, the prior year's
    own saved planner. Income for prior years only ever comes from their own
    planner — without it the taper can't be checked and the year is unverified.
    Scheme membership is inferred from a non-zero pension input."""
    sel, inputs = ctx["tax_year"], ctx["inputs"]
    prior_years = ctx.get("prior_years") or {}
    own_input = _pension_input_from(inputs) or ZERO
    years = [
        PensionYear(
            sel,
            own_input,
            money(ctx["profile"]["income"]["total"]),
            sacrifice=money(inputs.get("pension_employee") or 0),
            ras_gross=_ras_gross(inputs),
            member=own_input > 0,
        )
    ]
    for back in range(1, 7):
        ty = sel - back
        prior = prior_years.get(ty) or {}
        own = prior.get("inputs") or {}
        explicit = inputs.get(f"pension_prior_{back}") if back <= 3 else None
        total = money(explicit) if explicit is not None else _pension_input_from(own)
        if total is None:
            continue
        net = None
        if own.get("employment_income") is not None:
            net = money(tax_profile.total_income(own, prior.get("invest") or {}))
        years.append(
            PensionYear(
                ty,
                total,
                net,
                sacrifice=money(own.get("pension_employee") or 0),
                ras_gross=_ras_gross(own),
                member=total > 0,
            )
        )
    return years


def _allowance_note(r: dict) -> str:
    if not r["verified"]:
        return "income not entered — untapered allowance assumed"
    if r["tapered"]:
        over = r["adjusted_income"] - r["adjusted_limit"]
        note = (
            f"tapered: adjusted income {_gbp(r['adjusted_income'])} is {_gbp(over)} over "
            f"{_gbp(r['adjusted_limit'])} → −£{r['reduction']:,.0f}"
        )
        if r["standard"] - r["reduction"] < r["floor"]:
            note += f", held at the {_gbp(r['floor'])} floor"
        return note
    if r["threshold_income"] <= r["threshold_limit"]:
        return (
            f"threshold income {_gbp(r['threshold_income'])} ≤ {_gbp(r['threshold_limit'])} "
            "— no taper"
        )
    return f"adjusted income {_gbp(r['adjusted_income'])} ≤ {_gbp(r['adjusted_limit'])} — no taper"


def _pension_detail(res: dict, sel_year: int) -> str:
    """The workings, one line per step, for the tip's expandable detail."""
    label = tax_years.label
    s = res["selected"]
    lines = [
        f"Annual allowance {label(sel_year)}: {_gbp(s['allowance'])} "
        f"(standard {_gbp(s['standard'])}; {_allowance_note(s)})",
        f"Pension input {label(sel_year)}: {_gbp(s['pension_input'])} → "
        + (f"{_gbp(s['unused'])} unused" if s["excess"] == 0 else f"{_gbp(s['excess'])} over"),
        "Carry-forward from earlier years (oldest used first):",
    ]
    for ty in (sel_year - 3, sel_year - 2, sel_year - 1):
        r = res["years"].get(ty)
        if r is None:
            lines.append(f"  {label(ty)}: no figure entered")
            continue
        if r["excess"] > 0:
            line = (
                f"  {label(ty)}: input {_gbp(r['pension_input'])} is {_gbp(r['excess'])} over "
                f"its {_gbp(r['allowance'])} allowance ({_allowance_note(r)})"
            )
            if r["consumed"]:
                line += " — covered by " + ", ".join(
                    f"{_gbp(a)} from {label(y)}" for y, a in r["consumed"].items()
                )
            if r["charge"] > 0:
                line += f"; {_gbp(r['charge'])} uncovered"
        else:
            line = (
                f"  {label(ty)}: {_gbp(r['unused'])} unused of {_gbp(r['allowance'])} "
                f"({_allowance_note(r)})"
            )
        eaten = sum(
            (rr["consumed"].get(ty, ZERO) for y, rr in res["years"].items() if y != sel_year),
            ZERO,
        )
        if eaten > 0:
            line += f" − {_gbp(eaten)} used by a later year's excess"
        if not r["member"]:
            line += " — not a scheme member, nothing carried"
        lines.append(line + f" → {_gbp(res['carry_available'][ty])} available")
    lines.append(
        f"Headroom = {_gbp(s['allowance'])} − {_gbp(s['pension_input'])} + "
        f"{_gbp(res['carry_total'])} = {_gbp(res['headroom'])}"
    )
    if res["unverified_total"] > 0:
        lines.append(f"  of which {_gbp(res['unverified_total'])} is unverified (see warnings)")
    if s["consumed"]:
        lines.append(
            "Excess covered by: "
            + ", ".join(f"{_gbp(a)} from {label(y)}" for y, a in s["consumed"].items())
        )
    if res["charge"] > 0:
        lines.append(f"Uncovered excess (annual allowance charge): {_gbp(res['charge'])}")
    nxt = " · ".join(f"{label(ty)} {_gbp(v)}" for ty, v in res["carry_next"].items())
    line = f"Into {label(sel_year + 1)}: {nxt} = {_gbp(res['carry_next_total'])}"
    if res["expired"] > 0:
        line += f" ({label(sel_year - 3)} remainder {_gbp(res['expired'])} expires 5 Apr {sel_year + 1})"
    lines.append(line)
    return "\n".join(lines)


def pension_headroom(ctx):
    sel_year, inputs, profile = ctx["tax_year"], ctx["inputs"], ctx["profile"]
    today = ctx.get("today") or date.today()
    res = pension_aa.compute(sel_year, _pension_years(ctx))
    s = res["selected"]
    detail = _pension_detail(res, sel_year)
    warnings = res["warnings"]
    lab, nxt = tax_years.label(sel_year), tax_years.label(sel_year + 1)
    rate = profile["marginal"]["effective_rate"]
    rules = tax_years.pension_rules(sel_year)
    why = (
        f"Each year's annual allowance is £{rules['aa']:,} (£40,000 before 2023/24), reduced "
        f"by £1 for every £2 of adjusted income over £{rules['adjusted_income']:,} — but only "
        f"when threshold income also exceeds £{rules['threshold_income']:,} — down to a "
        f"£{rules['aa_min']:,} floor (2020/21–2022/23: £240,000 limit, £4,000 floor). Unused "
        "allowance carries forward three years, oldest first, only from years you were a "
        "scheme member; whatever is still over is charged at your marginal rate. Your payroll "
        "contribution is treated as salary sacrifice (an employer contribution, added back to "
        "threshold income); relief-at-source SIPP payments are grossed up by 25%."
    )
    carry_list = (
        " · ".join(f"{tax_years.label(ty)} {_gbp(v)}" for ty, v in res["carry_next"].items())
        or "nothing"
    )
    expired_note = (
        f" {tax_years.label(sel_year - 3)}'s remaining {_gbp(res['expired'])} expired on "
        f"5 Apr {sel_year + 1}."
        if res["expired"] > 0
        else ""
    )
    charge_tax = _gbp(res["charge"] * money(rate)) if res["charge"] > 0 else None
    sa101 = (
        "declare it on SA101 (Additional information), 'Pension savings tax charges' box 10; "
        f"the charge is at your marginal rate (~{charge_tax}). Scheme Pays can settle a charge "
        "over £2,000 from the pension itself"
    )

    if today > tax_years.tax_year_end(sel_year):
        if res["charge"] > 0:
            return _tip(
                "pension_headroom",
                f"{lab}: annual allowance charge on {_gbp(res['charge'])}",
                f"Even after carry-forward, {_gbp(res['charge'])} of {lab} pension input exceeded "
                f"the allowance — {sa101}. Carried into {nxt}: {carry_list}.{expired_note}",
                why,
                None,
                deadline=tax_years.filing_deadline(sel_year).isoformat(),
                confidence="high",
                detail=detail,
                warnings=warnings,
            )
        return _tip(
            "pension_headroom",
            f"{lab}: no annual allowance charge; {_gbp(res['carry_next_total'])} carries into {nxt}",
            f"Nothing to declare for {lab}: pension input {_gbp(s['pension_input'])} was within "
            f"the {_gbp(s['allowance'])} allowance plus carry-forward (headroom that existed: "
            f"{_gbp(res['headroom'])}). Unused allowance available in {nxt}: {carry_list}."
            + expired_note,
            why,
            None,
            confidence="high",
            detail=detail,
            warnings=warnings,
        )

    if res["charge"] > 0:
        return _tip(
            "pension_headroom",
            f"Pension input exceeds your allowance by {_gbp(res['charge'])}",
            f"Even after carry-forward, {_gbp(res['charge'])} is over the allowance: expect an "
            "annual allowance charge. If you can, reduce salary-sacrifice/employer contributions "
            f"for the rest of the year; otherwise {sa101}.",
            why,
            None,
            deadline=tax_years.tax_year_end(sel_year).isoformat(),
            detail=detail,
            warnings=warnings,
        )

    headroom = res["headroom"]
    if headroom < 100:
        return None
    # Personal contributions are capped at relevant UK earnings (or £3,600 gross
    # for anyone); the rest of the headroom can only be used by an employer.
    earnings = max(money(inputs.get("employment_income") or 0), money(3600))
    suggested = min(headroom, earnings)
    what = (
        f"Contribute up to {_gbp(suggested)} gross ({_gbp(money(suggested * Decimal('0.8')))} net "
        f"— HMRC adds 25%) to a relief-at-source SIPP before 5 April {sel_year + 1}."
    )
    if suggested < headroom:
        what += (
            f" That's capped at your relevant UK earnings ({_gbp(earnings)} employment income); "
            f"the rest of the {_gbp(headroom)} headroom can only be used by employer contributions."
        )
    if s["tapered"]:
        what += (
            f" A personal contribution also reduces threshold income ({_gbp(s['threshold_income'])} "
            f"now); if it fell to {_gbp(s['threshold_limit'])} or below the taper would switch off "
            f"and the full {_gbp(s['standard'])} allowance would apply — check before settling on "
            "an amount."
        )
    if res["unverified_total"] > 0:
        what += (
            f" {_gbp(res['unverified_total'])} of this relies on unverified prior years — see the "
            "warnings."
        )
    return _tip(
        "pension_headroom",
        f"{_gbp(headroom)} of pension annual allowance unused",
        what,
        why,
        float(suggested) * rate,
        deadline=tax_years.tax_year_end(sel_year).isoformat(),
        detail=detail,
        warnings=warnings,
    )


def sixty_percent_trap(ctx):
    y, profile = ctx["year"], ctx["profile"]
    ani = profile["income"]["adjusted_net_income"]
    if not (y["pa_taper_start"] < ani <= y["additional_threshold"]):
        return None
    excess = ani - y["pa_taper_start"]
    return _tip(
        "sixty_trap",
        f"You're £{excess:,.0f} into the 60% trap",
        f"A gross pension contribution (or Gift Aid) of £{excess:,.0f} brings "
        f"adjusted net income back to £{y['pa_taper_start']:,.0f} and restores "
        "your full personal allowance.",
        "Between £100,000 and £125,140 each £2 of income removes £1 of personal "
        "allowance, so the effective tax rate on this slice is ~60%. Relief on a "
        "contribution in this zone is correspondingly ~60%, not 40%.",
        excess * 0.60,
        deadline=tax_years.tax_year_end(ctx["tax_year"]).isoformat(),
        confidence="high",
    )


def cgt_harvest(ctx):
    y, invest, bundle = ctx["year"], ctx["invest"], ctx["bundle"]
    total_gain = float(invest.get("total_gain") or 0)
    unused = y["cgt_allowance"] - max(0.0, total_gain)
    if unused < 200:
        return None
    holdings = []
    if bundle:
        holdings = [p["symbol"] for p in bundle.get("portfolio_eoy", [])][:6]
    rate = y["cgt_rates_shares"]["higher"]
    return _tip(
        "cgt_harvest",
        f"£{unused:,.0f} of CGT allowance unused",
        "Realise gains up to the unused annual exempt amount before 5 April"
        + (f" (current holdings: {', '.join(holdings)})" if holdings else "")
        + ". Note: buying the same security back within 30 days voids this "
        "(bed-and-breakfast rule) — rebuy inside an ISA/SIPP or buy something similar.",
        f"Gains within the £{y['cgt_allowance']:,.0f} annual exempt amount are "
        "tax-free, and the allowance doesn't carry forward. Harvesting resets "
        f"your cost base, saving up to {rate:.0%} on that gain later.",
        unused * rate,
        deadline=tax_years.tax_year_end(ctx["tax_year"]).isoformat(),
    )


def bed_and_isa(ctx):
    inputs, profile = ctx["inputs"], ctx["profile"]
    isa_used = float(inputs.get("isa_used") or 0)
    remaining = ctx["year"]["isa_allowance"] - isa_used
    if remaining < 500:
        return None
    recurring = profile["tax"]["dividend_tax"] + profile["tax"]["savings_tax"]
    return _tip(
        "bed_isa",
        f"£{remaining:,.0f} of ISA allowance unused",
        f"Move up to £{remaining:,.0f} of GIA holdings into your ISA "
        "(sell in GIA, rebuy in ISA — 'bed and ISA'; the 30-day rule doesn't "
        "apply across the ISA wrapper). Cash earning taxed interest can move too.",
        "Inside an ISA, dividends, interest and gains are tax-free forever. "
        f"You're currently paying ~£{recurring:,.0f}/year of tax on investment "
        "income that could be sheltered (assumes similar income next year).",
        recurring if recurring > 0 else None,
        deadline=tax_years.tax_year_end(ctx["tax_year"]).isoformat(),
    )


def allowance_overflow(ctx):
    profile = ctx["profile"]
    parts = []
    win = 0.0
    if profile["tax"]["dividend_tax"] > 0:
        parts.append(
            f"dividends over the £{ctx['year']['dividend_allowance']:,.0f} allowance "
            f"cost £{profile['tax']['dividend_tax']:,.0f}"
        )
        win += profile["tax"]["dividend_tax"]
    if profile["tax"]["savings_tax"] > 0:
        parts.append(
            f"interest over your £{profile['allowances']['psa']:,.0f} personal savings "
            f"allowance costs £{profile['tax']['savings_tax']:,.0f}"
        )
        win += profile["tax"]["savings_tax"]
    if not parts:
        return None
    return _tip(
        "allowance_overflow",
        "Investment income is over the tax-free allowances",
        "This year: " + "; ".join(parts) + ". The bed-and-ISA tip removes this "
        "going forward; premium bonds or low-coupon gilts are alternatives for cash.",
        "The dividend allowance and personal savings allowance are use-it-or-lose-it "
        "0% bands; income above them is taxed at your marginal rates.",
        None,  # informational — the win is claimed by bed_isa
        confidence="high",
    )


def payments_on_account(ctx):
    profile, ty = ctx["profile"], ctx["tax_year"]
    untaxed = profile["tax"]["dividend_tax"] + profile["tax"]["savings_tax"]
    if untaxed <= 1000:
        return None
    deadline = tax_years.filing_deadline(ty)
    return _tip(
        "payments_on_account",
        "Payments on account will likely apply",
        f"Expect HMRC to ask for ~£{untaxed / 2:,.0f} on 31 Jan and again on 31 Jul "
        "as advance payments towards next year, on top of this year's bill. "
        "Budget for it; you can apply to reduce them if next year's income will be lower.",
        "When more than £1,000 of tax isn't collected at source, HMRC charges two "
        "advance instalments (50% each) based on this year's liability. "
        "CGT is excluded from payments on account.",
        None,
        deadline=deadline.isoformat(),
        confidence="high",
    )


def withholding_check(ctx):
    bundle = ctx["bundle"]
    if not bundle:
        return None
    flagged = set()
    for d in bundle.get("dividends", []):
        amount = float(d["amount_gbp"] or 0)
        tax = float(d["tax_at_source_gbp"] or 0)
        if amount > 0 and tax / amount > 0.20:
            flagged.add(d["symbol"])
    if not flagged:
        return None
    return _tip(
        "withholding",
        f"US dividends taxed above the 15% treaty rate ({', '.join(sorted(flagged))})",
        "Check your W-8BEN with the broker — it expires every 3 years; without a "
        "valid one, US withholding is 30% instead of the treaty 15%.",
        "The UK–US treaty caps withholding at 15% and only that 15% is creditable "
        "against UK tax — the extra 15% is simply lost.",
        None,
        confidence="high",
    )


def eri_note(ctx):
    bundle = ctx["bundle"]
    if not bundle or not bundle.get("eri_distributions"):
        return None
    return _tip(
        "eri",
        "Offshore reporting funds: excess reported income applies",
        "The report includes excess reported income (HS265) — it's taxable even "
        "though never paid out, and it raises your funds' cost base. The figures "
        "are already in the report's dividend/interest totals.",
        "Offshore reporting funds (e.g. Irish-domiciled ETFs) must report income "
        "in excess of distributions; UK holders owe tax on it 6 months after the "
        "fund's period end.",
        None,
        confidence="high",
    )


TIPS = [
    pension_headroom,
    sixty_percent_trap,
    cgt_harvest,
    bed_and_isa,
    allowance_overflow,
    payments_on_account,
    withholding_check,
    eri_note,
]


def build_tips(ctx) -> list[dict]:
    out = []
    for fn in TIPS:
        tip = fn(ctx)
        if tip:
            out.append(tip)
    out.sort(key=lambda t: -(t["estimated_win_gbp"] or 0))
    return out
