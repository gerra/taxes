"""CapitalGainsReport -> ReportBundle JSON. Only imported by engine.worker.

Decimals are serialised as strings to keep full precision; the frontend formats
them. schema_version guards consumers against shape changes on fork upgrades.
"""

from collections import defaultdict
from decimal import Decimal

SCHEMA_VERSION = 2


def _d(value) -> str | None:
    return None if value is None else str(value)


def _entry(e) -> dict:
    return {
        "rule": e.rule_type.name,
        "quantity": _d(e.quantity),
        "amount": _d(e.amount),
        "allowable_cost": _d(e.allowable_cost),
        "fees": _d(e.fees),
        "gain": _d(e.gain),
        "new_quantity": _d(e.new_quantity),
        "new_pool_cost": _d(e.new_pool_cost),
        "bnb_date": (
            e.bed_and_breakfast_date_index.isoformat() if e.bed_and_breakfast_date_index else None
        ),
    }


def serialize_report(report) -> dict:
    from cgt_calc.model import RuleType

    disposals = []
    acquisitions = []
    other_events = []
    for dt in sorted(report.calculation_log):
        for key, entries in report.calculation_log[dt].items():
            kind, _, label = key.partition("$")
            event = {
                "date": dt.isoformat(),
                "symbol": label,
                "entries": [_entry(e) for e in entries],
                "amount": _d(sum((e.amount for e in entries), Decimal(0))),
                "gain": _d(sum((e.gain for e in entries), Decimal(0))),
            }
            if kind in ("sell", "exempt"):
                # An exempt security (a gilt, a UK T-bill) is listed with its
                # notional gain but counts for nothing: TCGA 1992 s115.
                event["exempt"] = kind == "exempt"
                disposals.append(event)
            elif kind == "buy":
                acquisitions.append(event)
            else:
                event["kind"] = kind
                other_events.append(event)

    dividends = []
    interest = []
    interest_tax = []
    other_income: dict[tuple[str, str], dict] = {}
    eri_distributions = []
    for dt in sorted(report.calculation_log_yields):
        for key, entries in report.calculation_log_yields[dt].items():
            kind, _, label = key.partition("$")
            for e in entries:
                if kind == "dividend" and e.dividend is not None:
                    div = e.dividend
                    dividends.append(
                        {
                            "date": dt.isoformat(),
                            "symbol": label,
                            "amount_gbp": _d(e.amount),
                            "tax_at_source_gbp": _d(div.tax_at_source),
                            "is_interest": div.is_interest,
                            "treaty": (
                                {
                                    "country": div.tax_treaty.country,
                                    "country_rate": _d(div.tax_treaty.country_rate),
                                    "treaty_rate": _d(div.tax_treaty.treaty_rate),
                                    "relief_gbp": _d(div.tax_treaty_amount),
                                }
                                if div.tax_treaty
                                else None
                            ),
                        }
                    )
                elif kind.startswith("otherIncome"):
                    # Property income distributions, share-lending fees: one
                    # row per payment, the tax withheld folded in by source.
                    row = other_income.setdefault(
                        (dt.isoformat(), label),
                        {
                            "date": dt.isoformat(),
                            "source": label,
                            "amount_gbp": "0",
                            "tax_gbp": "0",
                        },
                    )
                    field = "tax_gbp" if kind == "otherIncomeTax" else "amount_gbp"
                    row[field] = _d(Decimal(row[field]) + e.amount)
                elif kind.startswith("interestTax"):
                    interest_tax.append(
                        {
                            "date": dt.isoformat(),
                            "broker": label,
                            "currency": kind[len("interestTax") :],
                            "amount_gbp": _d(e.amount),
                        }
                    )
                elif kind.startswith("interest"):
                    interest.append(
                        {
                            "date": dt.isoformat(),
                            "broker": label,
                            "currency": "GBP" if kind == "interestUK" else kind[len("interest") :],
                            "uk": kind == "interestUK",
                            "amount_gbp": _d(e.amount),
                        }
                    )
                elif e.rule_type == RuleType.EXCESS_REPORTED_INCOME_DISTRIBUTION:
                    eri_distributions.append(
                        {
                            "date": dt.isoformat(),
                            "symbol": label,
                            "amount_gbp": _d(e.amount),
                            "is_interest": bool(e.eris and e.eris[0].is_interest),
                        }
                    )

    # Aggregate interest per (broker, currency) for convenience
    interest_totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for row in interest:
        interest_totals[(row["broker"], row["currency"])] += Decimal(row["amount_gbp"])

    allowance = report.capital_gain_allowance
    taxable_gain = (
        max(Decimal(0), report.total_gain() - allowance) if allowance is not None else None
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "tax_year": report.tax_year,
        "totals": {
            "disposal_count": report.disposal_count,
            "disposal_proceeds": _d(report.disposal_proceeds),
            "allowable_costs": _d(report.allowable_costs),
            "capital_gain_before_losses": _d(report.capital_gain),
            "capital_loss": _d(report.capital_loss),
            "total_gain": _d(report.total_gain()),
            "capital_gain_allowance": _d(allowance),
            "taxable_gain": _d(taxable_gain),
            "dividends_total": _d(report.total_dividends_amount()),
            "dividend_treaty_relief": _d(report.total_dividend_taxes_in_tax_treaties_amount()),
            "dividend_allowance": _d(report.dividend_allowance),
            "dividends_taxable": _d(report.total_dividend_taxable_gain()),
            "uk_interest": _d(report.total_uk_interest),
            "foreign_interest": _d(report.total_foreign_interest),
            "interest_tax": _d(report.total_interest_tax),
            "other_income": _d(report.total_other_income),
            "other_income_tax": _d(report.total_other_income_tax),
            "exempt_disposal_count": report.exempt_disposal_count(),
            "exempt_disposal_proceeds": _d(report.exempt_disposal_proceeds()),
            "eri_dividends": _d(report.total_eri_amount(is_interest=False)),
            "eri_interest": _d(report.total_eri_amount(is_interest=True)),
        },
        "disposals": disposals,
        "acquisitions": acquisitions,
        "other_events": other_events,
        "dividends": dividends,
        "interest": interest,
        "interest_by_source": [
            {"broker": b, "currency": c, "amount_gbp": _d(v)}
            for (b, c), v in sorted(interest_totals.items())
        ],
        "interest_tax": interest_tax,
        "other_income": [other_income[k] for k in sorted(other_income)],
        "eri_distributions": eri_distributions,
        "portfolio_eoy": [
            {"symbol": p.symbol, "quantity": _d(p.quantity), "pool_cost": _d(p.amount)}
            for p in report.portfolio
            if p.quantity > 0
        ],
        "warnings": [],
    }
