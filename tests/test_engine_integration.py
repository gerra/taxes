"""End-to-end engine test: real worker subprocess over a GBP-only raw fixture
(GBP never triggers HMRC exchange-rate fetches, so no network is needed)."""

import json
import os
import subprocess
import sys
from decimal import Decimal

import pytest

from core import paths

_RAW = """date,action,symbol,quantity,price,fees,currency
2023-04-10,TRANSFER,,1,2000,0,GBP
2023-05-01,BUY,TST,100,10.00,0,GBP
2023-06-01,SELL,TST,50,12.00,0,GBP
2023-07-31,INTEREST,,1,123.45,0,GBP
"""


def _run_worker(job, work_dir):
    job_path = os.path.join(work_dir, "job.json")
    result_path = os.path.join(work_dir, "result.json")
    with open(job_path, "w") as f:
        json.dump(job, f)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-m", "engine.worker", job_path, result_path],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert os.path.exists(result_path), f"worker crashed: {proc.stderr[-2000:]}"
    with open(result_path) as f:
        return json.load(f)


@pytest.fixture
def raw_file(tmp_path):
    p = tmp_path / "raw.csv"
    p.write_text(_RAW)
    return str(p)


def test_validate_raw(raw_file, tmp_path):
    result = _run_worker(
        {"mode": "validate", "account_type": "raw_csv", "file": raw_file}, str(tmp_path)
    )
    assert result["ok"], result
    assert result["tx_count"] == 4
    assert result["date_min"] == "2023-04-10"
    assert result["date_max"] == "2023-07-31"


def test_validate_bad_file(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("date,action\n2023-01-01,BUY\n")
    result = _run_worker(
        {"mode": "validate", "account_type": "raw_csv", "file": str(bad)}, str(tmp_path)
    )
    assert not result["ok"]
    assert result["error"]["type"]


def test_runner_logs_worker_failure(tmp_path, caplog):
    """The web side logs a failed job and the worker's traceback, so a rejected
    upload is diagnosable from the journal."""
    import logging

    from engine.runner import _run_worker as runner_run_worker

    caplog.set_level(logging.INFO)
    bad = tmp_path / "bad.csv"
    bad.write_text("date,action\n2023-01-01,BUY\n")
    result = runner_run_worker(
        {"mode": "validate", "account_type": "raw_csv", "file": str(bad)}, str(tmp_path)
    )
    assert not result["ok"]
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        m.startswith("worker (validate, raw_csv) failed: ") and result["error"]["message"] in m
        for m in messages
    )
    assert any("worker stderr tail:" in m and "Traceback" in m for m in messages)


def test_calculate_2023(raw_file, tmp_path):
    paths.ensure_dirs()
    work_dir = str(tmp_path / "work")
    os.makedirs(work_dir)
    job = {
        "mode": "calculate",
        "tax_year": 2023,
        "files": {"raw": raw_file},
        "spin_offs": {},
        "exchange_rates_file": str(tmp_path / "rates.csv"),
        "isin_translation_file": str(tmp_path / "isin.csv"),
        "work_dir": work_dir,
        "pdf_path": None,
        "balance_check": True,
    }
    result = _run_worker(job, work_dir)
    assert result["ok"], result
    totals = result["bundle"]["totals"]
    assert totals["disposal_count"] == 1
    assert Decimal(totals["disposal_proceeds"]) == 600
    assert Decimal(totals["allowable_costs"]) == 500
    assert Decimal(totals["capital_gain_before_losses"]) == 100
    assert Decimal(totals["total_gain"]) == 100
    assert Decimal(totals["capital_gain_allowance"]) == 6000
    assert Decimal(totals["taxable_gain"]) == 0
    assert Decimal(totals["uk_interest"]) == Decimal("123.45")
    disposals = result["bundle"]["disposals"]
    assert len(disposals) == 1
    assert disposals[0]["symbol"] == "TST"
    assert disposals[0]["entries"][0]["rule"] == "SECTION_104"
    portfolio = result["bundle"]["portfolio_eoy"]
    assert len(portfolio) == 1
    assert portfolio[0]["symbol"] == "TST"
    assert Decimal(portfolio[0]["quantity"]) == 50
    assert Decimal(portfolio[0]["pool_cost"]) == 500


_RAW_INCOME = """date,action,symbol,quantity,price,fees,currency
2023-04-10,TRANSFER,,1,2000,0,GBP
2023-05-01,BUY,TST,100,10.00,0,GBP
2023-05-01,BUY,GLT,100,0.94,0,GBP
2023-06-01,SELL,TST,50,12.00,0,GBP
2023-06-01,SELL,GLT,100,0.95,0,GBP
2023-08-15,OTHER_INCOME,PHP,1,80.64,0,GBP
2023-08-15,OTHER_INCOME_TAX,PHP,1,-16.13,0,GBP
2023-08-17,OTHER_INCOME,,1,0.12,0,GBP
"""


def test_calculate_other_income_and_exempt_security(tmp_path):
    """A gilt named in the job is listed but not charged; REIT income and its
    withheld tax land in the other-income bucket, not interest."""
    paths.ensure_dirs()
    raw = tmp_path / "raw.csv"
    raw.write_text(_RAW_INCOME)
    work_dir = str(tmp_path / "work")
    os.makedirs(work_dir)
    job = {
        "mode": "calculate",
        "tax_year": 2023,
        "files": {"raw": str(raw)},
        "spin_offs": {},
        "exempt_securities": ["glt"],
        "exchange_rates_file": str(tmp_path / "rates.csv"),
        "isin_translation_file": str(tmp_path / "isin.csv"),
        "work_dir": work_dir,
        "pdf_path": None,
        "balance_check": True,
    }
    result = _run_worker(job, work_dir)
    assert result["ok"], result
    bundle = result["bundle"]
    totals = bundle["totals"]
    assert totals["disposal_count"] == 1
    assert Decimal(totals["disposal_proceeds"]) == 600
    assert Decimal(totals["total_gain"]) == 100
    assert totals["exempt_disposal_count"] == 1
    assert Decimal(totals["exempt_disposal_proceeds"]) == 95
    assert Decimal(totals["other_income"]) == Decimal("80.76")
    assert Decimal(totals["other_income_tax"]) == Decimal("16.13")
    assert Decimal(totals["uk_interest"]) == 0

    by_symbol = {d["symbol"]: d for d in bundle["disposals"]}
    assert by_symbol["TST"]["exempt"] is False
    assert by_symbol["GLT"]["exempt"] is True
    assert Decimal(by_symbol["GLT"]["gain"]) == 1
    assert bundle["other_income"] == [
        {"date": "2023-08-15", "source": "PHP", "amount_gbp": "80.64", "tax_gbp": "16.13"},
        {"date": "2023-08-17", "source": "Unknown", "amount_gbp": "0.12", "tax_gbp": "0"},
    ]
    assert bundle["exempt"]["securities"] == [
        {"symbol": "GLT", "isin": None, "kind": "manual", "title": None, "source": "configured"}
    ]
    assert bundle["exempt"]["ais_applies"] is False


_RAW_DISTRIBUTIONS = """date,action,symbol,quantity,price,fees,currency
2023-04-10,TRANSFER,,1,5000,0,GBP
2023-05-01,BUY,VGOV,100,10.00,0,GBP
2023-05-01,BUY,ULVR,100,10.00,0,GBP
2023-08-15,DIVIDEND,VGOV,1,45.00,0,GBP
2023-08-15,DIVIDEND,ULVR,1,60.00,0,GBP
"""


def test_bond_fund_distributions_are_taxed_as_interest_not_dividends(tmp_path):
    """VGOV is a gilt fund: the engine must be told so, or its distribution is
    counted as a dividend and eats the dividend allowance."""
    paths.ensure_dirs()
    work_dir = str(tmp_path / "work")
    os.makedirs(work_dir)
    raw = tmp_path / "raw.csv"
    raw.write_text(_RAW_DISTRIBUTIONS)
    job = {
        "mode": "calculate",
        "tax_year": 2023,
        "files": {"raw": str(raw)},
        "spin_offs": {},
        "exchange_rates_file": str(tmp_path / "rates.csv"),
        "isin_translation_file": str(tmp_path / "isin.csv"),
        "work_dir": work_dir,
        "pdf_path": None,
        "balance_check": True,
    }
    result = _run_worker(job, work_dir)
    assert result["ok"], result
    bundle = result["bundle"]
    assert Decimal(bundle["totals"]["dividends_total"]) == 60
    by_symbol = {d["symbol"]: d for d in bundle["dividends"]}
    assert by_symbol["VGOV"]["is_interest"] is True
    assert by_symbol["ULVR"]["is_interest"] is False
    # The audit columns: currency and the rate used (1 for a GBP payment).
    assert by_symbol["ULVR"]["currency"] == "GBP"
    assert by_symbol["ULVR"]["fx_rate"] == "1"
    assert Decimal(by_symbol["ULVR"]["gross"]) == 60
