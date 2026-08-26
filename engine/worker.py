"""cgt-calc worker — the ONLY module that imports cgt_calc, always run as a
short-lived subprocess (`python -m engine.worker job.json result.json`).

Isolation matters because the library is not web-safe: it mutates the global
decimal context, SpinOffHandler falls back to input() for unknown spin-offs,
and SchwabParser keeps class-level mutable state. A fresh process per run makes
all of that harmless.

Job JSON:
  {"mode": "validate", "account_type": ..., "file": path}
  {"mode": "calculate", "tax_year": int, "files": {schwab|schwab_award|
   schwab_equity_award_json|freetrade|raw: path}, "spin_offs": {dst: src},
   "exchange_rates_file": path, "isin_translation_file": path,
   "work_dir": path, "pdf_path": path|null, "balance_check": bool}

Result JSON: {"ok": true, ...} or {"ok": false, "error": {"type", "message", ...}}.
Written to the result file, never stdout (the library prints to stdout).
"""

import decimal
import json
import logging
import os
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from cgt_calc.exceptions import CgtError, InvalidTransactionError

from engine.serialize import serialize_report


class UnknownSpinOffError(Exception):
    def __init__(self, symbol: str):
        super().__init__(f"Unknown spin-off source for {symbol}")
        self.symbol = symbol


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _capture_warnings() -> _ListHandler:
    handler = _ListHandler()
    logging.getLogger().addHandler(handler)
    return handler


def _patch_spin_off_handler():
    """Unknown spin-offs must raise (with the symbol), never prompt via input()."""
    from cgt_calc.spin_off_handler import SpinOffHandler

    def get_spin_off_source(self, symbol, *args, **kwargs):
        if symbol in self.cache:
            return self.cache[symbol]
        raise UnknownSpinOffError(symbol)

    SpinOffHandler.get_spin_off_source = get_spin_off_source


def _tx_stats(transactions) -> dict:
    dates = [t.date for t in transactions]
    return {
        "tx_count": len(transactions),
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
    }


def run_validate(job: dict) -> dict:
    from cgt_calc.parsers.freetrade import FreetradeParser
    from cgt_calc.parsers.raw import RawParser
    from cgt_calc.parsers.schwab import AwardPrices, SchwabParser, _read_schwab_awards
    from cgt_calc.parsers.schwab_equity_award_json import SchwabEquityAwardsJSONParser

    handler = _capture_warnings()
    path = Path(job["file"])
    account_type = job["account_type"]
    warnings: list[str] = []

    if account_type == "schwab_individual":
        # Stock Plan Activity rows need award prices, which live in a separate
        # document — for standalone validation fall back to price 0 and warn.
        misses: list[str] = []
        orig_get = AwardPrices.get

        def tolerant_get(self, dt, symbol):
            try:
                return orig_get(self, dt, symbol)
            except KeyError:
                misses.append(f"{symbol} on {dt.isoformat()}")
                return (dt, Decimal(0))

        AwardPrices.get = tolerant_get
        try:
            transactions = SchwabParser.load_from_file(path)
        finally:
            AwardPrices.get = orig_get
        stats = _tx_stats(transactions)
        if misses:
            warnings.append(
                f"{len(misses)} RSU vest rows (stock-plan activity: "
                f"{', '.join(misses[:3])}{', …' if len(misses) > 3 else ''}) have no price "
                "in this file — it comes from the Equity Awards export. Add a "
                "'Schwab — Equity Awards' account and upload that export; this note "
                "disappears once it's there."
            )
        # The library's own "No Schwab Award file provided" is the same fact, said worse.
        handler.messages = [m for m in handler.messages if "schwab award file" not in m.lower()]
    elif account_type == "schwab_awards":
        if path.suffix.lower() == ".json":
            transactions = SchwabEquityAwardsJSONParser.load_from_file(path)
            stats = _tx_stats(transactions)
        else:
            prices = _read_schwab_awards(path)
            dates = sorted(prices.award_prices)
            stats = {
                "tx_count": sum(len(v) for v in prices.award_prices.values()),
                "date_min": dates[0].isoformat() if dates else None,
                "date_max": dates[-1].isoformat() if dates else None,
            }
    elif account_type == "freetrade_gia":
        stats = _tx_stats(FreetradeParser.load_from_file(path))
    elif account_type in ("raw_csv", "bank_generic"):
        stats = _tx_stats(RawParser.load_from_file(path))
    else:
        raise ValueError(f"Unknown account type: {account_type}")

    warnings.extend(handler.messages)
    return {"ok": True, **stats, "warnings": warnings}


def detect_withholding_refunds(transactions) -> list[dict]:
    """Pair sales whose reported amount is short of quantity × price − fees with a
    later positive ADJUSTMENT for the same symbol/currency and the same amount
    (a broker refunding backup withholding). Must run BEFORE the fork's
    convert_to_hmrc_transactions, which overwrites the sale amount."""
    from cgt_calc.model import ActionType

    refunds: list[dict] = []
    adjustments = [
        t
        for t in transactions
        if t.action == ActionType.ADJUSTMENT and t.amount is not None and t.amount > 0
    ]
    for sale in transactions:
        if (
            sale.action != ActionType.SELL
            or sale.amount is None
            or not sale.quantity
            or not sale.price
        ):
            continue
        missing = sale.quantity * sale.price - (sale.fees or Decimal(0)) - sale.amount
        if missing < Decimal("0.50"):
            continue
        for adj in adjustments:
            days = (adj.date - sale.date).days
            if (
                adj.symbol == sale.symbol
                and adj.currency == sale.currency
                and abs(adj.amount - missing) < Decimal("0.05")
                and 0 <= days <= 60
            ):
                refunds.append(
                    {
                        "symbol": sale.symbol,
                        "sale_date": sale.date.isoformat(),
                        "refund_date": adj.date.isoformat(),
                        "amount": str(adj.amount),
                        "currency": sale.currency,
                        "days": days,
                    }
                )
                adjustments.remove(adj)
                break
    return refunds


def run_calculate(job: dict) -> dict:
    from cgt_calc import render_latex
    from cgt_calc.args_parser import create_parser
    from cgt_calc.currency_converter import CurrencyConverter
    from cgt_calc.current_price_fetcher import CurrentPriceFetcher
    from cgt_calc.exceptions import MissingExternalToolError
    from cgt_calc.initial_prices import InitialPrices
    from cgt_calc.isin_converter import IsinConverter
    from cgt_calc.main import CapitalGainsCalculator
    from cgt_calc.parsers.broker_registry import BrokerRegistry
    from cgt_calc.spin_off_handler import SpinOffHandler

    _patch_spin_off_handler()
    # Same strictness as the CLI's main(): mixing Decimal and float raises.
    decimal.getcontext().traps[decimal.FloatOperation] = True

    os.chdir(job["work_dir"])  # pdflatex + any library relative writes land here
    handler = _capture_warnings()

    flag_map = {
        "schwab": "--schwab-file",
        "schwab_award": "--schwab-award-file",
        "schwab_equity_award_json": "--schwab-equity-award-json",
        "freetrade": "--freetrade-file",
        "raw": "--raw-file",
        "eri_raw": "--eri-raw-file",
    }
    argv = ["--year", str(job["tax_year"]), "--no-report"]
    for key, flag in flag_map.items():
        if job["files"].get(key):
            argv += [flag, job["files"][key]]
    argv += ["--exchange-rates-file", job["exchange_rates_file"]]
    argv += ["--isin-translation-file", job["isin_translation_file"]]
    argv += ["--spin-offs-file", os.path.join(job["work_dir"], "spin_offs.csv")]
    if not job.get("balance_check", True):
        argv.append("--no-balance-check")
    args = create_parser().parse_args(argv)

    # Mirror cgt_calc.main.calculate_cgt, but keep the report object.
    isin_converter = IsinConverter(args.isin_translation_file)
    broker_transactions = BrokerRegistry.load_all_transactions(args, isin_converter)
    refunds = detect_withholding_refunds(broker_transactions)
    currency_converter = CurrencyConverter(args.exchange_rates_file)
    price_fetcher = CurrentPriceFetcher(currency_converter)
    initial_prices = InitialPrices(args.initial_prices_file)
    spin_off_handler = SpinOffHandler(args.spin_offs_file)
    spin_off_handler.cache.update(job.get("spin_offs", {}))

    calculator = CapitalGainsCalculator(
        args.year,
        currency_converter,
        isin_converter,
        price_fetcher,
        spin_off_handler,
        initial_prices,
        args.interest_fund_tickers,
        balance_check=args.balance_check,
        calc_unrealized_gains=False,
    )
    calculator.convert_to_hmrc_transactions(broker_transactions)
    report = calculator.calculate_capital_gain()

    pdf_rendered = False
    if job.get("pdf_path"):
        try:
            render_latex.render_pdf(report, output_path=Path(job["pdf_path"]))
            pdf_rendered = True
        except MissingExternalToolError as e:
            handler.messages.append(f"PDF not rendered: {e}")

    bundle = serialize_report(report)
    bundle["refunds"] = refunds
    bundle["warnings"] = handler.messages + bundle.get("warnings", [])
    bundle["meta"] = {
        "files": {k: os.path.basename(v) for k, v in job["files"].items() if v},
        "balance_check": job.get("balance_check", True),
        "generated": date.today().isoformat(),
    }
    return {"ok": True, "bundle": bundle, "pdf_rendered": pdf_rendered}


# InvalidTransactionError appends the offending transaction's Python repr to
# its message; the UI gets it as structured fields instead.
_TRANSACTION_MARKER = " for the following transaction:\n"

# The balance check fails with one enormous string: a headline, then a ledger of
# transaction reprs each followed by its running balance, then a CLI tip. The UI
# gets the headline as fields and the ledger as rows.
_BALANCE_HEADER = re.compile(
    r"Reached a negative balance\((?P<balance>-?[\d.]+)\) for broker (?P<broker>.+?) "
    r"\((?P<currency>[A-Z]{3})\) after processing the following transactions:\n"
)
_BALANCE_ROW = "Balance after transaction="


def _parse_transaction_repr(line: str) -> dict:
    """Pull the fields the UI shows out of a BrokerTransaction repr. Anything
    unparseable is kept verbatim as a note rather than dropped."""

    def grab(pattern: str) -> str | None:
        m = re.search(pattern, line)
        return m.group(1) if m else None

    day = re.search(r"date=datetime\.date\((\d+), (\d+), (\d+)\)", line)
    action = grab(r"action=<ActionType\.(\w+)")
    description = grab(r"description='([^']*)'") or ""
    if action and description.endswith(f" ActionType.{action}"):
        description = description[: -len(f" ActionType.{action}")]
    row = {
        "date": date(*(int(g) for g in day.groups())).isoformat() if day else None,
        "action": action,
        "symbol": grab(r"symbol='([^']*)'"),
        "description": description or None,
        "amount": grab(r"amount=Decimal\('([^']*)'\)"),
        "balance": None,
    }
    return row if any(v for v in row.values()) else {"note": line}


def parse_balance_ledger(body: str) -> list[dict]:
    rows: list[dict] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(_BALANCE_ROW):
            if rows:
                rows[-1]["balance"] = line[len(_BALANCE_ROW) :]
            continue
        if line.startswith("..."):  # "... N earlier transaction(s) omitted ..."
            rows.append({"note": line.strip(". ")})
            continue
        rows.append(_parse_transaction_repr(line))
    return rows


def describe_transaction(t) -> dict:
    """Flatten a BrokerTransaction for the API (money as strings)."""

    def money(v):
        return None if v is None else str(v)

    return {
        "date": t.date.isoformat(),
        "action": t.action.name,
        "symbol": t.symbol,
        "isin": t.isin,
        "description": t.description,
        "quantity": money(t.quantity),
        "price": money(t.price),
        "fees": money(t.fees),
        "amount": money(t.amount),
        "currency": t.currency,
        "broker": t.broker,
    }


def describe_error(e: Exception) -> dict:
    if isinstance(e, UnknownSpinOffError):
        return {"type": "unknown_spin_off", "symbol": e.symbol, "message": str(e)}
    if isinstance(e, InvalidTransactionError):
        message = str(e).split(_TRANSACTION_MARKER, 1)[0]
        return {
            "type": type(e).__name__,
            "message": message,
            "transaction": describe_transaction(e.transaction),
        }
    if isinstance(e, CgtError):
        text = str(e)
        m = _BALANCE_HEADER.match(text)
        if m:
            body = text[m.end() :].split("\nTip:")[0]
            return {
                "type": "negative_balance",
                "message": (
                    f"{m['broker']}'s running {m['currency']} cash balance goes negative "
                    f"({m['balance']}), so money left the account that your documents never "
                    "show arriving."
                ),
                "broker": m["broker"],
                "currency": m["currency"],
                "balance": m["balance"],
                "ledger": parse_balance_ledger(body),
            }
        return {"type": type(e).__name__, "message": text}
    return {"type": "unexpected", "message": f"{type(e).__name__}: {e}"}


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    job_path, result_path = sys.argv[1], sys.argv[2]
    with open(job_path) as f:
        job = json.load(f)
    try:
        if job["mode"] == "validate":
            result = run_validate(job)
        elif job["mode"] == "calculate":
            result = run_calculate(job)
        else:
            raise ValueError(f"Unknown mode: {job['mode']}")
    except Exception as e:  # noqa: BLE001 — every failure must become a structured result
        logging.exception("worker failed")
        result = {"ok": False, "error": describe_error(e)}
    with open(result_path, "w") as f:
        json.dump(result, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
