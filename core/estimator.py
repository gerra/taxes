"""The Self Assessment estimator: what the return actually asks for.

Four things live here because getting any of them wrong changes the bill:

1. **Capital gains at the rate for the disposal date.** 2024/25 is a split-rate
   year (Autumn Budget 2024): disposals before 30 October 2024 are charged at
   10%/20%, on or after at 18%/24%. The SA return's own calculation charges the
   *whole year* at the pre-30-October rates; the extra due on later disposals is
   entered by hand in Capital Gains Summary box 51. Both figures are exposed
   (`sa_cgt_at_pre_oct_rates`, `cgt_adjustment`) so the box can be filled in.
2. **Beneficial allocation.** The annual exempt amount and losses come off the
   gains taxed at the highest rate first, and the remaining basic rate band is
   filled with the gains that save the most by sitting in it.
3. **Classification before taxation.** Not everything a broker labels
   "dividend" is one: REIT property income distributions are property income
   with 20% already withheld, and distributions from funds holding more than
   60% interest-bearing assets are savings income. Neither uses the dividend
   allowance.
4. **Foreign tax credit relief is a credit against tax**, capped at the lower of
   the tax actually withheld, the treaty rate, and the UK tax on that income.
   It never reduces the taxable amount.

Amounts are Decimal throughout; callers convert at their own boundary. HMRC
rounds gains down and losses/reliefs up to whole pounds before applying rates,
and keeps the tax to the penny — so does this module, which means a figure can
differ by up to £1 from one computed on unrounded amounts.

Yearly maintenance: rates and allowances come from `core.tax_years`; the
REIT/bond-fund tables below need a look whenever a new holding starts paying.
"""

from __future__ import annotations

import itertools
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)

# Payments on account: due only when the balancing payment (the SA liability
# left after tax collected at source, CGT excluded) tops this, AND less than
# 80% of the year's income tax was collected at source. TMA 1970 s59A.
POA_THRESHOLD = Decimal(1000)
POA_AT_SOURCE_SHARE = Decimal("0.80")

# Rates residential property is charged at when the year's constants don't say.
_DEFAULT_RESIDENTIAL = {"basic": 0.18, "higher": 0.24}

PRE_CHANGE = "pre_30_oct"
POST_CHANGE = "post_30_oct"
SHARES = "shares"
RESIDENTIAL = "residential"


# ── Distribution classifications ──────────────────────────────────────────────
#
# `taxed_as` is the income tax pot the amount joins: "dividend" (dividend rates,
# dividend allowance), "savings" (savings rates, personal savings allowance),
# "property"/"misc" (ordinary income tax rates, no allowance of their own).

UK_DIVIDEND = "uk_dividend"
FOREIGN_DIVIDEND = "foreign_dividend"
PROPERTY_INCOME_DISTRIBUTION = "property_income_distribution"
INTEREST_DISTRIBUTION = "interest_distribution"
UK_INTEREST = "uk_interest"
FOREIGN_INTEREST = "foreign_interest"
SHARE_LENDING_FEE = "share_lending_fee"
ERI_DIVIDEND = "eri_dividend"
ERI_INTEREST = "eri_interest"

KINDS = {
    UK_DIVIDEND: ("UK dividend", "dividend", True),
    FOREIGN_DIVIDEND: ("Foreign dividend", "dividend", True),
    PROPERTY_INCOME_DISTRIBUTION: ("REIT property income distribution (PID)", "property", False),
    INTEREST_DISTRIBUTION: ("Bond fund interest distribution", "savings", False),
    UK_INTEREST: ("UK interest", "savings", False),
    FOREIGN_INTEREST: ("Foreign interest", "savings", False),
    SHARE_LENDING_FEE: ("Share-lending fee", "misc", False),
    ERI_DIVIDEND: ("Excess reported income (dividend fund)", "dividend", True),
    ERI_INTEREST: ("Excess reported income (bond fund)", "savings", False),
}

# UK REITs and property companies: what they pay out is mostly a property
# income distribution with 20% income tax already deducted, not a dividend.
# A REIT can also pay an ordinary dividend, so the ticker alone does not decide
# it: only rows the broker taxed, or typed PROPERTY, are treated as PIDs. The
# table sharpens the wording and catches a REIT whose ISIN is not GB.
KNOWN_REITS = {
    "LAND": "Landsec (British Land's sector peer) — UK REIT",
    "PHP": "Primary Health Properties — UK REIT",
    "BLND": "British Land — UK REIT",
    "SGRO": "Segro — UK REIT",
    "BBOX": "Tritax Big Box — UK REIT",
    "UKCM": "UK Commercial Property REIT",
    "TRY": "TR Property Investment Trust — UK REIT",
}

# Funds and ETFs that hold more than 60% interest-bearing assets, so their
# distributions are interest for UK tax (the bond fund rule, ITTOIA 2005 s378A).
# Check the fund's reporting-fund statement before adding one.
KNOWN_INTEREST_FUNDS = {
    "VGOV": "Vanguard UK Gilt UCITS ETF — gilts only",
    "VUSC": "Vanguard USD Corporate 1-3 Year Bond UCITS ETF",
    "VUCP": "Vanguard USD Corporate Bond UCITS ETF",
    "VECP": "Vanguard EUR Corporate Bond UCITS ETF",
    "ERNS": "iShares £ Ultrashort Bond UCITS ETF",
    "ERNE": "iShares € Ultrashort Bond UCITS ETF",
    "ERNA": "iShares $ Ultrashort Bond UCITS ETF",
    "IGLS": "iShares Core UK Gilts 0-5yr UCITS ETF",
    "IGLT": "iShares Core UK Gilts UCITS ETF",
    "VAGP": "Vanguard Global Aggregate Bond UCITS ETF (GBP hedged)",
    "SAAA": "iShares $ Treasury Bond 0-1yr UCITS ETF",
}

# ISIN prefixes of the usual offshore fund domiciles. A fund registered there
# is an offshore fund: its excess reported income is taxable (HS265), and
# whether its distributions are interest or dividends depends on the >60% bond
# test in its reporting-fund statement, which no export ever carries.
OFFSHORE_ISIN_PREFIXES = ("IE", "LU", "JE", "GG", "IM", "KY", "BM")

# Names in the `interest`/`other_income` logs that are brokers, not securities:
# a payment "from" one of these is cash interest or a share-lending fee.
_BROKER_NAMES = {"freetrade", "charles schwab", "schwab", "interactive brokers", "trading 212"}

# A UK payer taking tax off a "dividend" is a REIT: UK dividends carry no
# withholding, and the PID rate is 20%.
_PID_WITHHOLDING_RATE = Decimal("0.20")

# Double taxation treaty rates on dividends, by the payer's ISIN country: the
# most Foreign Tax Credit Relief HMRC will give however much was actually
# withheld. A country not listed here gets no credit until it is added.
TREATY_DIVIDEND_RATES = {
    "US": Decimal("0.15"),
    "PL": Decimal("0.10"),
    "IE": ZERO,  # Irish-domiciled ETFs distribute gross to UK holders
    "LU": ZERO,
}


# ── Small helpers ─────────────────────────────────────────────────────────────


def dec(value) -> Decimal:
    """Decimal from anything the bundle carries (str, float, int, None)."""
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_gain_down(amount: Decimal) -> Decimal:
    """Gains go down to the whole pound, the way HMRC's calculation does."""
    return amount.to_integral_value(rounding=ROUND_FLOOR)


def round_relief_up(amount: Decimal) -> Decimal:
    """Losses and reliefs go up to the whole pound — both favour the taxpayer."""
    return amount.to_integral_value(rounding=ROUND_CEILING)


def _fmt_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%-d %b %Y")


def is_offshore(isin: str | None) -> bool:
    return bool(isin) and str(isin)[:2].upper() in OFFSHORE_ISIN_PREFIXES


def unverified_fund_distributions(rows: list[dict], bundle: dict) -> list[dict]:
    """Distributions taxed as dividends that came from an offshore fund we have
    no reporting-fund status for. If the fund holds more than 60% interest-
    bearing assets its distributions are interest instead, and only the fund's
    own statement says which — so these are flagged, never guessed."""
    isins = {
        (d.get("symbol") or "").upper(): d.get("isin")
        for d in (bundle.get("dividends") or [])
        if d.get("isin")
    }
    out = []
    for r in rows:
        symbol = (r["symbol"] or "").upper()
        if r["kind"] != FOREIGN_DIVIDEND or symbol in KNOWN_INTEREST_FUNDS:
            continue
        isin = isins.get(symbol)
        if is_offshore(isin):
            out.append({"symbol": r["symbol"], "isin": str(isin), "amount_gbp": r["gross_gbp"]})
    merged: dict[str, dict] = {}
    for f in out:
        row = merged.setdefault(f["symbol"], {**f, "amount_gbp": ZERO})
        row["amount_gbp"] += f["amount_gbp"]
    return [merged[k] for k in sorted(merged)]


def is_cgt_exempt(disposal: dict) -> bool:
    """Gilts and UK Treasury bills: outside CGT entirely (TCGA 1992 s115)."""
    return bool(disposal.get("exempt"))


# ── Capital gains ─────────────────────────────────────────────────────────────


def rate_change(year: dict) -> dict | None:
    """The year's mid-year CGT rate change, if it had one."""
    return year.get("cgt_mid_year_change")


def _bucket_defs(year: dict) -> list[dict]:
    """The rate buckets gains can fall into this year, in canonical order:
    highest-charged first, which is also the order relief is offered to."""
    shares = year["cgt_rates_shares"]
    resi = year.get("cgt_rates_residential") or _DEFAULT_RESIDENTIAL
    change = rate_change(year)
    out: list[dict] = []
    if change:
        cut = _fmt_date(change["date"])
        before = change["rates_before"]
        out.append(
            {
                "key": POST_CHANGE,
                "label": f"Gains on disposals on or after {cut}",
                "basic": dec(shares["basic"]),
                "higher": dec(shares["higher"]),
                "residential": False,
            }
        )
        out.append(
            {
                "key": PRE_CHANGE,
                "label": f"Gains on disposals before {cut}",
                "basic": dec(before["basic"]),
                "higher": dec(before["higher"]),
                "residential": False,
            }
        )
    else:
        out.append(
            {
                "key": SHARES,
                "label": "Gains on shares and other assets",
                "basic": dec(shares["basic"]),
                "higher": dec(shares["higher"]),
                "residential": False,
            }
        )
    out.append(
        {
            "key": RESIDENTIAL,
            "label": "Gains on residential property",
            "basic": dec(resi["basic"]),
            "higher": dec(resi["higher"]),
            "residential": True,
        }
    )
    for b in out:
        b["gain"] = ZERO
    return out


def _bucket_for(disposal: dict, change: dict | None) -> str:
    if disposal.get("residential"):
        return RESIDENTIAL
    if not change:
        return SHARES
    return (
        PRE_CHANGE
        if date.fromisoformat(disposal["date"]) < date.fromisoformat(change["date"])
        else POST_CHANGE
    )


def _charge(buckets: list[dict], nets: dict[str, Decimal], basic_room: Decimal) -> list[dict]:
    """Round each bucket's net gain down, then fill the remaining basic rate
    band with the gains that gain most from being in it (the biggest
    higher-minus-basic spread), and charge the rest at the higher rate.

    Returns rows in `buckets` order, each carrying at_basic/at_higher/tax."""
    rows = []
    for b in buckets:
        net = nets.get(b["key"], ZERO)
        rows.append({**b, "net": net, "rounded": round_gain_down(net)})
    room = basic_room
    # Biggest saving from the band first; ties resolved by the lower basic rate,
    # which is what "fill the band with the lowest-rate gains first" means when
    # the spreads are equal.
    for row in sorted(rows, key=lambda r: (-(r["higher"] - r["basic"]), r["basic"])):
        at_basic = min(row["rounded"], room)
        room -= at_basic
        row["at_basic"] = at_basic
        row["at_higher"] = row["rounded"] - at_basic
        row["tax"] = at_basic * row["basic"] + row["at_higher"] * row["higher"]
    return rows


def _allocate_relief(order: tuple[dict, ...], relief: Decimal) -> dict[str, Decimal]:
    left = relief
    nets: dict[str, Decimal] = {}
    for b in order:
        take = min(b["gain"], left)
        nets[b["key"]] = b["gain"] - take
        left -= take
    return nets


def cgt_for_year(
    disposals: list[dict],
    year: dict,
    *,
    basic_room: Decimal | float | int = 0,
    losses_brought_forward: Decimal | float | int = 0,
) -> dict:
    """Capital gains tax for one tax year, by disposal date.

    disposals: [{date: ISO, gain: amount, exempt?: bool, residential?: bool}] —
    the tax year is the caller's; only exempt/residential flags and the date
    matter here. basic_room: how much of the basic rate band the taxpayer's
    income leaves free (gains stack on top of income)."""
    basic_room = dec(basic_room)
    change = rate_change(year)
    buckets = _bucket_defs(year)
    by_key = {b["key"]: b for b in buckets}

    losses = ZERO
    for d in disposals:
        if is_cgt_exempt(d):
            continue
        gain = dec(d.get("gain"))
        if gain >= 0:
            by_key[_bucket_for(d, change)]["gain"] += gain
        else:
            losses += -gain

    gains_total = sum((b["gain"] for b in buckets), ZERO)
    aea = dec(year.get("cgt_allowance", 0))
    after_losses = max(ZERO, gains_total - losses)
    bf_used = min(dec(losses_brought_forward), max(ZERO, after_losses - aea))
    # Reliefs are rounded up (in the taxpayer's favour); the AEA is already whole.
    relief_total = min(gains_total, round_relief_up(losses) + aea + round_relief_up(bf_used))

    # Relief comes off the highest-charged gains first. With at most three
    # buckets, trying every order and keeping the cheapest is exact and cheap —
    # and it stays right if a future year's rates reorder the buckets.
    chargeable = [b for b in buckets if b["gain"] > 0]
    best_rows, best_tax = None, None
    for order in itertools.permutations(chargeable):
        rows = _charge(buckets, _allocate_relief(order, relief_total), basic_room)
        total = sum((r["tax"] for r in rows), ZERO)
        if best_tax is None or total < best_tax:
            best_rows, best_tax = rows, total
    if best_rows is None:  # no gains at all
        best_rows = _charge(buckets, {}, basic_room)
        best_tax = ZERO

    total_gain = gains_total - losses
    taxable_gain = max(ZERO, gains_total - relief_total)
    sa_cgt = _sa_return_charge(best_rows, year, basic_room)
    adjustment = best_tax - sa_cgt

    pre_change_disposals = [
        d
        for d in disposals
        if not is_cgt_exempt(d) and change and _bucket_for(d, change) == PRE_CHANGE
    ]
    needs_box_51 = bool(change) and adjustment != ZERO
    note = None
    if needs_box_51:
        cut = _fmt_date(change["date"])
        note = (
            f"The Self Assessment return charges the whole year at the pre-{cut} rates "
            f"({_pct(change['rates_before']['basic'])}/{_pct(change['rates_before']['higher'])}), "
            f"so its own figure is £{sa_cgt:,.2f}. Your disposals on or after {cut} are "
            f"charged at {_pct(year['cgt_rates_shares']['basic'])}/"
            f"{_pct(year['cgt_rates_shares']['higher'])} instead, which is £{adjustment:,.2f} "
            "more. Put that in box 51 of the Capital Gains Summary (SA108), 'adjustment to "
            "Capital Gains Tax', and say why in box 54."
        )

    return {
        "gains": gains_total,
        "losses": losses,
        "losses_brought_forward_used": bf_used,
        "total_gain": total_gain,
        "annual_exempt_amount": aea,
        "relief_allocated": relief_total,
        "taxable_gain": taxable_gain,
        "taxable_gain_rounded": round_gain_down(taxable_gain),
        "basic_room": basic_room,
        "buckets": [
            {
                "key": r["key"],
                "label": r["label"],
                "gain": by_key[r["key"]]["gain"],
                "relief": by_key[r["key"]]["gain"] - r["net"],
                "net": r["net"],
                "rounded": r["rounded"],
                "at_basic": r["at_basic"],
                "at_higher": r["at_higher"],
                "basic_rate": r["basic"],
                "higher_rate": r["higher"],
                "tax": r["tax"],
            }
            for r in best_rows
        ],
        "cgt_total": best_tax,
        "sa_cgt_at_pre_oct_rates": sa_cgt,
        "cgt_adjustment": adjustment,
        "split_applies": bool(change),
        "change_date": change["date"] if change else None,
        "has_pre_change_disposals": bool(pre_change_disposals),
        "needs_box_51_adjustment": needs_box_51,
        "adjustment_note": note,
    }


def _pct(rate) -> str:
    return f"{dec(rate) * HUNDRED:.0f}%"


def _sa_return_charge(rows: list[dict], year: dict, basic_room: Decimal) -> Decimal:
    """What the SA return's own calculation produces: every non-residential gain
    at the pre-change rates (the return has no disposal-date split), residential
    at its own. Rounding follows the return, which works from the SA108 totals —
    so the whole-year figure is rounded once, not bucket by bucket."""
    change = rate_change(year)
    pre = change["rates_before"] if change else year["cgt_rates_shares"]
    resi = year.get("cgt_rates_residential") or _DEFAULT_RESIDENTIAL
    shares_net = sum((r["net"] for r in rows if not r["residential"]), ZERO)
    resi_net = sum((r["net"] for r in rows if r["residential"]), ZERO)
    sa_buckets = [
        {
            "key": SHARES,
            "label": "shares",
            "basic": dec(pre["basic"]),
            "higher": dec(pre["higher"]),
            "residential": False,
        },
        {
            "key": RESIDENTIAL,
            "label": "residential",
            "basic": dec(resi["basic"]),
            "higher": dec(resi["higher"]),
            "residential": True,
        },
    ]
    charged = _charge(sa_buckets, {SHARES: shares_net, RESIDENTIAL: resi_net}, basic_room)
    return sum((r["tax"] for r in charged), ZERO)


# ── Distribution classification ───────────────────────────────────────────────


def _looks_like_broker(name: str) -> bool:
    return (name or "").strip().lower() in _BROKER_NAMES


def _classify_dividend(row: dict, reits: dict, interest_funds: dict) -> tuple[str, str]:
    """(kind, why) for one row the export called a dividend."""
    symbol = (row.get("symbol") or "").upper()
    isin = (row.get("isin") or "").upper()
    country = (row.get("country") or "").upper() or None
    withheld = abs(dec(row.get("tax_at_source_gbp")))
    gross = dec(row.get("amount_gbp"))

    if symbol in interest_funds or isin in interest_funds:
        note = interest_funds.get(symbol) or interest_funds.get(isin)
        return INTEREST_DISTRIBUTION, (
            f"{note}: a fund holding more than 60% interest-bearing assets pays interest "
            "distributions, taxed as savings income, not dividends (ITTOIA 2005 s378A)."
        )
    if row.get("is_interest"):
        return INTEREST_DISTRIBUTION, (
            "The calculator was told this holding is a bond fund, so its distributions are "
            "interest for UK tax, not dividends."
        )
    if withheld > 0 and (country == "GB" or symbol in reits):
        rate = (withheld / gross) if gross else ZERO
        who = reits.get(symbol, "A UK company")
        return PROPERTY_INCOME_DISTRIBUTION, (
            f"{who} paid this with £{withheld:,.2f} tax taken off ({rate * HUNDRED:.0f}%). "
            "UK dividends are always paid gross, so this is a REIT property income "
            "distribution out of its tax-exempt property business: property income at your "
            "marginal rate, with the 20% withheld credited against the bill. It does not "
            "use the dividend allowance."
        )
    if country == "GB" and symbol in reits:
        # A REIT can pay an ordinary dividend as well as a PID, and this one
        # came gross, so it is left as a dividend — but it is worth checking.
        return UK_DIVIDEND, (
            f"{reits[symbol]}, paid gross. A REIT's property income distributions always "
            "have 20% deducted, so a gross payment is its ordinary (non-PID) dividend and "
            "is taxed at dividend rates. Check the payment notice: if it was in fact a PID, "
            "it belongs in box 17 as property income instead."
        )
    if country == "GB":
        return UK_DIVIDEND, (
            "A UK-registered company paying gross: an ordinary dividend, taxed at dividend "
            "rates after the dividend allowance."
        )
    where = f" ({country})" if country else ""
    return FOREIGN_DIVIDEND, (
        f"The payer is registered outside the UK{where}, so this is a foreign dividend: UK "
        "dividend rates apply, and any tax withheld is claimable as Foreign Tax Credit "
        "Relief up to the treaty rate."
    )


def _row(
    *,
    date_: str,
    symbol: str | None,
    kind: str,
    why: str,
    gross_gbp: Decimal,
    withheld_gbp: Decimal = ZERO,
    currency: str | None = None,
    fx_rate=None,
    gross: Decimal | None = None,
    source: str | None = None,
    treaty_rate: Decimal | None = None,
) -> dict:
    label, taxed_as, uses_allowance = KINDS[kind]
    # The treaty caps the credit whatever the broker actually withheld.
    creditable = min(withheld_gbp, treaty_rate * gross_gbp) if treaty_rate is not None else ZERO
    return {
        "date": date_,
        "symbol": symbol,
        "source": source or symbol,
        "kind": kind,
        "label": label,
        "taxed_as": taxed_as,
        "uses_dividend_allowance": uses_allowance,
        "why": why,
        "currency": currency,
        "gross": gross,
        "fx_rate": fx_rate,
        "gross_gbp": gross_gbp,
        "withheld_gbp": withheld_gbp,
        "amount_gbp": gross_gbp,
        "treaty_rate": treaty_rate,
        "treaty_relief_gbp": creditable,
    }


def _treaty_rate_for(row: dict, kind: str) -> Decimal | None:
    """The treaty rate to cap the credit at, from the engine's own match where
    it made one, otherwise from the payer's ISIN country."""
    if kind != FOREIGN_DIVIDEND:
        return None
    treaty = row.get("treaty") or {}
    if treaty.get("treaty_rate") is not None:
        return dec(treaty["treaty_rate"])
    country = (row.get("country") or (row.get("isin") or "")[:2]).upper()
    return TREATY_DIVIDEND_RATES.get(country)


def classify_distributions(
    bundle: dict,
    *,
    reits: dict | None = None,
    interest_funds: dict | None = None,
) -> list[dict]:
    """Every distribution in the bundle, classified for UK tax and itemised for
    a hand audit: date, ticker, gross, withheld, classification, GBP amount and
    the FX rate used. Ordered by date, then by ticker."""
    reits = KNOWN_REITS if reits is None else reits
    interest_funds = KNOWN_INTEREST_FUNDS if interest_funds is None else interest_funds
    rows: list[dict] = []

    for d in bundle.get("dividends") or []:
        kind, why = _classify_dividend(d, reits, interest_funds)
        rows.append(
            _row(
                date_=d["date"],
                symbol=d.get("symbol"),
                kind=kind,
                why=why,
                gross_gbp=dec(d.get("amount_gbp")),
                withheld_gbp=abs(dec(d.get("tax_at_source_gbp"))),
                currency=d.get("currency"),
                fx_rate=d.get("fx_rate"),
                gross=dec(d["gross"]) if d.get("gross") is not None else None,
                treaty_rate=_treaty_rate_for(d, kind),
            )
        )

    for i in bundle.get("interest") or []:
        uk = i.get("uk") if i.get("uk") is not None else (i.get("currency") == "GBP")
        rows.append(
            _row(
                date_=i["date"],
                symbol=None,
                source=i.get("broker"),
                kind=UK_INTEREST if uk else FOREIGN_INTEREST,
                why=(
                    "Cash interest paid gross by a UK bank or broker: savings income, taxed "
                    "after the personal savings allowance."
                    if uk
                    else "Cash interest from a non-UK source (e.g. USD cash at a US broker): "
                    "savings income here, converted at the HMRC monthly rate. The UK–US "
                    "treaty rate on interest is nil, so any withholding is not creditable."
                ),
                gross_gbp=dec(i.get("amount_gbp")),
                currency=i.get("currency"),
                fx_rate=i.get("fx_rate"),
            )
        )

    for o in bundle.get("other_income") or []:
        source = o.get("source") or ""
        withheld = abs(dec(o.get("tax_gbp")))
        is_fee = withheld == 0 and _looks_like_broker(source)
        rows.append(
            _row(
                date_=o["date"],
                symbol=None if is_fee else source,
                source=source,
                kind=SHARE_LENDING_FEE if is_fee else PROPERTY_INCOME_DISTRIBUTION,
                why=(
                    "A fee the broker paid for lending your shares out: miscellaneous income, "
                    "not a dividend (SA100 box 17)."
                    if is_fee
                    else "Typed as a property distribution by the broker: a REIT PID, taxed as "
                    "property income with the 20% withheld credited against the bill."
                ),
                gross_gbp=dec(o.get("amount_gbp")),
                withheld_gbp=withheld,
            )
        )

    for e in bundle.get("eri_distributions") or []:
        symbol = (e.get("symbol") or "").upper()
        interest = bool(e.get("is_interest")) or symbol in interest_funds
        rows.append(
            _row(
                date_=e["date"],
                symbol=e.get("symbol"),
                kind=ERI_INTEREST if interest else ERI_DIVIDEND,
                why=(
                    "Excess reported income of an offshore reporting fund (HS265): taxable "
                    "though never paid out, six months after the fund's period end. "
                    + (
                        "The fund is a bond fund, so it counts as interest."
                        if interest
                        else "Taxed as a foreign dividend."
                    )
                ),
                gross_gbp=dec(e.get("amount_gbp")),
            )
        )

    rows.sort(key=lambda r: (r["date"], r["source"] or "", r["kind"]))
    return rows


def income_totals(rows: list[dict]) -> dict:
    """Totals by classification, ready for the income tax computation."""

    def total(*kinds, field="gross_gbp") -> Decimal:
        return sum((r[field] for r in rows if r["kind"] in kinds), ZERO)

    uk_dividends = total(UK_DIVIDEND)
    foreign_dividends = total(FOREIGN_DIVIDEND, ERI_DIVIDEND)
    interest_distributions = total(INTEREST_DISTRIBUTION, ERI_INTEREST)
    uk_interest = total(UK_INTEREST)
    foreign_interest = total(FOREIGN_INTEREST)
    property_income = total(PROPERTY_INCOME_DISTRIBUTION)
    fees = total(SHARE_LENDING_FEE)
    return {
        "uk_dividends": uk_dividends,
        "foreign_dividends": foreign_dividends,
        "dividends_total": uk_dividends + foreign_dividends,
        "foreign_dividend_tax": total(FOREIGN_DIVIDEND, ERI_DIVIDEND, field="withheld_gbp"),
        # What the treaties let you actually credit — the FTCR cap.
        "foreign_dividend_treaty_relief": total(
            FOREIGN_DIVIDEND, ERI_DIVIDEND, field="treaty_relief_gbp"
        ),
        "property_income": property_income,
        "property_income_tax": total(PROPERTY_INCOME_DISTRIBUTION, field="withheld_gbp"),
        "share_lending_fees": fees,
        "other_income": property_income + fees,
        "other_income_tax": total(PROPERTY_INCOME_DISTRIBUTION, field="withheld_gbp"),
        "interest_distributions": interest_distributions,
        "uk_interest": uk_interest,
        "foreign_interest": foreign_interest,
        "savings_total": interest_distributions + uk_interest + foreign_interest,
    }


# ── Foreign tax credit relief ─────────────────────────────────────────────────


def ftcr(
    *,
    gross: Decimal,
    withheld: Decimal,
    treaty_rate: Decimal,
    uk_tax_on_income: Decimal,
) -> Decimal:
    """Relief for foreign tax on the same income (TIOPA 2010 Part 2): the lower
    of the tax actually withheld, the treaty rate on the gross amount, and the
    UK tax on that income. A credit against the UK tax bill — it never reduces
    the taxable amount, and it is never repayable."""
    return max(
        ZERO,
        min(abs(dec(withheld)), dec(treaty_rate) * dec(gross), max(ZERO, dec(uk_tax_on_income))),
    )


# ── Payments on account ───────────────────────────────────────────────────────


def payments_on_account(
    *,
    liability_excluding_cgt: Decimal,
    tax_collected_at_source: Decimal,
    total_liability_excluding_cgt: Decimal,
) -> dict:
    """The TMA 1970 s59A test, with both conditions kept visible.

    liability_excluding_cgt: the balancing payment — income tax (and Class 4
    NIC) left owing after tax collected at source, with capital gains tax taken
    out. CGT is never part of a payment on account.
    total_liability_excluding_cgt: the whole income tax liability for the year,
    at-source deductions included, again without CGT."""
    liability = max(ZERO, dec(liability_excluding_cgt))
    total = max(ZERO, dec(total_liability_excluding_cgt))
    at_source = max(ZERO, dec(tax_collected_at_source))
    share = (at_source / total) if total > 0 else ONE
    over_threshold = liability > POA_THRESHOLD
    under_80 = share < POA_AT_SOURCE_SHARE
    required = over_threshold and under_80
    return {
        "required": required,
        "threshold": POA_THRESHOLD,
        "liability_excluding_cgt": liability,
        "over_threshold": over_threshold,
        "tax_collected_at_source": at_source,
        "total_liability_excluding_cgt": total,
        "percent_at_source": share * HUNDRED,
        "under_80_percent_at_source": under_80,
        "each_instalment": (liability / 2) if required else ZERO,
        "explain": (
            "Payments on account are due only when both tests are met: the Self Assessment "
            f"balancing payment excluding capital gains tax is over £{POA_THRESHOLD:,.0f} "
            f"(here £{liability:,.2f} — {'yes' if over_threshold else 'no'}), and less than 80% "
            "of the year's income tax was collected at source "
            f"(here {share * HUNDRED:.1f}% — {'yes' if under_80 else 'no'}). "
            + (
                f"Two instalments of £{liability / 2:,.2f} are due, on 31 January and 31 July."
                if required
                else "Neither instalment applies. Capital gains tax is never part of a payment "
                "on account, so a big CGT bill on its own never triggers one."
            )
        ),
    }
