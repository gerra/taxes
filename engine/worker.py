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
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from cgt_calc.exceptions import CgtError

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
                f"{len(misses)} stock-plan rows need the Equity Awards document "
                f"for vest prices ({', '.join(misses[:3])}" + (", …)" if len(misses) > 3 else ")")
            )
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
    bundle["warnings"] = handler.messages + bundle.get("warnings", [])
    bundle["meta"] = {
        "files": {k: os.path.basename(v) for k, v in job["files"].items() if v},
        "balance_check": job.get("balance_check", True),
        "generated": date.today().isoformat(),
    }
    return {"ok": True, "bundle": bundle, "pdf_rendered": pdf_rendered}


def describe_error(e: Exception) -> dict:
    if isinstance(e, UnknownSpinOffError):
        return {"type": "unknown_spin_off", "symbol": e.symbol, "message": str(e)}
    if isinstance(e, CgtError):
        return {"type": type(e).__name__, "message": str(e)}
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
