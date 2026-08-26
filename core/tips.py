"""Tip catalogue: each tip is a pure function (ctx) -> tip dict | None.

ctx = {inputs, year (tax_years constants), profile (tax_profile.build_profile),
invest (report summary), bundle (full ReportBundle or None), tax_year}.

Every tip states its assumptions; the UI renders a disclaimer that these are
computed hints, not advice."""

from core import tax_years


def _tip(id_, title, what, why, win, deadline=None, confidence="medium"):
    return {
        "id": id_,
        "title": title,
        "what_to_do": what,
        "why": why,
        "estimated_win_gbp": round(win, 0) if win is not None else None,
        "deadline": deadline,
        "confidence": confidence,
    }


def pension_headroom(ctx):
    y, inputs, profile = ctx["year"], ctx["inputs"], ctx["profile"]
    ani = profile["income"]["adjusted_net_income"]
    employer = float(inputs.get("pension_employer") or 0)
    employee = float(inputs.get("pension_employee") or 0)
    sipp_gross = float(inputs.get("sipp_paid") or 0) / 0.8
    used = employer + employee + sipp_gross

    aa = y["pension_aa"]
    # approx: taper test uses adjusted income ≈ ANI + employer contributions
    adjusted_income = ani + employer + employee
    if adjusted_income > y["pension_taper_adjusted_income"]:
        aa = max(
            y["pension_aa_min"],
            aa - (adjusted_income - y["pension_taper_adjusted_income"]) / 2,
        )

    # Carry-forward: unused allowance from the 3 prior years, each at that
    # year's own (untapered) allowance — £40k up to 2022/23, £60k since.
    carry_forward = 0.0
    carried = []  # (tax_year, unused) for years that contribute something
    for i in (1, 2, 3):
        prior = inputs.get(f"pension_prior_{i}")
        prior_year = ctx["tax_year"] - i
        prior_aa = tax_years.pension_aa(prior_year)
        if prior is None or prior_aa is None:
            continue
        unused = max(0.0, prior_aa - float(prior or 0))
        carry_forward += unused
        if unused:
            carried.append((prior_year, unused))

    headroom = max(0.0, aa - used) + carry_forward
    if headroom < 100:
        return None
    rate = profile["marginal"]["effective_rate"]
    deadline = tax_years.tax_year_end(ctx["tax_year"]).isoformat()
    return _tip(
        "pension_headroom",
        f"£{headroom:,.0f} of pension annual allowance unused",
        f"Contribute up to £{headroom:,.0f} (gross) to your SIPP before 5 April. "
        f"Pay in £{headroom * 0.8:,.0f} net — HMRC adds 25% automatically; any "
        "higher-rate relief comes back through Self Assessment.",
        f"Pension contributions get relief at your marginal rate "
        f"({rate:.0%} effective for you"
        + (", boosted by personal-allowance restoration" if profile["bands"]["in_pa_taper"] else "")
        + f"). Annual allowance this year: £{aa:,.0f}"
        + (
            f" plus £{carry_forward:,.0f} carry-forward ("
            + ", ".join(f"£{u:,.0f} from {tax_years.label(py)}" for py, u in carried)
            + ")"
            if carry_forward
            else ""
        )
        + ". Carry-forward uses each year's own allowance and assumes your income "
        "was below the taper threshold in those years and the figures you entered "
        "for them are complete.",
        headroom * rate,
        deadline=deadline,
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
